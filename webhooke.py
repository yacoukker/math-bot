from flask import Flask, request, jsonify
from sympy import symbols, Interval, Union, S, Eq, solveset, simplify
import re, os

app = Flask(__name__)
x = symbols("x")
session_state = {}

@app.route("/webhook", methods=["POST"])
def webhook():
    print("[Webhook ACTIVÉ] une requête a été reçue.")
    req = request.get_json()
    user_input = req.get("queryResult", {}).get("queryText", "").strip().lower()
    print("Entrée reçue:", user_input)

    session_id = req.get("session", "default")

    if "f(x)=" in user_input:
        session_state.pop(session_id, None)

    if "reset" in user_input and len(user_input) <= 20:
        session_state.pop(session_id, None)
        return respond("Très bien ! Reprenons depuis le début. Envoie-moi une nouvelle fonction sous la forme : f(x) = ...")

    if session_id not in session_state:
        expr = extract_expr(user_input)
        if not expr:
            return respond("Écris la fonction sous la forme : f(x) = ...")
        components = analyse_expression(expr)
        if not components:
            return respond("La fonction est définie sur ℝ : aucun log, racine ni dénominateur détecté.")
        session_state[session_id] = {
            "expr": expr,
            "steps": components,
            "current": 0,
            "mode": "condition",
            "conditions": [],
            "attente_finale": False,
        }
        current_type, arg = components[0]
        return respond(f"Commençons. Quelle est la condition sur {component_label(current_type)} {arg} pour qu’il soit défini ?")

    state = session_state[session_id]

    if state.get("attente_finale"):
        if any(token in user_input for token in ["[", "]", "(", ")", "oo", "∞", "x", "≥", ">", "reel", "r"]):
            correct, bonne_reponse = is_domain_correct_math(user_input, state["conditions"])
            session_state.pop(session_id)
            if correct:
                return respond("Bravo ! Tu as correctement trouvé l'ensemble de définition.")
            else:
                return respond(f"Ce n’est pas tout à fait correct. L’ensemble de définition est : D = {bonne_reponse}\nNe t’inquiète pas, tu peux y arriver avec un peu de pratique !")
        else:
            return respond("Essaie de donner l’ensemble sous forme d’un intervalle, par exemple : ]2,+∞[ ou ℝ.")

    current_type, arg = state["steps"][state["current"]]
    condition = expected_condition(current_type, arg)
    solution = expected_solution_set(current_type, arg)

    if state["mode"] == "condition":
        if match_condition(user_input, current_type, arg):
            state["mode"] = "solution"
            return respond(f"Parfait ! Résous maintenant cette inéquation : {condition}")
        else:
            state["mode"] = "solution"
            explication = error_explanation(current_type, arg, condition)
            return respond(f"{explication}\nPeux-tu résoudre maintenant cette inéquation : {condition} ?")

    elif state["mode"] == "solution":
        if match_solution(user_input, solution):
            state["conditions"].append(solution)
            return next_step(state, session_id, "Bien joué !")
        else:
            state["conditions"].append(solution)
            return next_step(state, session_id, f"Ce n’est pas tout à fait ça. En réalité, la solution est : {convert_to_logical_notation(solution)}")

def next_step(state, session_id, message):
    state["current"] += 1
    state["mode"] = "condition"
    if state["current"] < len(state["steps"]):
        next_type, next_arg = state["steps"][state["current"]]
        return respond(message + f"\n\nPassons à {component_label(next_type)}. Quelle est la condition sur {next_arg} pour qu’il soit défini ?")
    else:
        state["attente_finale"] = True
        conditions_text = "\n".join([convert_to_logical_notation(c) for c in state["conditions"]])
        return respond(message + "\n\nVoici les conditions obtenues sur x :\n" + conditions_text + "\nPeux-tu en déduire maintenant l’ensemble de définition D ?")

# === Fonctions auxiliaires ===

def extract_expr(text):
    match = re.search(r"f\(x\)\s*=\s*(.+)", text)
    if not match:
        return None
    expr_raw = match.group(1)
    return re.sub(r"√\s*\((.*?)\)", r"sqrt(\1)", expr_raw)

def analyse_expression(expr):
    components = []
    components += [("racine", arg) for arg in re.findall(r"sqrt\((.*?)\)", expr)]
    components += [("log", arg) for arg in re.findall(r"log\((.*?)\)", expr)]
    if "/" in expr:
        denom = expr.split("/")[-1]
        components.append(("denominateur", denom.strip()))
    return components

def component_label(type_):
    return {"racine": "√", "log": "log", "denominateur": "le dénominateur"}.get(type_, "cette expression")

def expected_condition(type_, arg):
    if type_ == "racine":
        return f"{arg} ≥ 0"
    elif type_ == "log":
        return f"{arg} > 0"
    elif type_ == "denominateur":
        return f"{arg} ≠ 0"
    return ""

def expected_solution_set(type_, arg):
    from sympy.parsing.sympy_parser import parse_expr
    expr = parse_expr(arg.replace("^", "**"))
    if type_ == "racine":
        return solveset(expr >= 0, x, domain=S.Reals)
    elif type_ == "log":
        return solveset(expr > 0, x, domain=S.Reals)
    elif type_ == "denominateur":
        return S.Reals - solveset(Eq(expr, 0), x, domain=S.Reals)
    return S.Reals

