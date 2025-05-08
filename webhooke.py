from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# نموذج مجاني على Hugging Face (أفضل من flan-t5)
HUGGINGFACE_API_URL = "https://api-inference.huggingface.co/models/tiiuae/falcon-7b-instruct"

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '')

    # إرسال السؤال إلى النموذج المجاني
    result = ask_huggingface(f"Aide-moi à trouver le domaine de définition de la fonction suivante : {user_input}")
    return jsonify({'fulfillmentText': result})

def ask_huggingface(prompt):
    payload = {"inputs": prompt}
    headers = {"Accept": "application/json"}  # بدون token، للاستخدام المجاني
    response = requests.post(HUGGINGFACE_API_URL, headers=headers, json=payload)

    if response.status_code == 200:
        result = response.json()
        if isinstance(result, list) and 'generated_text' in result[0]:
            return result[0]['generated_text']
        elif isinstance(result, dict) and 'generated_text' in result:
            return result['generated_text']
        else:
            return "Je n’ai pas pu interpréter la réponse du modèle."
    else:
        return "Le service Hugging Face est temporairement indisponible. Réessaie dans un moment."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
