from flask import Flask, request, jsonify
from sympy import (
    symbols, Interval, Union, S,
    simplify, Eq, solveset, EmptySet
)
import re, os

app = Flask(__name__)
x = symbols("x")
session_state = {}


@app.route("/webhook", methods=["POST"])
def webhook():
    req = request.get_json()
    user_input = req.get("queryResult", {}).get("queryText", "").strip().lower()
    session_id = req.get("session", "default")

    # إعادة التهيئة لو أرسل التلميذ دالة جديدة
    if "f(x)=" in user_input:
        session_state.pop(session_id, None)

    # أمر /reset
    if "reset" in user_input and len(user_input) <= 20:
        session_state.pop(session_id, None)
        return respond(
            "Très bien ! Reprenons depuis le début. Envoie-moi une nouvelle fonction sous la forme : f(x) = ..."
        )

    # بداية جلسة جديدة
    if session_id not in session_state:
        expr = extract_expr(user_input)
        if not expr:
            return respond("Écris la fonction sous la forme : f(x) = ...")

        components = analyse_expression(expr)
        if not components:
            return respond(
                "La fonction est définie sur ℝ : aucun log, racine ni dénominateur détecté."
            )

        session_state[session_id] = {
            "expr": expr,
            "steps": components,
            "current": 0,
            "mode": "condition",
            "conditions": [],
            "attente_finale": False,
        }

        ctype, carg = components[0]
        return respond(
            f"Commençons. Quelle est la condition sur {component_label(ctype)} {carg} pour qu’il soit défini ?"
        )

    # الجلسة الجارية
    state = session_state[session_id]

    # مرحلة الاستنتاج النهائي للمجال
    if state["attente_finale"]:
        if any(tok in user_input for tok in ["[", "]", "oo", "∞", "x", "≥", "≤", "≠", "r"]):
            correct, bonne = is_domain_correct_math(user_input, state["conditions"])
            session_state.pop(session_id)
            if correct:
                return respond("Bravo ! Tu as correctement trouvé l'ensemble de définition.")
            else:
                return respond(
                    f"Ce n’est pas tout à fait correct. L’ensemble de définition est : D = {bonne}\n"
                    "Ne t’inquiète pas, tu peux y arriver avec un peu de pratique !"
                )
        else:
            return respond("Essaie de donner l’ensemble sous forme d’intervalle, par exemple : ]2,+∞[ ou ℝ.")

    # مرحلة الشرط / الحلّ المرحلي
    ctype, carg = state["steps"][state["current"]]
    condition = expected_condition(ctype, carg)
    solution  = expected_solution(ctype, carg)

    if state["mode"] == "condition":
        if match_condition(user_input, ctype, carg):
            state["mode"] = "solution"
            return respond(f"Parfait ! Résous maintenant : {condition}")
        else:
            state["mode"] = "solution"
            expl = error_explanation(ctype, carg, condition)
            return respond(f"{expl}\nPeux-tu résoudre maintenant ? {condition}")

    elif state["mode"] == "solution":
        sol = solution  # la chaîne retournée par expected_solution
        # si l'élève répond correctement
        if match_solution(user_input, sol):
            state["conditions"].append(sol)
            # réponse positive
            return respond(
                "Formidable ! Les conditions sur x sont :\n"
                f"• {sol}\n\n"
                "Peux-tu maintenant en déduire l’ensemble de définition D ?"
            )
        else:
            # on collecte tout de même la solution pour le récap
            state["conditions"].append(sol)
            # réponse corrective
            recap = "\n".join(f"• {c}" for c in state["conditions"])
            return respond(
                "Pas de problème. La solution de l’inéquation est :\n"
                f"{sol}\n\n"
                "Les conditions sur x sont :\n"
                f"{recap}\n\n"
                "Peux-tu maintenant en déduire l’ensemble de définition D ?"
            )



def next_step(state, session_id, msg):
    state["current"] += 1
    state["mode"] = "condition"
    if state["current"] < len(state["steps"]):
        ctype, carg = state["steps"][state["current"]]
        return respond(
            msg
            + f"\n\nPassons à {component_label(ctype)}. Quelle condition ? {expected_condition(ctype, carg)}"
        )
    else:
        state["attente_finale"] = True
        conds = "\n".join(state["conditions"])
        return respond(
            msg
            + "\n\nVoici les conditions obtenues sur x :\n"
            + conds
            + "\nPeux-tu en déduire maintenant l’ensemble de définition D ?"
        )


# ======== الأدوات ========

def solve_set(expr_str, mode):
    """Retourne l’objet Solveset sur ℝ."""
    e = simplify(expr_str.replace("^","**"))
    if mode == "ge": return solveset(e >= 0, x, domain=S.Reals)
    if mode == "gt": return solveset(e >  0, x, domain=S.Reals)
    if mode == "ne": return solveset(e != 0, x, domain=S.Reals)
    return S.Reals

