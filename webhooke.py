from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

HUGGINGFACE_API_URL = "https://api-inference.huggingface.co/models/google/flan-t5-large"

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '')

    # أرسل الدالة إلى نموذج مجاني من Hugging Face
    result = ask_huggingface(f"Aide-moi à trouver le domaine de définition de : {user_input}")
    return jsonify({'fulfillmentText': result})

def ask_huggingface(prompt):
    payload = {"inputs": prompt}
    response = requests.post(HUGGINGFACE_API_URL, json=payload)

    if response.status_code == 200:
        result = response.json()
        if isinstance(result, list) and 'generated_text' in result[0]:
            return result[0]['generated_text']
        else:
            return "Je n’ai pas pu comprendre la réponse."
    else:
        return "Le service Hugging Face est temporairement indisponible."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
