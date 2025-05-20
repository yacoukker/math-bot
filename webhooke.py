from flask import Flask, request, jsonify
from sympy import symbols, solveset, S, Eq
from sympy.parsing.sympy_parser import parse_expr
from sympy.sets.sets import Set
import re, os

app = Flask(__name__)

# Déclaration de la variable utilisée dans les expressions mathématiques
x = symbols('x')

# Dictionnaire pour stocker les sessions utilisateur
sessions = {}

# Fonction pour convertir un ensemble Sympy en une notation d'intervalle en français
# Exemple : Interval.open(-∞, 3) -> ]-∞,3[
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

# Analyse et conversion de la réponse de l'élève en une expression Sympy
def parse_student_set(reply):
    try:
        r = reply.replace(' ', '').replace('∞', 'oo')
        r = r.replace('][', '] ∪ [').replace('U', ' ∪ ')
        return parse_expr(r, evaluate=False)
    except:
        return None

# Prétraitement de l'expression : conversion des puissances et insertion des multiplications manquantes
def preprocess(expr):
    expr = expr.replace('^', '**')
    expr = re.sub(r'(?<=\d)(?=[a-zA-Z\(])', '*', expr)
    expr = re.sub(r'(?<=[a-zA-Z\)])(?=\d|\()', '*', expr)
    return expr

# Analyse de l'expression pour extraire les conditions de définition
def analyse_expr(expr):
    comps = []
    # Racines carrées -> condition : argument >= 0
    for arg in re.findall(r'sqrt\((.*?)\)', expr):
        arg_p = preprocess(arg)
        cond = solveset(parse_expr(arg_p) >= 0, x, domain=S.Reals)
        comps.append({'type':'racine','arg':arg,'cond_set':cond})
    # Logarithmes -> condition : argument > 0
    for arg in re.findall(r'log\((.*?)\)', expr):
        arg_p = preprocess(arg)
        cond = solveset(parse_expr(arg_p) > 0, x, domain=S.Reals)
        comps.append({'type':'log','arg':arg,'cond_set':cond})
    # Dénominateurs -> condition : dénominateur ≠ 0
    if '/' in expr:
        denom = expr.split('/')[-1]
        denom_p = preprocess(denom)
        zeros = solveset(Eq(parse_expr(denom_p), 0), x, domain=S.Reals)
        cond = S.Reals - zeros
        comps.append({'type':'denom','arg':denom,'cond_set':cond})
    return comps

@app.route('/webhook', methods=['POST'])
def webhook():
    req = request.get_json()
    text = req.get('queryResult', {}).get('queryText', '').strip()
    sess = req.get('session', 'default')

    # Réinitialisation de la session
    if text.lower().startswith('/reset'):
        sessions.pop(sess, None)
        return respond("Session réinitialisée. Envoyez f(x)=... pour recommencer.")
    # Nouvelle fonction f(x)=...
    if 'f(x)' in text and '=' in text:
        sessions.pop(sess, None)

    state = sessions.get(sess)

    # Démarrage de la session
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
        return respond(f"Très bien, commençons. Quelle est la condition sur {step['arg']} pour qu'il soit défini ?")

    # Récupération de l'état de session
    state = sessions[sess]
    idx = state['idx']
    comp = state['comps'][idx]
    cond = comp['cond_set']
    french_cond = to_french_interval(cond)

    # Vérification de la réponse finale sur le domaine
    if state.get('ask_domain'):
        student = parse_student_set(text)
        domain = state['conds'][0]
        for c in state['conds'][1:]:
            domain = domain.intersect(c)
        correct = to_french_interval(domain)
        sessions.pop(sess)
        if student and student == domain:
            return respond("Bravo ! Vous avez trouvé le domaine de définition.")
        else:
            return respond(f"Ce n'est pas correct. Le domaine de définition est {correct}.")

    # Étape 0 : poser la condition de définition
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

    # Étape 1 : validation de la solution de l'élève
    student = parse_student_set(text)
    try:
        if student:
            student_set = solveset(student, x, domain=S.Reals) if not isinstance(student, Set) else student
            if student_set == cond:
                reply = "Très bien, c'est correct."
            else:
                reply = f"Ce n'est pas correct. La solution est {french_cond}."
        else:
            reply = f"Ce n'est pas correct. La solution est {french_cond}."
    except Exception:
        reply = f"Erreur dans l'analyse de votre réponse. La solution correcte est {french_cond}."

    # Passer à l'élément suivant ou demander le domaine
    state['conds'].append(cond)
    state['idx']+=1
    state['substep']=0
    if state['idx']<len(state['comps']):
        nxt=state['comps'][state['idx']]
        return respond(f"{reply}\nProchaine condition : sur {nxt['arg']}, quelle est la condition pour qu'il soit défini ?")

    # Demande finale de la part de l'élève
    state['ask_domain']=True
    return respond(f"{reply}\nMaintenant, donnez le domaine de définition de f(x).")

# Fonction utilitaire pour envoyer la réponse à Dialogflow
def respond(txt):
    return jsonify({'fulfillmentText':txt})

# Lancement du serveur Flask
if __name__=='__main__':
    port=int(os.environ.get('PORT',10000))
    app.run(host='0.0.0.0',port=port)
