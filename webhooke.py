from flask import Flask, request, jsonify
from openai import OpenAI
import os

# إنشاء عميل OpenAI مع مفتاح API من المتغير البيئي
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    user_input = req.get('queryResult', {}).get('queryText', '')

    # إرسال الرسالة إلى GPT
    gpt_reply = ask_gpt(user_input)
    return jsonify({'fulfillmentText': gpt_reply})

def ask_gpt(message):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu es un assistant pédagogique en mathématiques. "
                    "Tu aides l'élève à déterminer le domaine de définition d'une fonction, "
                    "en posant des questions étape par étape, et en expliquant chaque notion au besoin."
                )
            },
            {"role": "user", "content": f"Aide-moi à analyser la fonction suivante : {message}"}
        ]
    )
    return response.choices[0].message.content

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