def inequality_str(sol_set):
    """Transforme un Solveset en texte 'x <= a ou x >= b' ou 'x != a'."""
    if sol_set is S.EmptySet:
        return "∅"
    # cas '≠'
    if isinstance(sol_set, Union):
        parts = []
        for iv in sol_set.args:
            if isinstance(iv, Interval):
                # union de deux intervalles open autour de val
                a, b = iv.start, iv.end
                if a == -S.Infinity and b != S.Infinity:
                    parts.append(f"x < {b}")
                elif b == S.Infinity and a != -S.Infinity:
                    parts.append(f"x > {a}")
        # si c'est issu d'un ≠ c, on aura deux open autour de c
        if len(parts)==2 and parts[0].startswith("x <") and parts[1].startswith("x >"):
            # x != c
            c = sol_set.args[0].end
            return f"x != {c}"
        return " ou ".join(parts)
    # cas interval unique
    if isinstance(sol_set, Interval):
        a, b = sol_set.start, sol_set.end
        left = "<" if sol_set.left_open else "≤"
        right= "<" if sol_set.right_open else "≤"
        if a == -S.Infinity:    # (-∞, b] ou (-∞, b)
            return f"x {left} {b}"
        if b == S.Infinity:     # [a, ∞) ou (a, ∞)
            return f"x {right} {a}"
    # fallback
    return str(sol_set)

def extract_expr(text):
    m = re.search(r"f\(x\)\s*=\s*(.+)", text)
    if not m: return None
    return re.sub(r"√\s*\((.*?)\)", r"sqrt(\1)", m.group(1))


def analyse_expression(expr):
    steps = []
    steps += [("racine", e) for e in re.findall(r"sqrt\((.*?)\)", expr)]
    steps += [("log",    e) for e in re.findall(r"log\((.*?)\)", expr)]
    if "/" in expr:
        denom = expr.split("/")[-1]
        steps.append(("denominateur", denom.strip()))
    return steps


def component_label(t):
    return {"racine": "√", "log": "log", "denominateur": "le dénominateur"}[t]


def expected_condition(t, arg):
    if t == "racine":       return f"{arg} ≥ 0"
    if t == "log":          return f"{arg} > 0"
    if t == "denominateur": return f"{arg} ≠ 0"


def expected_solution(type_, arg):
    modes = {"racine":"ge", "log":"gt", "denominateur":"ne"}
    sol_set = solve_set(arg, modes[type_])
    # on garde à la fois l'objet et son texte
    return inequality_str(sol_set)



def solve_inequality(expr_str, mode):
    try:
        exp = simplify(expr_str.replace("^","**"))
        if mode == "ge": sol = solveset(exp>=0, x, domain=S.Reals)
        if mode == "gt": sol = solveset(exp>0,  x, domain=S.Reals)
        if mode == "ne": sol = solveset(exp!=0, x, domain=S.Reals)
        return convert_to_notation(sol)
    except:
        return "?"


def error_explanation(t, arg, cond):
    if t == "racine":
        return f"Pour √, l’intérieur doit être ≥ 0, donc {cond}."
    if t == "log":
        return f"Pour log, l’argument doit être > 0, donc {cond}."
    if t == "denominateur":
        return f"Le dénominateur ne doit pas être nul, donc {cond}."


def match_condition(reply, t, arg):
    r = reply.replace(" ","").replace(">=", "≥").replace("!=", "≠")
    pts = {
      "racine":["≥0",arg+"≥0"], "log":[">0",arg+">0"],
      "denominateur":["≠0",arg+"≠0"]
    }[t]
    return any(p in r for p in pts)


def match_solution(reply, attendu):
    # تنظيف و مقارنة جزئية
    norm = lambda s: re.sub(r"\s+","",s.lower()) \
                   .replace(">=", "≥").replace("<=", "≤").replace("!=", "≠")
    return norm(attendu) in norm(reply)


def condition_to_str(sol_text):
    # نحتفظ بالحل النصي كما أُرجع من solve_inequality
    return sol_text


def is_domain_correct_math(reply, conds):
    # ... كما عندك سابقًا (unchanged)
    sets = [condition_to_set(c) for c in conds]
    if not sets: return False, "ℝ"
    dom = sets[0]
    for s in sets[1:]: dom = dom.intersect(s)
    stud = parse_student_domain(reply)
    return (stud == dom), convert_to_notation(dom)


def condition_to_set(c):
    # ... غيرت لتدعم النصوص من solve_inequality إن لزم
    # ولكن بما أننا نستعمل نصوص موحدة، يبقى كما عندك سابقًا
    if "≥" in c:
        v = float(c.split("≥")[1]); return Interval(v, S.Infinity)
    if ">" in c:
        v = float(c.split(">")[1]); return Interval.open(v, S.Infinity)
    if "≠" in c:
        v = float(c.split("≠")[1])
        return Union(Interval.open(-S.Infinity, v), Interval.open(v, S.Infinity))
    return S.Reals


def parse_student_domain(r):
    # ... كما عندك سابقًا
    try:
        t = r.lower().replace(" ","").replace("∞","oo")
        t = t.replace("d=","")
        m = re.match(r"[\[\]()\]]?(-?\d+),\+?oo[\[\]()\]]?", t)
        if m:
            a=float(m.group(1))
            return Interval(a, S.Infinity,
                            left_open=t.startswith("]") or t.startswith("("))
        if "r" in t: return S.Reals
    except: pass
    return None


def convert_to_notation(sol):
    if sol is EmptySet: return "∅"
    if isinstance(sol, Interval):
        a="-∞" if sol.start==S.NegativeInfinity else str(sol.start)
        b="+∞" if sol.end  ==S.Infinity         else str(sol.end)
        l="[" if not sol.left_open else "]"
        r="]" if not sol.right_open else "["
        return f"{l}{a}, {b}{r}"
    if isinstance(sol, Union):
        return " ∪ ".join(convert_to_notation(i) for i in sol.args)
    if sol is S.Reals:
        return "ℝ"
    return str(sol)


def respond(t): return jsonify({"fulfillmentText": t})


if __name__ == "__main__":
    port = int(os.environ.get("PORT",10000))
    app.run(host="0.0.0.0",port=port)
