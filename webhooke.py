from flask import Flask, request, jsonify
from sympy import symbols, sqrt, log, sympify
import re

app = Flask(__name__)
x = symbols('x')  # المتغير الرئيسي في الدوال

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    user_input = data['queryResult']['queryText']  # النص الذي أرسله التلميذ

    # محاولة استخراج الدالة من النص
    match = re.search(r"f\(x\)\s*=\s*(.*)", user_input)
    if match:
        expr_str = match.group(1)
        try:
            expr = sympify(expr_str)
            conditions = []

            # الجذر: يجب أن يكون ما تحت الجذر ≥ 0
            if expr.has(sqrt):
                for r in expr.atoms(sqrt):
                    arg = r.args[0]
                    conditions.append(f"{arg} ≥ 0")

            # اللوغاريتم: يجب أن يكون ما داخل log > 0
            if expr.has(log):
                for r in expr.atoms(log):
                    arg = r.args[0]
                    conditions.append(f"{arg} > 0")

            # المقام: يجب أن لا يساوي صفر
            denom = expr.as_numer_denom()[1]
            if denom != 1:
                conditions.append(f"{denom} ≠ 0")

            if conditions:
                message = "لنبدأ بتحليل الدالة.\nما رأيك في الشروط التالية؟\n- " + "\n- ".join(conditions)
            else:
                message = "لا توجد جذور أو مقامات أو لوغاريتمات، إذن المجال هو R."

        except Exception:
            message = "عذرًا، لم أتمكن من فهم الدالة. حاول كتابتها بشكل أبسط مثل: f(x)=1/sqrt(x-2)"
    else:
        message = "يرجى كتابة الدالة بهذا الشكل: f(x) = ..."

    return jsonify({'fulfillmentText': message})

if __name__ == '__main__':
    app.run(port=5000, debug=True)
