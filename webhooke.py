from flask import Flask, request, jsonify
from sympy import symbols, sympify, sqrt, log
import re, os

app = Flask(__name__)
x = symbols('x')

# تتبع حالة كل session حسب نوع المكون والمرحلة
session_state = {}

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '')
    session_id = req.get('session', 'default')
    user_text = user_input.strip().lower()

    # مرحلة البداية: التقاط الدالة وتحليلها
    if session_id not in session_state:
        expr_str = extract_expr(user_text)
        if not expr_str:
            return respond("Merci d’écrire la fonction sous la forme : f(x) = ...")
        try:
            expr = sympify(expr_str)
        except:
            return respond("Je n’ai pas pu comprendre la fonction. Essaie encore.")

        steps = []

        # جذور مربعة
        for r in expr.atoms(sqrt):
            arg = str(r.args[0])
            steps.append(("racine", arg))

        # لوغاريتمات
        for l in expr.atoms(log):
            arg = str(l.args[0])
            steps.append(("log", arg))

        # المقام
        denom = expr.as_numer_denom()[1]
        if denom != 1:
            steps.append(("denominateur", str(denom)))

        if not steps:
            return respond("La fonction est définie partout : D = ℝ")

        session_state[session_id] = {
            "expr": expr_str,
            "steps": steps,
            "current": 0
        }

        type_, arg = steps[0]
        return respond(first_question(type_, arg))

    # متابعة السيناريو
    state = session_state[session_id]
    current = state["current"]
    steps = state["steps"]

    # انتظار إجابة التلميذ
    if current < len(steps):
        type_, arg = steps[current]
        response = feedback_for(type_, arg, user_text)

        state["current"] += 1
        if state["current"] < len(steps):
            next_type, next_arg = steps[state["current"]]
            response += "\n\nEnsuite : " + first_question(next_type, next_arg)
        else:
            response += "\n\nBravo ! Tu peux maintenant écrire une nouvelle fonction si tu veux."
            session_state.pop(session_id)

        return respond(response)

    return respond("Reformule ta question ou propose une autre fonction.")

def extract_expr(text):
    match = re.search(r"f\(x\)\s*=\s*(.+)", text)
    return match.group(1) if match else None

def first_question(type_, arg):
    if type_ == "racine":
        return f"Quelle condition doit vérifier {arg} pour que la racine √({arg}) soit définie ?"
    elif type_ == "log":
        return f"Que doit-on imposer à {arg} pour que log({arg}) soit défini ?"
    elif type_ == "denominateur":
        return f"Que faut-il éviter avec le dénominateur {arg} pour que la fonction soit définie ?"
    else:
        return "Analysons cette fonction."

def feedback_for(type_, arg, user_input):
    if type_ == "racine":
        return f"Parfait. Pour que √({arg}) soit défini, il faut que {arg} ≥ 0."
    elif type_ == "log":
        return f"Exact. Pour que log({arg}) soit défini, on doit avoir {arg} > 0."
    elif type_ == "denominateur":
        return f"Bien vu. Il faut que {arg} ≠ 0 pour éviter une division par zéro."
    else:
        return "Bonne réponse."

def respond(text):
    return jsonify({"fulfillmentText": text})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
