from flask import Flask, request, jsonify
from sympy import symbols, Interval, Union, S, simplify, Eq, solveset, sympify
import re, os

app = Flask(__name__)
x = symbols('x')
session_state = {}

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '').strip().lower()
    session_id = req.get('session', 'default')

    if "f(x)=" in user_input:
        session_state.pop(session_id, None)

    if "reset" in user_input and len(user_input) <= 20:
        session_state.pop(session_id, None)
        return respond("Très bien ! Reprenons depuis le début. Envoie-moi une nouvelle fonction sous la forme : f(x) = ...")

    if session_id not in session_state:
        expr = extract_expr(user_input)
        if not expr:
            return respond("Écris la fonction sous la forme : f(x) = ...")

        components = analyse_expression(expr)
        if not components:
            return respond("La fonction est définie sur ℝ : aucun log, racine ni dénominateur détecté.")

        session_state[session_id] = {
            "expr": expr,
            "steps": components,
            "current": 0,
            "mode": "condition",
            "conditions": [],
            "attente_finale": False
        }

        current_type, arg = components[0]
        return respond(f"Commençons. Quelle est la condition sur {component_label(current_type)} {arg} pour qu’il soit défini ?")

    state = session_state[session_id]

    if state.get("attente_finale"):
        if any(token in user_input for token in ["[", "]", "(", ")", "oo", "∞", "x", "≥", ">", "reel", "r"]):
            correct, bonne_reponse = is_domain_correct_math(user_input, state["conditions"])
            session_state.pop(session_id)
            if correct:
                return respond("Bravo ! Tu as correctement trouvé l'ensemble de définition.")
            else:
                return respond(f"Ce n’est pas tout à fait correct. L’ensemble de définition est : D = {bonne_reponse}\nNe t’inquiète pas, tu peux y arriver avec un peu de pratique !")
        else:
            return respond("Essaie de donner l’ensemble sous forme d’un intervalle, par exemple : ]2,+∞[ ou ℝ.")

    current_type, arg = state["steps"][state["current"]]
    condition = expected_condition(current_type, arg)
    solution = expected_solution(current_type, arg)

    if state["mode"] == "condition":
        if match_condition(user_input, current_type, arg):
            state["mode"] = "solution"
            return respond(f"Parfait ! Résous maintenant cette inéquation : {condition}")
        else:
            state["mode"] = "solution"
            explication = error_explanation(current_type, arg, condition)
            return respond(f"{explication}\nPeux-tu résoudre maintenant cette inéquation : {condition} ?")

    elif state["mode"] == "solution":
        if match_solution(user_input, solution):
            state["conditions"].append(solution)
            return next_step(state, session_id, "Bien joué !")
        else:
            state["conditions"].append(solution)
            return next_step(state, session_id, f"Ce n’est pas tout à fait ça. En réalité, la solution est : {solution}")

def next_step(state, session_id, message):
    state["current"] += 1
    state["mode"] = "condition"

    if state["current"] < len(state["steps"]):
        next_type, next_arg = state["steps"][state["current"]]
        return respond(message + f"\n\nPassons à {component_label(next_type)}. Quelle est la condition sur {next_arg} pour qu’il soit défini ?")
    else:
        state["attente_finale"] = True
        conds = state["conditions"]
        conditions_text = "\n".join(conds)
        return respond(message + "\n\nVoici les conditions obtenues sur x :\n" + conditions_text +
                       "\nPeux-tu en déduire maintenant l’ensemble de définition D ?")

# ==== outils ====

def extract_expr(text):
    match = re.search(r"f\(x\)\s*=\s*(.+)", text)
    if not match:
        return None
    expr_raw = match.group(1)
    return re.sub(r"√\s*\((.*?)\)", r"sqrt(\1)", expr_raw)

def analyse_expression(expr):
    components = []
    components += [("racine", arg) for arg in re.findall(r'sqrt\((.*?)\)', expr)]
    components += [("log", arg) for arg in re.findall(r'log\((.*?)\)', expr)]
    if "/" in expr:
        denom = expr.split("/")[-1]
        components.append(("denominateur", denom.strip()))
    return components

def component_label(type_):
    return {
        "racine": "√",
        "log": "log",
        "denominateur": "le dénominateur"
    }.get(type_, "cette expression")

