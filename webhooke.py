from flask import Flask, request, jsonify
from sympy import symbols, sympify, log
import re, os

app = Flask(__name__)
x = symbols('x')

# حالة الجلسة
session_state = {}

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '').strip()
    session_id = req.get('session', 'default')

    # إذا كانت الجلسة جديدة
    if session_id not in session_state:
        expr_str = extract_expr(user_input)
        if not expr_str:
            return respond("Merci d’écrire la fonction sous la forme : f(x) = ...")
        try:
            expr = sympify(expr_str)
        except:
            return respond("Je n’ai pas pu comprendre la fonction. Essaie encore.")

        steps = []

        # البحث عن جذور
        sqrt_matches = re.findall(r'sqrt\((.*?)\)', expr_str)
        steps += [("racine", arg.strip()) for arg in sqrt_matches]

        # البحث عن log
        log_matches = re.findall(r'log\((.*?)\)', expr_str)
        steps += [("log", arg.strip()) for arg in log_matches]

        # البحث عن مقام
        denom = expr.as_numer_denom()[1]
        if denom != 1:
            steps.append(("denominateur", str(denom)))

        if not steps:
            return respond("La fonction est définie partout : D = ℝ")

        session_state[session_id] = {
            "expr": expr_str,
            "steps": steps,
            "current": 0,
            "conditions": [],
            "attente_finale": False
        }

        type_, arg = steps[0]
        return respond(first_question(type_, arg))

    # متابعة الجلسة
    state = session_state[session_id]

    # إذا كنا في المرحلة النهائية
    if state.get("attente_finale"):
        response = handle_final_domain(user_input, state)
        session_state.pop(session_id)
        return respond(response)

    current = state["current"]
    steps = state["steps"]

    if current < len(steps):
        type_, arg = steps[current]
        attendu = expected_condition(type_, arg)
        if is_correct_answer(user_input, attendu):
            response = f"Très bien ! {attendu}"
        elif is_unknown(user_input):
            response = f"Aucune inquiétude. Pour ce cas, on doit avoir : {attendu}"
        else:
            response = f"Pas tout à fait. Pour ce type, il faut : {attendu}"

        state["conditions"].append(attendu)
        state["current"] += 1

        if state["current"] < len(steps):
            next_type, next_arg = steps[state["current"]]
            response += "\n\nEt maintenant : " + first_question(next_type, next_arg)
        else:
            conds = state["conditions"]
            joined = " et ".join(conds)
            response += f"\n\nOn a maintenant toutes les conditions : {joined}"
            response += "\nPeux-tu en déduire le domaine de définition D ?"
            state["attente_finale"] = True

        return respond(response)

    return respond("Reformule ta question ou propose une autre fonction.")

def extract_expr(text):
    match = re.search(r"f\(x\)\s*=\s*(.+)", text)
    if not match:
        return None
    expr_raw = match.group(1)
    expr_fixed = re.sub(r"√\s*\((.*?)\)", r"sqrt(\1)", expr_raw)
    return expr_fixed

def first_question(type_, arg):
    if type_ == "racine":
        return f"Quelle condition doit vérifier {arg} pour que √({arg}) soit définie ?"
    elif type_ == "log":
        return f"Que doit-on imposer à {arg} pour que log({arg}) soit défini ?"
    elif type_ == "denominateur":
        return f"Que faut-il éviter avec le dénominateur {arg} ?"
    return "Analysons cette fonction."

def expected_condition(type_, arg):
    if type_ == "racine":
        return f"{arg} ≥ 0"
    elif type_ == "log":
        return f"{arg} > 0"
    elif type_ == "denominateur":
        return f"{arg} ≠ 0"
    return ""

def is_correct_answer(user_input, attendu):
    cleaned = user_input.replace(" ", "")
    return cleaned == attendu.replace(" ", "")

def is_unknown(user_input):
    user_input = user_input.lower()
    return user_input in ["je ne sais pas", "aucune idée", "pas sûr", "non", "je ne peux pas", "je ne trouve pas"]

def handle_final_domain(user_input, state):
    if is_unknown(user_input):
        conds = state["conditions"]
        return "Pas de souci ! En combinant toutes les conditions :\n" + \
               " et ".join(conds) + "\nOn peut en déduire l'ensemble de définition D."

    return "Excellent ! Tu as su en déduire le domaine. Bravo pour ton raisonnement !"

def respond(text):
    return jsonify({"fulfillmentText": text})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
