from flask import Flask, request, jsonify
from sympy import symbols, solveset, S, Eq
from sympy.parsing.sympy_parser import parse_expr
import re, os

app = Flask(__name__)

# Définir le symbole
x = symbols('x')

# Stockage des sessions
sessions = {}

# Convertir ensemble Sympy en notation intervalle français
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

# Parser réponse élève en ensemble Sympy
def parse_student_set(reply):
    try:
        r = reply.replace(' ', '').replace('∞', 'oo')
        r = r.replace('][', '] ∪ [').replace('U', ' ∪ ')
        return parse_expr(r, evaluate=False)
    except:
        return None

# Prétraitement: ^ -> **, multiplication implicite
def preprocess(expr):
    expr = expr.replace('^', '**')
    expr = re.sub(r'(?<=\d)(?=[a-zA-Z\(])', '*', expr)
    expr = re.sub(r'(?<=[a-zA-Z\)])(?=\d|\()', '*', expr)
    return expr

# Analyse expression pour conditions de définition
def analyse_expr(expr):
    comps = []
    # racine carrée
    for arg in re.findall(r'sqrt\((.*?)\)', expr):
        arg_p = preprocess(arg)
        cond = solveset(parse_expr(arg_p) >= 0, x, domain=S.Reals)
        comps.append({'type':'racine','arg':arg,'cond_set':cond})
    # logarithme
    for arg in re.findall(r'log\((.*?)\)', expr):
        arg_p = preprocess(arg)
        cond = solveset(parse_expr(arg_p) > 0, x, domain=S.Reals)
        comps.append({'type':'log','arg':arg,'cond_set':cond})
    # dénominateur
    if '/' in expr:
        denom = expr.split('/')[-1]
        denom_p = preprocess(denom)
        # trouver les zéros du dénominateur
        zeros = solveset(Eq(parse_expr(denom_p), 0), x, domain=S.Reals)
        cond = S.Reals - zeros
        comps.append({'type':'denom','arg':denom,'cond_set':cond})
    return comps

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    text = req.get('queryResult', {}).get('queryText', '').strip()
    sess = req.get('session', 'default')

    # reset
    if text.lower().startswith('/reset'):
        sessions.pop(sess, None)
        return respond("Session réinitialisée. Envoyez f(x)=... pour recommencer.")
    # nouvelle fonction
    if 'f(x)' in text and '=' in text:
        sessions.pop(sess, None)

    state = sessions.get(sess)
    if not state:
        m = re.search(r'f\(x\)=\s*(.+)', text)
        if not m:
            return respond("Écrivez la fonction sous la forme f(x)=... pour commencer.")
        raw = m.group(1)
        raw = re.sub(r'√\s*\((.*?)\)', r'sqrt(\1)', raw)
        raw = preprocess(raw)
        comps = analyse_expr(raw)
        sessions[sess] = {'comps':comps,'idx':0,'substep':0,'conds':[],'ask_domain':False}
        step = comps[0]
        return respond(f"Très bien, commençons. Quel est la condition sur {step['arg']} pour qu'il soit défini ?")

    state = sessions[sess]
    idx = state['idx']
    comp = state['comps'][idx]
    cond = comp['cond_set']
    french_cond = to_french_interval(cond)

    # Vérification domaine final
    if state['ask_domain']:
        student = parse_student_set(text)
        domain = state['conds'][0]
        for c in state['conds'][1:]: domain = domain.intersect(c)
        correct = to_french_interval(domain)
        sessions.pop(sess)
        if student and student == domain:
            return respond("Bravo ! Vous avez trouvé le domaine de définition.")
        else:
            return respond(f"Ce n'est pas correct. Le domaine de définition est {correct}.")

    # étape 0: poser condition
    if state['substep']==0:
        if re.search(r'\bnon\b', text.lower()) or 'je ne sais pas' in text.lower():
            msg = (f"D'accord. Pour que {comp['type']} soit défini, "
                   + ("l'expression sous la racine ≥ 0" if comp['type']=='racine' else
                      "l'argument du log > 0" if comp['type']=='log' else
                      "le dénominateur ≠ 0")
                   + f"; ici {french_cond}.")
            return respond(f"{msg} Maintenant, résolvez cette condition et donnez votre solution.")
        state['substep']=1
        return respond(f"Parfait. Résolvez {comp['arg']} {'≥ 0' if comp['type']=='racine' else '> 0' if comp['type']=='log' else '≠ 0'} et indiquez votre solution.")

    # étape 1: valider solution
    student = parse_student_set(text)
    state['conds'].append(cond)
    if student and student == cond:
        reply="Très bien, c'est correct."
    else:
        reply=f"Ce n'est pas correct. La solution est {french_cond}."

    # avancer ou demander domaine
    state['idx']+=1
    state['substep']=0
    if state['idx']<len(state['comps']):
        nxt=state['comps'][state['idx']]
        return respond(f"{reply}\nProchaine condition : sur {nxt['arg']}, quelle est la condition pour qu'il soit défini ?")

    state['ask_domain']=True
    return respond(f"{reply}\nMaintenant, donnez le domaine de définition de f(x).")

# helper

def respond(txt):
    return jsonify({'fulfillmentText':txt})

if __name__=='__main__':
    port=int(os.environ.get('PORT',10000))
    app.run(host='0.0.0.0',port=port)