def expected_condition(type_, arg):
    if type_ == "racine":
        return f"{arg} ≥ 0"
    elif type_ == "log":
        return f"{arg} > 0"
    elif type_ == "denominateur":
        return f"{arg} ≠ 0"
    return ""

def expected_solution(type_, arg):
    try:
        expr = arg.replace("^", "**").strip()
        sym_expr = sympify(expr)

        if type_ == "racine":
            sols = solveset(sym_expr >= 0, x, domain=S.Reals)
        elif type_ == "log":
            sols = solveset(sym_expr > 0, x, domain=S.Reals)
        elif type_ == "denominateur":
            sols = solveset(Eq(sym_expr, 0), x, domain=S.Reals)
            return " et ".join([f"x ≠ {s}" for s in sols])

        return str(sols)
    except:
        return "?"

def match_condition(reply, type_, arg):
    reply = reply.replace(" ", "").replace(">=", "≥").replace("<=", "≤").replace("!=", "≠").lower()
    patterns = {
        "racine": ["≥0", "positif", "nonnégatif", f"{arg}≥0"],
        "log": [">0", "strictementpositif", f"{arg}>0"],
        "denominateur": ["≠0", "différent", "nonnul", f"{arg}≠0"]
    }
    return any(p in reply for p in patterns.get(type_, []))

def match_solution(reply, attendu):
    normalize = lambda s: s.replace(" ", "").replace(">=", "≥").replace("<=", "≤").replace("!=", "≠").lower()
    reply_norm = normalize(reply)
    attendu_norm = normalize(attendu)
    if attendu_norm in reply_norm:
        return True
    reply_parts = set(re.split(r"[ouet]+", reply_norm))
    attendu_parts = set(re.split(r"[ouet]+", attendu_norm))
    return reply_parts == attendu_parts

def condition_to_set(condition_str):
    if "?" in condition_str:
        return S.Reals
    try:
        if "≥" in condition_str:
            val = int(condition_str.split("≥")[1].strip())
            return Interval(val, S.Infinity)
        elif ">" in condition_str:
            val = int(condition_str.split(">")[1].strip())
            return Interval.open(val, S.Infinity)
        elif "≠" in condition_str:
            val = int(condition_str.split("≠")[1].strip())
            return Union(Interval.open(-S.Infinity, val), Interval.open(val, S.Infinity))
    except:
        return S.Reals
    return S.Reals

def parse_student_domain(reply):
    try:
        reply = reply.lower().replace(" ", "").replace("∞", "oo").replace("+oo", "oo").replace("−", "-")
        reply = reply.replace("d=", "")
        match = re.match(r"[\[\]()\]]?(-?\d+)[;,]?(\+?oo)[\[\]()\]]?", reply)
        if match:
            a = float(match.group(1))
            return Interval(float(a), S.Infinity, left_open=reply.startswith("]") or reply.startswith("("))
        match_union = re.findall(r"-?oo,(-?\d+)", reply)
        match_union2 = re.findall(r"(-?\d+),\+?oo", reply)
        if len(match_union) == 1 and len(match_union2) == 2:
            a = float(match_union[0])
            return Union(Interval.open(-S.Infinity, a), Interval.open(a, S.Infinity))
        if "r" in reply or "reel" in reply:
            return S.Reals
    except:
        return None
    return None

def is_domain_correct_math(reply, conditions):
    sets = [condition_to_set(cond) for cond in conditions if "?" not in cond]
    if not sets:
        return False, "ℝ"
    correct_domain = sets[0]
    for s in sets[1:]:
        correct_domain = correct_domain.intersect(s)
    student_set = parse_student_domain(reply)
    correct_str = convert_to_notation(correct_domain)
    if student_set is None:
        return False, correct_str
    try:
        if student_set == correct_domain or Eq(student_set, correct_domain):
            return True, correct_str
    except:
        pass
    return False, correct_str

def convert_to_notation(interval):
    if isinstance(interval, Interval):
        a = "-∞" if interval.start == S.NegativeInfinity else str(interval.start)
        b = "+∞" if interval.end == S.Infinity else str(interval.end)
        left = "]" if interval.left_open else "["
        right = "[" if interval.right_open == False else "["
        return f"{left}{a}, {b}{right}"
    elif isinstance(interval, Union):
        parts = [convert_to_notation(i) for i in interval.args]
        return " ∪ ".join(parts)
    return "ℝ"

def respond(text):
    return jsonify({"fulfillmentText": text})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
