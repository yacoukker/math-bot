from flask import Flask, request, jsonify
from sympy import symbols, Interval, Union, S, simplify, Eq, solveset
import re, os

app = Flask(__name__)
x = symbols("x")
session_state = {}

@app.route("/webhook", methods=["POST"])
def webhook():
    req = request.get_json()
    user_input = req.get("queryResult", {}).get("queryText", "").strip().lower()
    session_id = req.get("session", "default")

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
            "attente_finale": False,
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
            return respond("Essaie de donner l’ensemble sous forme d’une condition, par exemple : x ≤ -1 ou x ≥ 2.")

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
            state["conditions"].append(convert_to_logic_notation(solution))
            return next_step(state, session_id, f"Ce n’est pas tout à fait ça. En réalité, la solution est : {convert_to_logic_notation(solution)}")

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
        return respond(message + "\n\nVoici les conditions obtenues sur x :\n" + conditions_text + "\nPeux-tu en déduire maintenant l’ensemble de définition D ?")

# ==== outils ====

def extract_expr(text):
    match = re.search(r"f\(x\)\s*=\s*(.+)", text)
    if not match:
        return None
    expr_raw = match.group(1)
    return re.sub(r"√\s*\((.*?)\)", r"sqrt(\1)", expr_raw)

def analyse_expression(expr):
    components = []
    components += [("racine", arg) for arg in re.findall(r"sqrt\((.*?)\)", expr)]
    components += [("log", arg) for arg in re.findall(r"log\((.*?)\)", expr)]
    if "/" in expr:
        denom = expr.split("/")[-1]
        components.append(("denominateur", denom.strip()))
    return components

def component_label(type_):
    return {"racine": "√", "log": "log", "denominateur": "le dénominateur"}.get(type_, "cette expression")

def expected_condition(type_, arg):
    if type_ == "racine":
        return f"{arg} ≥ 0"
    elif type_ == "log":
        return f"{arg} > 0"
    elif type_ == "denominateur":
        return f"{arg} ≠ 0"
    return ""

def expected_solution(type_, arg):
    if type_ == "racine":
        return solve_for_x(arg, '≥')
    elif type_ == "log":
        return solve_for_x(arg, '>')
    elif type_ == "denominateur":
        return solve_for_x(arg, '≠')
    return S.Reals

def solve_for_x(expr, op):
    expr = expr.replace("^", "**")
    try:
        f = simplify(expr)
        if op == '≥':
            return solveset(f >= 0, x, domain=S.Reals)
        elif op == '>':
            return solveset(f > 0, x, domain=S.Reals)
        elif op == '≠':
            return S.Reals - solveset(Eq(f, 0), x, domain=S.Reals)
        else:
            return S.Reals
    except:
        return S.Reals

def error_explanation(type_, arg, condition):
    if type_ == "racine":
        return f"Pas de souci. Pour que la racine carrée soit définie, ce qui est à l’intérieur doit être positif ou nul, donc ici {condition}."
    elif type_ == "log":
        return f"Aucun problème. Pour que le logarithme soit défini, l’argument doit être strictement positif, donc ici {condition}."
    elif type_ == "denominateur":
        return f"Très bien. Le dénominateur ne doit jamais être nul. On a donc {condition}."
    return f"Voici la condition correcte : {condition}"

def match_condition(reply, type_, arg):
    reply = reply.replace(" ", "").replace(">=", "≥").replace("!=", "≠")
    patterns = {
        "racine": ["≥0", "positif", "nonnégatif", f"{arg}≥0"],
        "log": [">0", "strictementpositif", f"{arg}>0"],
        "denominateur": ["≠0", "différent", "nonnul", f"{arg}≠0"],
    }
    return any(p in reply for p in patterns.get(type_, []))

def match_solution(reply, attendu_set):
    try:
        student_set = parse_student_domain(reply)
        return student_set.equals(attendu_set)
    except:
        return False

def convert_to_logic_notation(set_):
    def condition_from_interval(interval):
        conds = []
        if isinstance(interval, Interval):
            if interval.start != S.NegativeInfinity:
                op = '>=' if not interval.left_open else '>'
                conds.append(f"x {op} {interval.start}")
            if interval.end != S.Infinity:
                op = '<=' if not interval.right_open else '<'
                conds.append(f"x {op} {interval.end}")
            return ' et '.join(conds)
        return str(interval)

    if isinstance(set_, Union):
        return ' ou '.join(condition_from_interval(i) for i in set_.args)
    else:
        return condition_from_interval(set_)

# ... (reste du code intact jusqu'à la fonction parse_student_domain)

def parse_student_domain(reply):
    try:
        reply = reply.lower().replace(" ", "").replace("∞", "oo").replace("−", "-")
        reply = reply.replace("d=", "").replace("ou", "||").replace("et", "&&")

        # Cas: x<=-1||x>=2 ou x≤-1||x≥2
        parts = re.split(r"\|\|", reply)
        intervals = []
        for part in parts:
            match = re.match(r"x([<≥≤>]=?)(-?\d+(\.\d+)?)", part)
            if match:
                op, val, _ = match.groups()
                val = float(val)
                if op in ('<=', '≤'):
                    intervals.append(Interval(-S.Infinity, val))
                elif op == '<':
                    intervals.append(Interval.open(-S.Infinity, val))
                elif op in ('>=', '≥'):
                    intervals.append(Interval(val, S.Infinity))
                elif op == '>':
                    intervals.append(Interval.open(val, S.Infinity))

        if len(intervals) == 1:
            return intervals[0]
        elif len(intervals) > 1:
            return Union(*intervals)

        # Cas: format intervalle classique (conservé)
        match = re.match(r"[\[\]()\]]?(-?\d+)[;,]?([+]?oo)[\[\]()\]]?", reply)
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
        if student_set.equals(correct_domain):
            return True, correct_str
    except:
        pass
    return False, correct_str

def respond(text):
    return jsonify({"fulfillmentText": text})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
