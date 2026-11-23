import os
import random
import sqlite3
import functools
from datetime import datetime, timedelta

from flask import (
    Flask, request, redirect, url_for, session,
    render_template_string, abort
)

DB_PATH = os.environ.get("DB_PATH", "/tmp/fedex.db")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "fedex2024")
SECRET_KEY = os.environ.get("SECRET_KEY", "fedex-secret-change-me")

app = Flask(__name__)
app.secret_key = SECRET_KEY

STATUS_STEPS = [
    ("Label Created", "Shipment information sent to FedEx"),
    ("Picked Up", "Package picked up by FedEx courier"),
    ("In Transit", "Package is in transit to the destination facility"),
    ("Out for Delivery", "Package is on the truck for delivery"),
    ("Delivered", "Package delivered"),
]
LAST_STEP = len(STATUS_STEPS) - 1
SEGMENTS = 4


# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shipments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref TEXT UNIQUE NOT NULL,
                step INTEGER NOT NULL DEFAULT 0,
                origin TEXT NOT NULL DEFAULT '',
                destination TEXT NOT NULL DEFAULT '',
                weight TEXT NOT NULL DEFAULT '',
                service TEXT NOT NULL DEFAULT 'FedEx Ground',
                ship_date TEXT NOT NULL DEFAULT '',
                est_date TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


def gen_ref():
    """Unified reference generator: one 12-digit FedEx-style number."""
    return "7" + "".join(random.choices("0123456789", k=11))


def unique_ref():
    with db() as conn:
        for _ in range(50):
            ref = gen_ref()
            row = conn.execute(
                "SELECT 1 FROM shipments WHERE ref = ?", (ref,)
            ).fetchone()
            if not row:
                return ref
    return gen_ref()


def get_shipment(ref):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM shipments WHERE ref = ?", (ref,)
        ).fetchone()


def all_shipments():
    with db() as conn:
        return conn.execute(
            "SELECT * FROM shipments ORDER BY id DESC"
        ).fetchall()


def step_label(step):
    step = max(0, min(step, LAST_STEP))
    return STATUS_STEPS[step][0]


def step_detail(step):
    step = max(0, min(step, LAST_STEP))
    return STATUS_STEPS[step][1]


def fmt_date(value):
    if not value:
        return "—"
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%b %d, %Y")
    except ValueError:
        return value


app.jinja_env.globals["step_label"] = step_label
app.jinja_env.globals["step_detail"] = step_detail
app.jinja_env.globals["fmt_date"] = fmt_date
app.jinja_env.globals["LAST_STEP"] = LAST_STEP
app.jinja_env.globals["SEGMENTS"] = SEGMENTS


# --------------------------------------------------------------------------
# Base template
# --------------------------------------------------------------------------
BASE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ page_title }} — FedEx Tracking</title>
<style>
:root {
    --fedex-purple: #4d148c;
    --fedex-orange: #ff6600;
    --fedex-gray: #f5f5f5;
    --fedex-dark: #1a1a1a;
    --fedex-line: #d8d8d8;
}
* { box-sizing: border-box; }
body {
    margin: 0;
    background-color: var(--fedex-gray);
    color: var(--fedex-dark);
    font-family: "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 15px;
    line-height: 1.5;
}
a { color: var(--fedex-purple); text-decoration: none; }
a:hover { text-decoration: underline; }

