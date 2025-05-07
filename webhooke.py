from flask import Flask, request, jsonify
import spacy
import os

app = Flask(__name__)

# تحميل نموذج spaCy الفرنسي
try:
    nlp = spacy.load("fr_core_news_sm")
except:
    from spacy.cli import download
    download("fr_core_news_sm")
    nlp = spacy.load("fr_core_news_sm")

# تتبع حالة المحادثة لكل session
conversation_state = {}

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '')
    session = req.get('session', 'default')
    user_text = user_input.lower()

    # تحليل النص باستخدام spaCy
    doc = nlp(user_text)
    tokens = [token.text.lower() for token in doc]
    text_str = ' '.join(tokens)

    # تحديد المرحلة الحالية
    if session not in conversation_state or "f(x)" in user_text:
        conversation_state[session] = 'analyse'
        return respond("Commençons par analyser cette fonction étape par étape.\nQuel est l'expression à l'intérieur de la racine carrée ?")


    step = conversation_state[session]

    # === Étape 1: début ===
    if step == 'analyse':
        conversation_state[session] = 'racine'
        return respond("Commençons par analyser cette fonction étape par étape.\nQuel est l'expression à l'intérieur de la racine carrée ?")

    # === Étape 2: réponse sur le contenu de la racine ===
    elif step == 'racine':
        if 'x' in tokens and ('-2' in tokens or 'moins' in tokens or 'deux' in tokens):
            conversation_state[session] = 'condition_racine'
            return respond("Parfait ! Et quelle condition doit remplir une racine carrée pour que l'expression soit définie ?")
        else:
            return respond("Réessaie. Quelle est l'expression exacte sous la racine ?")

    # === Étape 3: condition de la racine carrée ===
    elif step == 'condition_racine':
        motifs = ['plus grand', 'supérieur', 'x >', 'x ≥', 'x >=', 'x supérieur à']
        if any(m in text_str for m in motifs) or '≥' in user_text or '>=' in user_text:
            conversation_state[session] = 'denominateur'
            return respond("Très bien, donc x ≥ 2.\nMaintenant, cette racine est dans un dénominateur. Qu'est-ce qu'on doit éviter ?")
        else:
            return respond("Essaie d'exprimer la condition pour que la racine carrée soit définie.")

    # === Étape 4: condition du dénominateur ===
    elif step == 'denominateur':
        if '≠' in user_text or 'différent de' in user_text or 'x ≠ 2' in user_text or 'pas égal' in user_text:
            conversation_state[session] = 'conclusion'
            return respond("Exactement ! Alors, quelle est l'ensemble des valeurs de x qui vérifient toutes ces conditions ?")
        else:
            return respond("On cherche à éviter que le dénominateur soit nul. Que doit-on faire ?")

    # === Étape 5: conclusion finale ===
    elif step == 'conclusion':
        if ']2, +∞[' in user_text or 'x > 2' in user_text or 'supérieur à 2' in text_str:
            conversation_state.pop(session)
            return respond("Parfait ! Le domaine de définition de f est D = ]2, +∞[\nSouhaites-tu essayer une autre fonction ?")
        else:
            return respond("Essaie d'exprimer le domaine de définition avec une bonne notation.")

    return respond("Je n'ai pas compris. Peux-tu reformuler ?")

def respond(text):
    return jsonify({'fulfillmentText': text})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