def match_condition(reply, type_, arg):
    reply = reply.replace(" ", "").replace(">=", "≥").replace("!=", "≠")
    patterns = {
        "racine": ["≥0", "positif", "nonnégatif", f"{arg}≥0"],
        "log": [">0", "strictementpositif", f"{arg}>0"],
        "denominateur": ["≠0", "différent", "nonnul", f"{arg}≠0"],
    }
    return any(p in reply for p in patterns.get(type_, []))

def match_solution(reply, attendu_set):
    try:
        student_set = parse_logical_expression(reply)
        return student_set.equals(attendu_set)
    except Exception as e:
        print("Erreur de comparaison:", e)
        return False

def parse_logical_expression(expr):
    # تنظيف أولي
    expr = expr.replace(" ", "").replace("ou", "||").replace("et", "&&") \
               .replace("≥", ">=").replace("≤", "<=") \
               .replace("−", "-").replace("÷", "/")

    # تفكيك حسب "ou"
    parts = expr.split("||")
    intervals = []

    for part in parts:
        if ">=" in part:
            _, val = part.split(">=")
            intervals.append(Interval(float(val), float("inf"), left_closed=True))
        elif "<=" in part:
            _, val = part.split("<=")
            intervals.append(Interval(float("-inf"), float(val), right_closed=True))
        elif ">" in part:
            _, val = part.split(">")
            intervals.append(Interval.open(float(val), float("inf")))
        elif "<" in part:
            _, val = part.split("<")
            intervals.append(Interval.open(float("-inf"), float(val)))
        elif "!=" in part or "≠" in part:
            val = part.split("≠")[-1] if "≠" in part else part.split("!=")[-1]
            a = float(val)
            intervals.append(Union(
                Interval.open(float("-inf"), a),
                Interval.open(a, float("inf"))
            ))

    if len(intervals) == 1:
        return intervals[0]
    return Union(*intervals)


def convert_to_logical_notation(interval):
    def single_condition(i):
        if isinstance(i, Interval):
            parts = []
            if i.start != S.NegativeInfinity:
                op = ">" if i.left_open else "≥"
                parts.append(f"x {op} {i.start}")
            if i.end != S.Infinity:
                op = "<" if i.right_open else "≤"
                parts.append(f"x {op} {i.end}")
            return " et ".join(parts)
        return str(i)
    if isinstance(interval, Union):
        return " ou ".join(single_condition(i) for i in interval.args)
    return single_condition(interval)

def is_domain_correct_math(reply, conditions):
    # تحويل كل الشروط إلى مجموعات (Intervals/Unions)
    sets = [c if isinstance(c, (Interval, Union)) else parse_logical_expression(c) for c in conditions]
    correct_domain = sets[0]
    for s in sets[1:]:
        correct_domain = correct_domain.intersect(s)

    # تحويل جواب التلميذ
    student_set = parse_student_domain(reply)
    correct_str = convert_to_interval_notation(correct_domain)

    if student_set is None:
        return False, correct_str

    # ✅ معالجة حالة S.Reals بشكل خاص
    try:
        if student_set == correct_domain:
            return True, correct_str
        elif hasattr(student_set, "equals") and student_set.equals(correct_domain):
            return True, correct_str
    except Exception as e:
        print("Erreur comparaison ensemble:", e)

    return False, correct_str


def parse_student_domain(reply):
    try:
        reply = reply.lower().replace(" ", "")
        reply = reply.replace("∞", "oo").replace("+oo", "oo").replace("−", "-")
        reply = reply.replace("d=", "").replace("d:", "").replace("=", "")
        reply = reply.replace("∪", "u")

        # ℝ ou reel
        if reply in ["r", "ℝ", "reel"]:
            return S.Reals

        # division en cas d'union
        parts = re.split(r"u", reply)
        intervals = []

        for part in parts:
            match = re.match(r"([\[\]])(-?oo|[-+]?\d+)[,;]([-+]?\d+|oo)([\[\]])", part)
            if match:
                left_bracket, a, b, right_bracket = match.groups()
                a = float("-inf") if "oo" in a else float(a)
                b = float("inf") if "oo" in b else float(b)
                left_open = left_bracket == "]"
                right_open = right_bracket == "["
                intervals.append(Interval(a, b, left_open=left_open, right_open=right_open))

        if len(intervals) == 1:
            return intervals[0]
        elif len(intervals) >= 2:
            return Union(*intervals)

    except Exception as e:
        print("Erreur dans parse_student_domain:", e)
        return None

    return None


def convert_to_interval_notation(interval):
    if isinstance(interval, Interval):
        a = "-∞" if interval.start == S.NegativeInfinity else str(interval.start)
        b = "+∞" if interval.end == S.Infinity else str(interval.end)
        left = "]" if interval.left_open else "["
        right = "[" if not interval.right_open else "["
        return f"{left}{a}, {b}{right}"
    elif isinstance(interval, Union):
        return " ∪ ".join([convert_to_interval_notation(i) for i in interval.args])
    return str(interval)

def respond(text):
    return jsonify({"fulfillmentText": text})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
