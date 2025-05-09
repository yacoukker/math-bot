from flask import Flask, request, jsonify
import re, os

app = Flask(__name__)
x = 'x'
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
        return respond(start_condition(current_type, arg))

    # Suite du scénario
    state = session_state[session_id]

    if state.get("attente_finale"):
        return respond(handle_domain_answer(user_input, state, session_id))

    current_type, arg = state["steps"][state["current"]]
    attendu = expected_condition(current_type, arg)
    solution = expected_solution(current_type, arg)

    if state["mode"] == "condition":
        if match_condition(user_input, current_type, arg):
            state["mode"] = "solution"
            return respond(f"Très bien ! Résous maintenant cette condition : {attendu}")
        else:
            state["mode"] = "solution"
            return respond(f"Pas grave. Pour que {label_component(current_type)} soit défini, on doit avoir : {attendu}.\nPeux-tu le résoudre ?")

    elif state["mode"] == "solution":
        if match_solution(user_input, solution):
            state["conditions"].append(solution)
            return next_step(state, session_id, "Excellent, bonne réponse !")
        else:
            state["conditions"].append(solution)
            return next_step(state, session_id, f"Ce n’est pas tout à fait ça. En fait, la solution est : {solution}")

def next_step(state, session_id, message):
    state["current"] += 1
    state["mode"] = "condition"

    if state["current"] < len(state["steps"]):
        next_type, next_arg = state["steps"][state["current"]]
        return respond(message + f"\n\nPassons à {label_component(next_type)}. Quelle est la condition pour que {describe(next_type, next_arg)} soit défini ?")
    else:
        conds = state["conditions"]
        state["attente_finale"] = True
        return respond(message + "\n\nVoici les conditions obtenues :\n- " + "\n- ".join(conds) +
                       "\nPeux-tu en déduire l’ensemble de définition D ?")

def handle_domain_answer(user_input, state, session_id):
    if is_domain_correct(user_input, state["conditions"]):
        session_state.pop(session_id)
        return "Bravo ! Tu as correctement trouvé l'ensemble de définition."
    else:
        session_state.pop(session_id)
        return "La bonne réponse est l’intersection des conditions obtenues. Ne t’en fais pas, essaie encore une autre fois — tu es sur la bonne voie !"

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

def label_component(type_):
    return {
        "racine": "la racine carrée",
        "log": "le logarithme",
        "denominateur": "le dénominateur"
    }.get(type_, "ce composant")

def describe(type_, arg):
    return arg

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
    if expr.startswith("x+"):
        return str(-int(expr[2:]))
    elif expr.startswith("x-"):
        return str(int(expr[2:]))
    return "?"

def match_condition(reply, type_, arg):
    reply = reply.replace(" ", "").replace(">=", "≥").replace("!=", "≠")
    patterns = {
        "racine": ["≥0", "positif", "nonnégatif"],
        "log": [">0", "strictementpositif"],
        "denominateur": ["≠0", "différent", "nonnul"]
    }
    return any(p in reply for p in patterns.get(type_, []))

def match_solution(reply, attendu):
    reply = reply.replace(" ", "").replace(">=", "≥").replace("!=", "≠")
    return attendu.replace(" ", "") in reply

def is_domain_correct(reply, conditions):
    reply = reply.replace(" ", "").replace("]","").replace("[","")
    return all(cond.split()[0] in reply for cond in conditions)

def respond(text):
    return jsonify({"fulfillmentText": text})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
