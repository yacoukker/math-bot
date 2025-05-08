from flask import Flask, request, jsonify
from sympy import symbols, sympify, sqrt, log, S
import os
import re

app = Flask(__name__)
x = symbols('x')

# لتتبع حالة المحادثة حسب session
session_states = {}

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_text = req.get('queryResult', {}).get('queryText', '')
    session = req.get('session', 'default')

    # إذا لم تكن هناك حالة بعد، نبدأ بتحليل الدالة
    if session not in session_states:
        expr = extract_expression(user_text)
        if expr is None:
            return respond("Je n'ai pas compris la fonction. Peux-tu écrire quelque chose comme : f(x) = 1 / √(x - 2) ?")
        try:
            parsed_expr = sympify(expr)
        except:
            return respond("Désolé, je n'arrive pas à comprendre cette fonction.")

        # استخراج المكونات المهمة
        steps = []
        if parsed_expr.has(sqrt):
            for r in parsed_expr.atoms(sqrt):
                condition = f"{r.args[0]} ≥ 0"
                steps.append(("racine", condition))
        if parsed_expr.has(log):
            for r in parsed_expr.atoms(log):
                condition = f"{r.args[0]} > 0"
                steps.append(("log", condition))
        denom = parsed_expr.as_numer_denom()[1]
        if denom != 1:
            steps.append(("denominateur", f"{denom} ≠ 0"))

        if not steps:
            return respond("La fonction est définie partout. Le domaine est ℝ.")

        session_states[session] = {
            "expr": expr,
            "steps": steps,
            "current": 0
        }
        return respond(f"Commençons l'analyse de f(x) = {expr}.\nPremière question : Que doit-on vérifier pour que {steps[0][1].split()[0]} soit valide ?")

    # مرحلة الحوار التفاعلي
    state = session_states[session]
    current_step = state["steps"][state["current"]]
    state["current"] += 1

    # إذا انتهت كل الشروط
    if state["current"] >= len(state["steps"]):
        session_states.pop(session)
        return respond("Très bien ! On a fini l'analyse. Tu peux maintenant proposer une autre fonction si tu veux.")

    # سؤال المرحلة التالية
    next_step = state["steps"][state["current"]]
    return respond(f"Parfait. Ensuite : Que doit-on vérifier pour que {next_step[1].split()[0]} soit valide ?")

def extract_expression(text):
    match = re.search(r"f\(x\)\s*=\s*(.*)", text)
    return match.group(1) if match else None

def respond(text):
    return jsonify({"fulfillmentText": text})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
