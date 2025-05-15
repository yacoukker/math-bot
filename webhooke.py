from flask import Flask, request, jsonify
from sympy import symbols, Interval, Union, S
import re, os

app = Flask(__name__)
x = symbols('x')
session_state = {}

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '').strip().lower()
    session_id = req.get('session', 'default')

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
        correct, bonne_reponse = is_domain_correct_math(user_input, state["conditions"])
        session_state.pop(session_id)
        if correct:
            return respond("Bravo ! Tu as correctement trouvé l'ensemble de définition.")
        else:
            return respond(f"Ce n’est pas tout à fait correct. L’ensemble de définition est : D = {bonne_reponse}\nNe t’inquiète pas, tu peux y arriver avec un peu de pratique !")

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
    if type_ == "racine":
        return f"x ≥ {solve_for_x(arg)}"
    elif type_ == "log":
        return f"x > {solve_for_x(arg)}"
    elif type_ == "denominateur":
        return f"x ≠ {solve_for_x(arg)}"
    return ""

def solve_for_x(expr):
    expr = expr.replace(" ", "")
    expr = expr.strip("()")  # إزالة الأقواس إذا وُجدت
    match = re.match(r"x([\+\-])(\d+)", expr)
    if match:
        sign, number = match.groups()
        return str(-int(number)) if sign == '+' else str(int(number))
    return "?"

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
        "denominateur": ["≠0", "différent", "nonnul", f"{arg}≠0"]
    }
    return any(p in reply for p in patterns.get(type_, []))

def match_solution(reply, attendu):
    reply = reply.replace(" ", "").replace(">=", "≥").replace("!=", "≠")
    return attendu.replace(" ", "") in reply

def condition_to_set(condition_str):
    if "?" in condition_str:
        return S.Reals  # تجاهل الشروط غير المفهومة

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
        reply = reply.replace(" ", "").replace("[", "").replace("]", "")
        reply = reply.replace("∞", "oo").replace("+oo", "oo").replace("−", "-")
        match = re.match(r"\]?(-?\d+),\+?oo\[?", reply)
        if match:
            a = float(match.group(1))
            return Interval.open(a, S.Infinity)
        elif "r" in reply or "ℝ" in reply:
            return S.Reals
    except:
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
    return student_set == correct_domain, correct_str

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
