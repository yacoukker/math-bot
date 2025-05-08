from flask import Flask, request, jsonify
import os
import re
from sympy import symbols, sympify, sqrt

app = Flask(__name__)
x = symbols('x')

# تتبع حالة المحادثة
sessions = {}

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '')
    session = req.get('session', 'default')
    user_text = user_input.lower().strip()

    if session not in sessions:
        expr = extract_expr(user_text)
        if not expr:
            return respond("Peux-tu écrire une fonction comme : f(x) = √(x + 3) ?")
        try:
            parsed = sympify(expr)
        except:
            return respond("Je ne comprends pas cette fonction. Essaie encore.")

        if not parsed.has(sqrt):
            return respond("Cette fonction ne contient pas de racine carrée. Je ne gère pour l’instant que les fonctions avec √.")

        racines = [r.args[0] for r in parsed.atoms(sqrt)]
        sessions[session] = {
            "step": 1,
            "racine": racines[0]
        }
        return respond("Commençons l'analyse de ta fonction.\nQuelle est l'expression à l'intérieur de la racine carrée ?")

    state = sessions[session]
    racine = str(state['racine'])

    if state["step"] == 1:
        if racine in user_text or user_text.replace(" ", "") == racine.replace(" ", ""):
            state["step"] = 2
            return respond(f"Très bien ! Quelle condition doit vérifier l'expression {racine} pour que la racine soit définie ?")
        else:
            return respond("Essaie de me donner exactement ce qu’il y a sous la racine.")

    if state["step"] == 2:
        if "≥" in user_text or ">=" in user_text:
            state["step"] = 3
            return respond("Parfait. Peux-tu isoler x dans cette inéquation ?")
        else:
            return respond("Essaie d’exprimer la condition comme une inéquation (par exemple : x + 3 ≥ 0).")

    if state["step"] == 3:
        if "x" in user_text and ("≥" in user_text or ">=" in user_text):
            state["step"] = 4
            return respond("Très bien ! Peux-tu maintenant me donner le domaine de définition ?")
        else:
            return respond("Essaie d’isoler x, par exemple : x ≥ -3.")

    if state["step"] == 4:
        if "d" in user_text and "[" in user_text:
            sessions.pop(session)
            return respond("Bravo ! Tu as bien déterminé le domaine.\nSouhaites-tu analyser une autre fonction ?")
        else:
            return respond("Essaie de donner le domaine avec une notation comme : D = [-3, +∞[.")

    return respond("Je n’ai pas compris. Peux-tu reformuler ?")

def extract_expr(text):
    match = re.search(r"f\(x\)\s*=\s*(.*)", text)
    return match.group(1) if match else None

def respond(text):
    return jsonify({'fulfillmentText': text})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
