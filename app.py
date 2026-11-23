import os, re, random, string, sqlite3
from flask import Flask, render_template_string, request, redirect, url_for, abort

app = Flask(__name__)
DB = os.environ.get("DB_PATH", "track.db")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "changeme")

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS pkgs(
            num TEXT PRIMARY KEY, status TEXT, origin TEXT, dest TEXT,
            created TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, num TEXT, [when] TEXT,
            text TEXT, loc TEXT)""")
init()

CSS = """
:root{--purple:#4d148c;--orange:#ff6600;--ink:#1a1a1a}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Arial,Helvetica,sans-serif;color:var(--ink);background:#fff}
.topbar{display:flex;align-items:center;gap:24px;padding:14px 40px;background:var(--purple);color:#fff}
.topbar nav{display:flex;gap:18px}
.topbar a{color:#fff;text-decoration:none;font-size:14px}
.brand{font-size:24px;font-weight:800;letter-spacing:-1px}
.hero{padding:70px 40px;background:linear-gradient(180deg,#f7f5fb,#fff)}
.hero h1{font-size:36px;font-weight:800;color:var(--purple);margin-bottom:20px}
.box{display:flex;gap:10px;max-width:620px;flex-wrap:wrap}
.box input{flex:1;min-width:160px;padding:13px 15px;border:1px solid #ccc;border-radius:4px;font-size:15px}
.box button{padding:13px 24px;background:var(--orange);color:#fff;border:0;border-radius:4px;font-weight:700;cursor:pointer}
.hint{margin-top:14px;font-size:14px;color:#555}.hint a{color:var(--purple)}
.pill{display:inline-block;margin:10px 0;padding:8px 16px;border-radius:20px;background:#4d148c;color:#fff;font-weight:700}
.meta{font-size:14px;color:#555;margin-bottom:20px}
.tl{border-left:3px solid var(--purple);padding-left:20px;margin:24px 0}
.ev{padding:12px 0;border-bottom:1px solid #f0f0f0;font-size:14px}
.ev b{display:block}.ev span{color:#777;font-size:12px}
.alert{padding:10px 14px;border-radius:6px;margin:12px 0;font-size:14px}
.ok{background:#e8f5e9;color:#2e7d32}.err{background:#fdecea;color:#c00}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{padding:8px;border-bottom:1px solid #eee;text-align:left}
"""

BASE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>%s</title>
<style>%s</style></head><body>
<header class="topbar"><div class="brand">FedEx</div>
<nav><a href="/">Home</a><a href="/track">Track</a></nav></header>
%s</body></html>"""

HOME = BASE % ("Track", CSS, """
<section class="hero"><h1>Track your shipment</h1>
<form action="/track" method="post" class="box">
<input name="num" placeholder="Enter tracking number"><button>Track</button></form>
</section>""")

TRACKPAGE = BASE % ("Track", CSS, """
<section class="hero"><h1>Track by number</h1>
<form action="/track" method="post" class="box">
<input name="num" placeholder="Enter tracking number"><button>Track</button></form>
{{ msg|safe }}</section>""")

RESULT = BASE % ("Tracking", CSS, """
<section class="hero"><h1>Tracking {{p['num']}}</h1>
<p class="pill">{{p['status']}}</p><p class="meta">{{p['origin']}} → {{p['dest']}}</p>
<div class="tl">{% for e in ev %}
<div class="ev"><b>{{e['text']}}</b><span>{{e['when']}} · {{e['loc']}}</span></div>
{% else %}<div class="ev">No activity yet.</div>{% endfor %}</div></section>""")

ADMIN = BASE % ("Admin", CSS, """
<section class="hero"><h1>Admin</h1>
<p><a href="{{ url_for('home') }}">Back to tracking</a></p>{{ msg|safe }}
<form method="post" action="{{ url_for('panel_add', k=k) }}" class="box">
<input id="package-number" name="num" placeholder="Tracking number (blank = auto)">
<button type="button" id="generate-number">Generate</button>
<p id="generate-error" role="status"></p>
<input name="status" placeholder="Status (e.g. In transit)">
<input name="origin" placeholder="Origin city"><input name="dest" placeholder="Destination city">
<button>Create package</button></form>
{% if pkgs %}<h3 style="margin:24px 0 8px">Packages</h3>
<table><tr><th>Number</th><th>Status</th><th>Route</th></tr>
{% for p in pkgs %}<tr><td><a href="/result/{{p['num']}}">{{p['num']}}</a></td>
<td>{{p['status']}}</td><td>{{p['origin']}}→{{p['dest']}}</td></tr>{% endfor %}</table>{% endif %}
<h3 style="margin:28px 0 8px">Add event</h3>
<form method="post" action="{{ url_for('panel_event', k=k) }}" class="box">
<input name="num" placeholder="Tracking number" required>
<input name="text" placeholder="Event text (e.g. Customs clearance)" required>
<input name="loc" placeholder="Location" required>
<input name="when" placeholder="2026-11-23 09:14" required>
<input name="status" placeholder="Set new status (optional)">
<button>Add event</button></form></section>
<script>
document.getElementById('generate-number').addEventListener('click', async () => {
  const error = document.getElementById('generate-error');
  error.textContent = '';
  try {
    const response = await fetch({{ url_for('generate') | tojson }});
    if (!response.ok) throw new Error('Request failed');
    const data = await response.json();
    document.getElementById('package-number').value = data.num;
  } catch {
    error.textContent = 'Could not generate a tracking number. Try again.';
  }
});
</script>""")

def gen():
    base = "".join(random.choices(string.digits, k=10))
    total = 0
    for i, ch in enumerate(reversed(base)):
        d = int(ch) * (2 if i % 2 == 0 else 1)
        total += d - 9 if d > 9 else d
    return base + str((10 - total % 10) % 10)

def guard():
    if request.args.get("k") != ADMIN_KEY:
        abort(403)

@app.route("/")
def home(): return render_template_string(HOME)

@app.route("/track", methods=["GET", "POST"])
def track():
    if request.method == "GET": return render_template_string(TRACKPAGE, msg="")
    num = (request.form.get("num") or "").strip()
    if not re.fullmatch(r"\d{10,22}", num):
        return render_template_string(TRACKPAGE, msg='<p class="alert err">Invalid number.</p>')
    return redirect(url_for("result", num=num))

@app.route("/generate")
def generate(): return {"num": gen()}

@app.route("/result/<num>")
def result(num):
    c = db()
    p = c.execute("SELECT * FROM pkgs WHERE num=?", (num,)).fetchone()
    if not p: return render_template_string(TRACKPAGE, msg=f'<p class="alert err">No package {num}</p>')
    ev = c.execute("SELECT * FROM events WHERE num=? ORDER BY [when] DESC", (num,)).fetchall()
    return render_template_string(RESULT, p=p, ev=ev)

@app.route("/panel")
def panel():
    guard()
    return render_template_string(ADMIN, k=ADMIN_KEY, msg="",
        pkgs=db().execute("SELECT * FROM pkgs ORDER BY created DESC").fetchall())

@app.route("/panel/add", methods=["POST"])
def panel_add():
    guard()
    num = (request.form.get("num") or gen()).strip()
    with db() as c:
        c.execute("INSERT OR REPLACE INTO pkgs(num,status,origin,dest) VALUES(?,?,?,?)",
                  (num, request.form.get("status") or "Label created",
                   request.form.get("origin") or "-", request.form.get("dest") or "-"))
    return redirect(url_for("panel", k=ADMIN_KEY))

@app.route("/panel/event", methods=["POST"])
def panel_event():
    guard()
    with db() as c:
        c.execute("INSERT INTO events(num,text,loc,[when]) VALUES(?,?,?,?)",
                  (request.form["num"], request.form["text"], request.form["loc"], request.form["when"]))
        if request.form.get("status"):
            c.execute("UPDATE pkgs SET status=? WHERE num=?", (request.form["status"], request.form["num"]))
    return redirect(url_for("panel", k=ADMIN_KEY))

if __name__ == "__main__": app.run(debug=True)