from flask import Flask, request, jsonify

app = Flask(__name__)

# يمكننا لاحقًا استبداله بـ session ID من Dialogflow إذا أردنا تتبع عدة مستخدمين
conversation_state = {}

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '')
    session = req.get('session', 'default')  # لتتبع المستخدم

    # إذا لم يتم تحديد مرحلة بعد
    if session not in conversation_state:
        conversation_state[session] = 'analyse'

    current_step = conversation_state[session]

    # === Étape 1: lancement de l'analyse ===
    if current_step == 'analyse':
        conversation_state[session] = 'racine'
        return respond("Commençons par analyser cette fonction étape par étape.\nQuel est l'expression à l'intérieur de la racine carrée ?")

    # === Étape 2: vérifier condition racine ===
    elif current_step == 'racine':
        if 'x - 2' in user_input or 'x-2' in user_input:
            conversation_state[session] = 'condition_racine'
            return respond("Parfait ! Et quelle condition doit remplir une racine carrée pour que l'expression soit définie ?")
        else:
            return respond("Réessaie. Quelle est l'expression exacte sous la racine ?")

    # === Étape 3: condition racine ===
    elif current_step == 'condition_racine':
        if '≥' in user_input or '>=' in user_input:
            conversation_state[session] = 'denominateur'
            return respond("Très bien, donc x ≥ 2.\nMaintenant, cette racine est dans un dénominateur. Qu'est-ce qu'on doit éviter ?")
        else:
            return respond("Essaie d'exprimer la condition pour que la racine carrée soit définie.")

    # === Étape 4: condition dénominateur ===
    elif current_step == 'denominateur':
        if '≠ 0' in user_input or '=/= 0' in user_input or 'x ≠ 2' in user_input:
            conversation_state[session] = 'conclusion'
            return respond("Exactement ! Alors, quelle est l'ensemble des valeurs de x qui vérifient toutes ces conditions ?")
        else:
            return respond("On cherche à éviter que le dénominateur soit nul. Que doit-on faire ?")

    # === Étape 5: conclusion ===
    elif current_step == 'conclusion':
        if ']2, +∞[' in user_input or '2 < x' in user_input:
            conversation_state.pop(session)
            return respond("Parfait ! Le domaine de définition de f est D = ]2, +∞[\nSouhaites-tu essayer une autre fonction ?")
        else:
            return respond("Essaie d'exprimer le domaine de définition avec une bonne notation.")

    # Par défaut
    return respond("Je n'ai pas compris. Peux-tu reformuler ?")

def respond(text):
    return jsonify({'fulfillmentText': text})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
