from flask import Flask, request, jsonify
import openai
import os
import re

# أدخل مفتاح API الخاص بك هنا
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '')

    # نرسل السؤال إلى GPT
    gpt_reply = ask_gpt(user_input)
    return jsonify({'fulfillmentText': gpt_reply})

def ask_gpt(message):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # مجاني مع رصيد محدود
        messages=[
            {"role": "system", "content": "Tu es un assistant pédagogique de mathématiques. Tu aides les élèves à trouver le domaine de définition d'une fonction étape par étape, en posant des questions."},
            {"role": "user", "content": f"Aide-moi à déterminer le domaine de définition de : {message}"}
        ]
    )
    return response['choices'][0]['message']['content']

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
