from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# نموذج مجاني مستقر على Hugging Face
HUGGINGFACE_API_URL = "https://api-inference.huggingface.co/models/tiiuae/falcon-7b-instruct"

# ✅ المفتاح يُؤخذ من متغير بيئي وليس داخل الكود
HUGGINGFACE_TOKEN = os.getenv("HF_TOKEN")

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '')

    # إرسال الطلب إلى نموذج الذكاء الاصطناعي
    result = ask_huggingface(f"Aide-moi à trouver le domaine de définition de la fonction suivante : {user_input}")
    return jsonify({'fulfillmentText': result})

def ask_huggingface(prompt):
    payload = {"inputs": prompt}
    headers = {
        "Authorization": HUGGINGFACE_TOKEN,
        "Accept": "application/json"
    }
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