header.nav {
    background: var(--fedex-purple);
    padding: 14px 22px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
}
.wordmark {
    font-size: 27px;
    font-weight: 800;
    letter-spacing: -1.4px;
    font-style: italic;
    line-height: 1;
}
.wordmark .fed { color: #ffffff; }
.wordmark .ex {
    color: var(--fedex-orange);
    margin-left: 1px;
}
header.nav nav a {
    color: #f0e6fb;
    font-size: 13.5px;
    font-weight: 600;
    margin-left: 18px;
    text-transform: uppercase;
    letter-spacing: .4px;
    text-decoration: none;
}
header.nav nav a:hover { color: #ffffff; text-decoration: none; }

main {
    max-width: 860px;
    margin: 0 auto;
    padding: 26px 18px 60px;
}
.card {
    background: #ffffff;
    border: 1px solid var(--fedex-line);
    border-radius: 6px;
    padding: 22px;
    margin-bottom: 20px;
}
h1 { font-size: 22px; margin: 0 0 6px; font-weight: 700; }
h2 { font-size: 17px; margin: 0 0 12px; font-weight: 700; }
p.sub { margin: 0 0 18px; color: #5c5c5c; font-size: 14px; }

label {
    display: block;
    font-size: 12.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .5px;
    color: #4a4a4a;
    margin-bottom: 5px;
}
input[type=text], input[type=date], input[type=password], textarea, select {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid #b8b8b8;
    border-radius: 4px;
    font-size: 14.5px;
    font-family: inherit;
    background: #fff;
}
input:focus, textarea:focus, select:focus {
    outline: 2px solid var(--fedex-purple);
    outline-offset: -1px;
    border-color: var(--fedex-purple);
}
textarea { min-height: 74px; resize: vertical; }
.field { margin-bottom: 14px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 560px) { .grid2 { grid-template-columns: 1fr; } }

button, .btn {
    display: inline-block;
    background: var(--fedex-orange);
    color: #ffffff;
    border: 0;
    border-radius: 4px;
    padding: 11px 22px;
    font-size: 14px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .5px;
    cursor: pointer;
    font-family: inherit;
}
button:hover, .btn:hover { background: #e35c00; text-decoration: none; }
.btn-purple { background: var(--fedex-purple); }
.btn-purple:hover { background: #3a0f6b; }
.btn-sm { padding: 7px 14px; font-size: 12px; }
.btn-ghost {
    background: transparent;
    color: var(--fedex-purple);
    border: 1px solid var(--fedex-purple);
}
.btn-ghost:hover { background: #f2ecfa; }

.notice {
    background: #fdf1e6;
    border-left: 4px solid var(--fedex-orange);
    padding: 11px 14px;
    border-radius: 4px;
    font-size: 14px;
    margin-bottom: 18px;
}
.notice.ok { background: #eef7ee; border-left-color: #2f7d32; }

/* progress */
.progress { display: flex; gap: 6px; margin: 20px 0 10px; }
.seg { flex: 1; height: 8px; border-radius: 4px; background: #dcdcdc; }
.seg.on { background: linear-gradient(90deg, var(--fedex-orange), var(--fedex-purple)); }
.steps {
    display: flex;
    gap: 6px;
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: .3px;
    color: #8c8c8c;
    font-weight: 700;
}
.steps div { flex: 1; text-align: center; }
.steps div.on { color: var(--fedex-purple); }

table.detail { width: 100%; border-collapse: collapse; font-size: 14px; }
table.detail th {
    text-align: left;
    width: 40%;
    padding: 9px 0;
    color: #6b6b6b;
    font-weight: 600;
    vertical-align: top;
    border-bottom: 1px solid #eee;
}
table.detail td {
    padding: 9px 0;
    border-bottom: 1px solid #eee;
    font-weight: 600;
}

.status-badge {
    display: inline-block;
    background: var(--fedex-purple);
    color: #fff;
    font-size: 11.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .6px;
    padding: 5px 11px;
    border-radius: 3px;
}
.ref { font-family: "Consolas", monospace; font-size: 16px; letter-spacing: .5px; font-weight: 700; }

table.admin { width: 100%; border-collapse: collapse; font-size: 13.5px; }
table.admin th {
    text-align: left;
    padding: 9px 8px;
    background: #faf7fd;
    border-bottom: 2px solid var(--fedex-line);
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: .5px;
    color: #5c5c5c;
}
table.admin td { padding: 9px 8px; border-bottom: 1px solid #eee; vertical-align: middle; }

footer.foot {
    text-align: center;
    font-size: 12px;
    color: #8a8a8a;
    padding: 26px 16px 40px;
}
</style>
</head>
<body>
<header class="nav">
    <a href="{{ url_for('index') }}" style="text-decoration:none">
        <span class="wordmark"><span class="fed">Fed</span><span class="ex">Ex</span></span>
    </a>
    <nav>
        <a href="{{ url_for('index') }}">Track</a>
        <a href="{{ url_for('admin') }}">Control Panel</a>
    </nav>
</header>
<main>
{{ content|safe }}
</main>
<footer class="foot">FedEx Tracking — mock environment</footer>
</body>
</html>"""


def render(body_tpl, page_title, **ctx):
    ctx["page_title"] = page_title
    body = render_template_string(body_tpl, **ctx)
    return render_template_string(BASE, content=body, **ctx)


# --------------------------------------------------------------------------
# Public routes
# --------------------------------------------------------------------------
INDEX_BODY = """
{% if msg %}<div class="notice">{{ msg }}</div>{% endif %}
<div class="card">
    <h1>Track your package</h1>
    <p class="sub">Enter your tracking number to see the latest status.</p>
    <form method="post" action="{{ url_for('track_submit') }}">
        <div class="field">
            <label for="ref">Tracking number</label>
            <input type="text" id="ref" name="ref" placeholder="12-digit tracking number"
                   value="{{ prefill }}" autocomplete="off">
        </div>
        <button type="submit">Track</button>
    </form>
</div>
<div class="card">
    <h2>Need help?</h2>
    <p class="sub" style="margin:0">
        Tracking numbers are 12 digits and can be found on your shipping label
        or in your confirmation email.
    </p>
</div>
"""


@app.route("/")
def index():
    return render(
        INDEX_BODY, "Home",
        msg=request.args.get("msg", ""),
        prefill=request.args.get("ref", ""),
    )


@app.route("/track", methods=["POST"])
def track_submit():
    ref = (request.form.get("ref") or "").strip().replace(" ", "")
    if not ref:
        return redirect(url_for("index", msg="Please enter a tracking number."))
    if not get_shipment(ref):
        return redirect(url_for(
            "index",
            msg=f"No shipment found for {ref}. Check the number and try again.",
            ref=ref,
        ))
    return redirect(url_for("track_view", ref=ref))


TRACK_BODY = """
<div class="card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
        <div>
            <h1>Tracking {{ s['ref'] }}</h1>
            <p class="sub" style="margin:4px 0 0">
                {{ step_detail(s['step']) }}
            </p>
        </div>
        <span class="status-badge">{{ step_label(s['step']) }}</span>
    </div>

    <div class="progress">
        {% for i in range(SEGMENTS) %}
        <div class="seg {{ 'on' if i < s['step'] else '' }}"></div>
        {% endfor %}
    </div>
    <div class="steps">
        {% for i in range(SEGMENTS) %}
        <div class="{{ 'on' if i < s['step'] else '' }}">{{ step_label(i) }}</div>
        {% endfor %}
    </div>
</div>

<div class="card">
    <h2>Shipment details</h2>
    <table class="detail">
        <tr><th>Tracking number</th><td class="ref">{{ s['ref'] }}</td></tr>
        <tr><th>Service</th><td>{{ s['service'] }}</td></tr>
        <tr><th>Status</th><td>{{ step_label(s['step']) }}</td></tr>
        <tr><th>Ship date</th><td>{{ fmt_date(s['ship_date']) }}</td></tr>
        <tr><th>Estimated delivery</th><td>{{ fmt_date(s['est_date']) }}</td></tr>
        <tr><th>Weight</th><td>{{ s['weight'] or '—' }}</td></tr>
        <tr><th>Origin</th><td>{{ s['origin'] or '—' }}</td></tr>
        <tr><th>Destination</th><td>{{ s['destination'] or '—' }}</td></tr>
    </table>
</div>

{% if s['notes'] %}
<div class="card">
    <h2>Delivery notes</h2>
    <p class="sub" style="margin:0">{{ s['notes']|safe }}</p>
</div>
{% endif %}

<p><a href="{{ url_for('index') }}">&larr; Track another package</a></p>
"""


@app.route("/track/<ref>")
def track_view(ref):
    s = get_shipment(ref)
    if not s:
        return render(
            """<div class="card"><h1>Not found</h1>
            <p class="sub">No shipment matches <strong>{{ ref }}</strong>.</p>
            <a class="btn btn-purple" href="{{ url_for('index') }}">Back to tracking</a></div>""",
            "Not found", ref=ref,
        ), 404
    return render(TRACK_BODY, f"Tracking {ref}", s=s)


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------
def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


LOGIN_BODY = """
<div class="card" style="max-width:420px;margin:0 auto">
    <h1>Control panel</h1>
    <p class="sub">Enter the admin password to continue.</p>
    {% if error %}<div class="notice">{{ error }}</div>{% endif %}
    <form method="post">
        <div class="field">
            <label for="pw">Password</label>
            <input type="password" id="pw" name="password" autofocus>
        </div>
        <button type="submit" class="btn-purple">Sign in</button>
    </form>
</div>
"""


@app.route("/control-panel-8471/login", methods=["GET", "POST"])
def admin_login():
    error = ""
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            nxt = request.args.get("next") or url_for("admin")
            return redirect(nxt)
        error = "Incorrect password."
    return render(LOGIN_BODY, "Admin login", error=error)


@app.route("/control-panel-8471/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))


ADMIN_BODY = """
{% if msg %}<div class="notice ok">{{ msg }}</div>{% endif %}
<div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
        <h1 style="margin:0">Control panel</h1>
        <a class="btn btn-ghost btn-sm" href="{{ url_for('admin_logout') }}">Log out</a>
    </div>
    <p class="sub" style="margin-top:8px">Create shipments and advance their status.</p>
</div>

<div class="card">
    <h2>New shipment</h2>
    <form method="post" action="{{ url_for('admin_create') }}">
        <div class="grid2">
            <div class="field">
                <label for="origin">Origin</label>
                <input type="text" id="origin" name="origin" placeholder="Memphis, TN">
            </div>
            <div class="field">
                <label for="destination">Destination</label>
                <input type="text" id="destination" name="destination" placeholder="Austin, TX">
            </div>
            <div class="field">
                <label for="weight">Weight</label>
                <input type="text" id="weight" name="weight" placeholder="2.4 lbs">
            </div>
            <div class="field">
                <label for="service">Service</label>
                <select id="service" name="service">
                    <option>FedEx Ground</option>
                    <option>FedEx Express Saver</option>
                    <option>FedEx 2Day</option>
                    <option>FedEx Priority Overnight</option>
                    <option>FedEx Home Delivery</option>
                </select>
            </div>
            <div class="field">
                <label for="ship_date">Ship date</label>
                <input type="date" id="ship_date" name="ship_date">
            </div>
            <div class="field">
                <label for="est_date">Estimated delivery</label>
                <input type="date" id="est_date" name="est_date">
            </div>
        </div>
        <div class="field">
            <label for="notes">Notes</label>
            <textarea id="notes" name="notes" placeholder="Optional delivery notes"></textarea>
        </div>
        <button type="submit" class="btn-purple">Create shipment</button>
    </form>
</div>

<div class="card">
    <h2>All shipments ({{ shipments|length }})</h2>
    {% if shipments %}
    <table class="admin">
        <tr>
            <th>Ref</th><th>Status</th><th>Destination</th><th>Est.</th><th>Actions</th>
        </tr>
        {% for s in shipments %}
        <tr>
            <td><a href="{{ url_for('track_view', ref=s['ref']) }}">{{ s['ref'] }}</a></td>
            <td>{{ step_label(s['step']) }}</td>
            <td>{{ s['destination'] or '—' }}</td>
            <td>{{ fmt_date(s['est_date']) }}</td>
            <td style="white-space:nowrap">
                <form method="post" action="{{ url_for('admin_advance', sid=s['id']) }}" style="display:inline">
                    <button class="btn-sm" type="submit">Advance</button>
                </form>
                <form method="post" action="{{ url_for('admin_delete', sid=s['id']) }}" style="display:inline"
                      onsubmit="return confirm('Delete {{ s['ref'] }}?')">
                    <button class="btn-sm btn-ghost" type="submit">Delete</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
    {% else %}
    <p class="sub" style="margin:0">No shipments yet.</p>
    {% endif %}
</div>
"""


@app.route("/control-panel-8471")
@login_required
def admin():
    return render(ADMIN_BODY, "Control panel",
                  shipments=all_shipments(), msg=request.args.get("msg", ""))


@app.route("/control-panel-8471/create", methods=["POST"])
@login_required
def admin_create():
    ref = unique_ref()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    est = (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d")
    with db() as conn:
        conn.execute("""
            INSERT INTO shipments
                (ref, step, origin, destination, weight, service,
                 ship_date, est_date, notes, created_at)
            VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ref,
            request.form.get("origin", "").strip(),
            request.form.get("destination", "").strip(),
            request.form.get("weight", "").strip(),
            request.form.get("service", "FedEx Ground").strip(),
            request.form.get("ship_date", "").strip() or today,
            request.form.get("est_date", "").strip() or est,
            request.form.get("notes", "").strip(),
            datetime.utcnow().isoformat(),
        ))
        conn.commit()
    return redirect(url_for("admin", msg=f"Shipment {ref} created."))


@app.route("/control-panel-8471/<int:sid>/advance", methods=["POST"])
@login_required
def admin_advance(sid):
    with db() as conn:
        row = conn.execute(
            "SELECT step, ref FROM shipments WHERE id = ?", (sid,)
        ).fetchone()
        if not row:
            abort(404)
        new_step = min(row["step"] + 1, LAST_STEP)
        conn.execute(
            "UPDATE shipments SET step = ? WHERE id = ?", (new_step, sid)
        )
        conn.commit()
        ref = row["ref"]
    return redirect(url_for(
        "admin", msg=f"{ref} → {step_label(new_step)}."
    ))


@app.route("/control-panel-8471/<int:sid>/delete", methods=["POST"])
@login_required
def admin_delete(sid):
    with db() as conn:
        conn.execute("DELETE FROM shipments WHERE id = ?", (sid,))
        conn.commit()
    return redirect(url_for("admin", msg="Shipment deleted."))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
