from flask import Flask, request, jsonify
from sympy import symbols, sympify, solveset, S, log
import re, os

app = Flask(__name__)
x = symbols('x')
session_state = {}

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '').strip()
    session_id = req.get('session', 'default')

    if session_id not in session_state:
        expr_str = extract_expr(user_input)
        if not expr_str:
            return respond("Merci d’écrire la fonction sous la forme : f(x) = ...")
        try:
            expr = sympify(expr_str)
        except:
            return respond("Je n’ai pas pu comprendre la fonction. Essaie encore.")

        steps = []

        # استخراج المكونات
        sqrt_matches = re.findall(r'sqrt\((.*?)\)', expr_str)
        steps += [("racine", arg.strip()) for arg in sqrt_matches]

        log_matches = re.findall(r'log\((.*?)\)', expr_str)
        steps += [("log", arg.strip()) for arg in log_matches]

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
            "awaiting_solution": False,
            "retry": False,
            "attente_finale": False
        }

        type_, arg = steps[0]
        condition = expected_condition(type_, arg)
        session_state[session_id]['current_condition'] = condition
        session_state[session_id]['awaiting_solution'] = True
        return respond(f"{explain_condition(type_, arg)}\nPeux-tu résoudre cette condition : {condition} ?")

    state = session_state[session_id]

    # المرحلة النهائية
    if state.get("attente_finale"):
        return respond(handle_final_domain(user_input, state))

    # حل الشرط الحالي
    if state.get("awaiting_solution"):
        condition = state.get("current_condition")
        if is_correct_answer(user_input, condition):
            state['conditions'].append(condition)
            state['awaiting_solution'] = False
            state['retry'] = False
            return next_step(session_id, "Bravo, bonne réponse !")
        elif is_unknown(user_input) or state.get("retry"):
            state['conditions'].append(condition)
            state['awaiting_solution'] = False
            state['retry'] = False
            return next_step(session_id, f"Pas de souci ! La solution est : {condition}")
        else:
            state['retry'] = True
            return respond("Essaie encore une fois de résoudre cette condition.")

    return respond("Je n’ai pas compris. Peux-tu reformuler ?")

# ========= OUTILS ========

def extract_expr(text):
    match = re.search(r"f\(x\)\s*=\s*(.+)", text)
    if not match:
        return None
    expr_raw = match.group(1)
    return re.sub(r"√\s*\((.*?)\)", r"sqrt(\1)", expr_raw)

def explain_condition(type_, arg):
    if type_ == "racine":
        return f"Pour que √({arg}) soit définie, il faut que {arg} soit positif ou nul."
    elif type_ == "log":
        return f"Pour que log({arg}) soit définie, il faut que {arg} soit strictement positif."
    elif type_ == "denominateur":
        return f"On doit éviter que le dénominateur {arg} soit nul."
    return ""

def expected_condition(type_, arg):
    if type_ == "racine":
        return f"{arg} ≥ 0"
    elif type_ == "log":
        return f"{arg} > 0"
    elif type_ == "denominateur":
        return f"{arg} ≠ 0"
    return ""

def is_correct_answer(user_input, attendu):
    cleaned = user_input.replace(" ", "").replace(">=️", "≥").replace(">=", "≥").replace("!=", "≠")
    return cleaned == attendu.replace(" ", "")

def is_unknown(user_input):
    user_input = user_input.lower()
    return user_input in ["je ne sais pas", "aucune idée", "pas sûr", "non", "je ne peux pas", "je ne trouve pas"]

def next_step(session_id, response_prefix):
    state = session_state[session_id]
    state["current"] += 1

    if state["current"] < len(state["steps"]):
        type_, arg = state["steps"][state["current"]]
        condition = expected_condition(type_, arg)
        state["current_condition"] = condition
        state["awaiting_solution"] = True
        return respond(f"{response_prefix}\n\nNouvelle condition : {explain_condition(type_, arg)}\nPeux-tu résoudre : {condition} ?")
    else:
        conds = state["conditions"]
        state["attente_finale"] = True
        return respond(f"{response_prefix}\n\nNous avons trouvé toutes les conditions :\n- " + "\n- ".join(conds) +
                       "\nPeux-tu en déduire maintenant l’ensemble de définition D ?")

def handle_final_domain(user_input, state):
    if is_unknown(user_input):
        return "Pas grave ! En combinant les conditions trouvées, on peut déterminer D comme l’intersection des ensembles admissibles. Bravo pour tes efforts !"
    return "Super ! Tu as su trouver D correctement. Félicitations !"

def respond(text):
    return jsonify({"fulfillmentText": text})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
