from flask import Flask, request, jsonify
from sympy import symbols, solveset, S
from sympy.parsing.sympy_parser import parse_expr
import re, os

app = Flask(__name__)

# Define symbol
x = symbols('x')

# In-memory session storage
sessions = {}

# Convert Sympy set to French interval notation
def to_french_interval(sol_set):
    from sympy import Interval, Union
    if sol_set == S.Reals:
        return 'ℝ'
    if isinstance(sol_set, Interval):
        left = '[' if not sol_set.left_open else ']'
        right = '[' if not sol_set.right_open else ']'
        start = '-∞' if sol_set.start == S.NegativeInfinity else str(sol_set.start)
        end = '+∞' if sol_set.end == S.Infinity else str(sol_set.end)
        return f"{left}{start},{end}{right}"
    if isinstance(sol_set, Union):
        return ' ∪ '.join(to_french_interval(i) for i in sol_set.args)
    return str(sol_set)

# Parse student's interval string into a Sympy set
def parse_student_set(reply):
    try:
        r = reply.replace(' ', '').replace('∞', 'oo')
        r = r.replace('][', '] ∪ [').replace('U', ' ∪ ')
        return parse_expr(r, evaluate=False)
    except Exception:
        return None

# Preprocess expression: replace ^ with ** and insert * for implicit multiplication
def preprocess(expr):
    expr = expr.replace('^', '**')
    expr = re.sub(r'(?<=\d)(?=[a-zA-Z\(])', '*', expr)
    expr = re.sub(r'(?<=[a-zA-Z\)])(?=\d|\()', '*', expr)
    return expr

# Analyze expression components for domain conditions
def analyse_expr(expr):
    comps = []
    # Square root
    for arg in re.findall(r'sqrt\((.*?)\)', expr):
        arg_p = preprocess(arg)
        cond = solveset(parse_expr(arg_p) >= 0, x, domain=S.Reals)
        comps.append({'type': 'racine', 'arg': arg, 'cond_set': cond})
    # Logarithm
    for arg in re.findall(r'log\((.*?)\)', expr):
        arg_p = preprocess(arg)
        cond = solveset(parse_expr(arg_p) > 0, x, domain=S.Reals)
        comps.append({'type': 'log', 'arg': arg, 'cond_set': cond})
    # Denominator
    if '/' in expr:
        denom = expr.split('/')[-1]
        denom_p = preprocess(denom)
        cond = solveset(parse_expr(denom_p) != 0, x, domain=S.Reals)
        comps.append({'type': 'denom', 'arg': denom, 'cond_set': cond})
    return comps

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    text = req.get('queryResult', {}).get('queryText', '').strip()
    sess = req.get('session', 'default')

    # Reset session
    if text.lower().startswith('/reset'):
        sessions.pop(sess, None)
        return respond("Session réinitialisée. Envoie une nouvelle fonction: f(x)=...")
    # New function declaration
    if 'f(x)' in text and '=' in text:
        sessions.pop(sess, None)

    state = sessions.get(sess)

    # Start new session
    if not state:
        m = re.search(r'f\(x\)\s*=\s*(.+)', text)
        if not m:
            return respond("Écris la fonction sous la forme f(x)=... pour démarrer.")
        raw = m.group(1)
        raw = re.sub(r'√\s*\((.*?)\)', r'sqrt(\1)', raw)
        raw = preprocess(raw)
        comps = analyse_expr(raw)
        sessions[sess] = {'comps': comps, 'idx': 0, 'substep': 0, 'conds': [], 'ask_domain': False}
        step = comps[0]
        return respond(f"حسناً، لنبدأ. ما هو الشرط على {step['arg']} ليكون معرفاً؟")

    # Retrieve session state
    state = sessions[sess]
    idx = state['idx']
    comps = state['comps']

    # Final domain check
    if state.get('ask_domain'):
        student = parse_student_set(text)
        domain = state['conds'][0]
        for c in state['conds'][1:]:
            domain = domain.intersect(c)
        correct = to_french_interval(domain)
        sessions.pop(sess)
        if student and student == domain:
            return respond("احسنت عمل رائع تهانينا!")
        else:
            return respond(f"لا بأس، مجموعة التعريف هي {correct}. مع قليل من التدريب ستصبح قادراً على إيجاد مجموعة التعريف بسهولة.")

    # Current component
    comp = comps[idx]
    cond = comp['cond_set']
    french_cond = to_french_interval(cond)

    # Ask or validate step
    if state['substep'] == 0:
        if re.search(r'لا\s', text) or 'لااعرف' in text.replace(' ', ''):
            msg = f"لا بأس، نذكرك أنه لكي يكون {comp['type']} معرفاً يجب أن يكون ما بداخله {'≥ 0' if comp['type']=='racine' else '> 0' if comp['type']=='log' else '≠ 0'}، وفي حالتنا يجب أن تكون {french_cond}."
            return respond(f"{msg} الآن حل المتراجحة في مسودتك وأجب بالحل الذي توصلت إليه.")
        state['substep'] = 1
        return respond(f"احسنت. الآن حل المتراجحة {comp['arg']} {'≥ 0' if comp['type']=='racine' else '> 0' if comp['type']=='log' else '≠ 0'} وأجب بالحل الذي توصلت إليه.")

    # Validate student's solution
    student = parse_student_set(text)
    state['conds'].append(cond)
    if student and student == cond:
        reply = "جيد جداً أنت في الطريق الصحيح."
    else:
        reply = f"لا بأس، حل هذه المتراجحة هو {french_cond}."

    # Advance or ask domain
    state['idx'] += 1
    state['substep'] = 0
    if state['idx'] < len(comps):
        nxt = comps[state['idx']]
        return respond(f"{reply}\nالآن ما هو الشرط على {nxt['arg']} ليكون معرفاً؟")

    # Ask for domain
    state['ask_domain'] = True
    return respond(f"{reply}\nالآن هل يمكنك التوصل إلى مجموعة التعريف؟")

# Helper to send JSON response
def respond(txt):
    return jsonify({'fulfillmentText': txt})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
