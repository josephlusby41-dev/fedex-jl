import os
import sqlite3
import random
import string
import datetime
from urllib.parse import quote
from flask import Flask, request, render_template_string, redirect, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-key-change-this")

DB_PATH = os.environ.get("DB_PATH", "/tmp/fedex.db")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "Deebaby25!")

CITIES = [
    ("Memphis, TN", "FedEx Express World Hub"),
    ("Indianapolis, IN", "FedEx Express Facility"),
    ("Atlanta, GA", "FedEx Express Facility"),
    ("Dallas, TX", "FedEx Ship Center"),
    ("Los Angeles, CA", "FedEx Express Facility"),
    ("Newark, NJ", "FedEx Express Facility"),
    ("Chicago, IL", "FedEx Express Facility"),
    ("Oakland, CA", "FedEx Ground Facility"),
]

STAGES = [
    ("Shipment information sent to FedEx", None),
    ("Picked up", None),
    ("In transit", None),
    ("Arrived at FedEx location", None),
    ("Out for delivery", None),
    ("Delivered", None),
]

_db_initialized = False

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    global _db_initialized
    if _db_initialized:
        return
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS trackings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_number TEXT UNIQUE,
        sender_name TEXT,
        recipient_name TEXT,
        recipient_address TEXT,
        service_type TEXT,
        weight TEXT,
        pieces TEXT,
        reference TEXT,
        status TEXT,
        created_at TEXT,
        eta TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tracking_number TEXT,
        timestamp TEXT,
        location TEXT,
        description TEXT,
        details TEXT
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_tn ON events(tracking_number)")
    conn.commit()
    conn.close()
    seed_demo_data()
    _db_initialized = True

def seed_demo_data():
    conn = get_db()
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM trackings").fetchone()[0]
    if count == 0:
        now = datetime.datetime.now()
        tn = "123456789012"
        eta = now + datetime.timedelta(days=2)
        eta_str = eta.strftime("%b %d") + " by 4:30 pm"
        c.execute("""INSERT INTO trackings
            (tracking_number, sender_name, recipient_name, recipient_address, service_type, weight, pieces, reference, status, created_at, eta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tn, "ACME WIDGETS LLC", "JOSEPH LUSBY", "1420 MAPLE ST, AUSTIN TX 78701",
             "FedEx Ground", "4.2 lbs", "1", "PO-88213", "In transit",
             fmt_ts(now), eta_str))
        add_event_internal(c, tn, now - datetime.timedelta(hours=6), "DALLAS, TX", "Picked up", "Tendered at FedEx origin facility")
        add_event_internal(c, tn, now - datetime.timedelta(hours=3), "DALLAS, TX", "In transit", "Departed FedEx location")
        conn.commit()
    conn.close()

def add_event_internal(cursor, tn, dt, location, desc, details=""):
    cursor.execute("INSERT INTO events (tracking_number, timestamp, location, description, details) VALUES (?, ?, ?, ?, ?)",
                   (tn, fmt_ts(dt), location, desc, details))

def add_event(tn, dt, location, desc, details=""):
    conn = get_db()
    c = conn.cursor()
    add_event_internal(c, tn, dt, location, desc, details)
    conn.commit()
    conn.close()

def fmt_ts(dt):
    return dt.strftime("%b %d, %Y %I:%M %p")

def gen_tracking_number():
    return str(random.randint(700000000000, 799999999999))

def rand_ref():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

# --- TEMPLATES ---

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' fill='%234d148c'/><text x='16' y='22' font-size='14' font-style='italic' font-weight='bold' text-anchor='middle' fill='white' font-family='Arial'>Fx</text></svg>">
    <style>
        :root {
            --fedex-purple: #4d148c;
            --fedex-orange: #ff6600;
            --fedex-gray: #f2f2f2;
            --text-dark: #333333;
            --text-light: #666666;
        }
        * { box-sizing: border-box; }
        body {
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: var(--fedex-gray);
            color: var(--text-dark);
            -webkit-font-smoothing: antialiased;
        }
        a { color: var(--fedex-purple); text-decoration: none; }
        a:hover { text-decoration: underline; }
        .top-accent { background: var(--fedex-purple); height: 4px; width: 100%; }
        header { background-color: #ffffff; border-bottom: 1px solid #e0e0e0; padding: 0; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .header-inner { max-width: 1100px; margin: 0 auto; padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; }
        .logo { font-size: 28px; font-weight: 900; letter-spacing: -1.5px; font-style: italic; line-height: 1; }
        .logo .fed { color: var(--fedex-purple); }
        .logo .ex { color: var(--fedex-orange); }
        .logo-sub { font-size: 10px; font-weight: 600; color: #999; text-transform: uppercase; letter-spacing: 1px; margin-left: 8px; vertical-align: middle; }
        nav { background: var(--fedex-purple); }
        nav .nav-inner { max-width: 1100px; margin: 0 auto; display: flex; }
        nav a { color: white; text-decoration: none; padding: 14px 20px; font-size: 14px; font-weight: 600; display: block; transition: background 0.2s; }
        nav a:hover { background: rgba(255,255,255,0.1); text-decoration: none; }
        nav a.active { background: var(--fedex-orange); }
        .container { max-width: 1100px; margin: 0 auto; padding: 0 20px; }
        .main-content { padding: 40px 0; min-height: 60vh; }
        .search-card { background: white; padding: 40px; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; max-width: 700px; margin: 0 auto; }
        .search-card h1 { font-size: 24px; margin: 0 0 10px; color: var(--text-dark); font-weight: 700; }
        .search-card p { color: var(--text-light); margin: 0 0 25px; font-size: 15px; }
        .input-group { display: flex; gap: 10px; justify-content: center; }
        input[type="text"] {
            padding: 12px 16px;
            width: 350px;
            border: 1px solid #ccc;
            border-radius: 4px;
            font-size: 16px;
            transition: border 0.2s;
        }
        input[type="text"]:focus { outline: none; border-color: var(--fedex-purple); box-shadow: 0 0 0 3px rgba(77,20,140,0.1); }
        .btn-track {
            background-color: var(--fedex-orange);
            color: white;
            border: none;
            padding: 12px 32px;
            font-size: 16px;
            font-weight: 700;
            border-radius: 4px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn-track:hover { background-color: #e55b00; }
        .error-msg {
            background-color: #fff5f5;
            border: 1px solid #feb2b2;
            color: #c53030;
            padding: 16px;
            border-radius: 4px;
            margin-top: 20px;
            text-align: left;
            max-width: 700px;
            margin-left: auto;
            margin-right: auto;
            font-size: 14px;
            display: flex;
            align-items: center;
        }
        .error-msg::before { content: "!"; display: inline-flex; justify-content: center; align-items: center; width: 20px; height: 20px; background: #c53030; color: white; border-radius: 50%; font-size: 12px; font-weight: bold; margin-right: 10px; }
        .result-card { max-width: 850px; margin: 0 auto; background: white; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }
        .result-header { padding: 24px 30px; border-bottom: 1px solid #eee; background: #fafafa; }
        .result-header .label { font-size: 12px; text-transform: uppercase; color: #666; font-weight: 600; letter-spacing: 0.5px; }
        .result-header .tn { font-size: 18px; font-weight: 700; color: var(--fedex-purple); margin: 4px 0 12px; }
        .result-header .status { font-size: 22px; font-weight: 800; color: var(--text-dark); }
        .result-header .eta { font-size: 14px; color: var(--text-light); margin-top: 6px; }
        .result-header .eta strong { color: var(--fedex-purple); }
        .progress-container { padding: 20px 30px; background: #fff; border-bottom: 1px solid #eee; }
        .progress-bar { display: flex; height: 6px; background: #eee; border-radius: 3px; overflow: hidden; margin-bottom: 10px; }
        .progress-bar span { flex: 1; background: #eee; transition: background 0.3s; }
        .progress-bar span.on { background: var(--fedex-orange); }
        .progress-labels { display: flex; justify-content: space-between; font-size: 11px; color: #999; font-weight: 600; text-transform: uppercase; }
        .details-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 20px; padding: 24px 30px; border-bottom: 1px solid #eee; background: #fff; }
        .detail-item strong { display: block; font-size: 11px; text-transform: uppercase; color: #999; margin-bottom: 4px; font-weight: 700; letter-spacing: 0.5px; }
        .detail-item span { font-size: 14px; color: var(--text-dark); font-weight: 500; }
        .timeline-section { padding: 30px; background: #fff; }
        .timeline-title { font-size: 16px; font-weight: 700; color: var(--text-dark); margin-bottom: 20px; text-transform: uppercase; letter-spacing: 0.5px; }
        .event-row { display: flex; gap: 20px; padding: 16px 0; border-bottom: 1px solid #f5f5f5; position: relative; }
        .event-row:last-child { border-bottom: none; }
        .loc-icon {
            width: 24px;
            height: 24px;
            flex-shrink: 0;
            margin-top: 2px;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%234d148c'%3E%3Cpath d='M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: center;
        }
        .event-time-col { min-width: 160px; font-size: 13px; color: #666; font-weight: 500; padding-top: 2px; }
        .event-info-col { flex: 1; }
        .event-desc { font-weight: 700; font-size: 15px; color: var(--text-dark); margin-bottom: 2px; }
        .event-loc { font-size: 13px; color: #666; }
        .event-det { font-size: 12px; color: #999; margin-top: 2px; font-style: italic; }
        .disclaimer { max-width: 850px; margin: 20px auto 0; font-size: 11px; color: #999; line-height: 1.5; text-align: center; }
        footer { background: var(--fedex-purple); color: #fff; margin-top: 60px; padding: 40px 0; font-size: 13px; }
        .footer-inner { max-width: 1100px; margin: 0 auto; padding: 0 20px; }
        .footer-links { display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; }
        .footer-links a { color: rgba(255,255,255,0.8); text-decoration: none; }
        .footer-links a:hover { color: white; text-decoration: underline; }
        .copyright { color: rgba(255,255,255,0.5); font-size: 11px; }
        /* Admin */
        .admin-card { background: white; border-radius: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 30px; max-width: 1000px; margin: 0 auto; }
        .admin-card h1 { color: var(--fedex-purple); margin-top: 0; }
        .admin-card table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        .admin-card th { background: var(--fedex-purple); color: #fff; padding: 10px; text-align: left; font-size: 13px; }
        .admin-card td { padding: 10px; border-bottom: 1px solid #eee; font-size: 14px; }
        .admin-card input, .admin-card select { padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; width: 100%; }
        .btn-admin { background: var(--fedex-purple); color: #fff; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-weight: 700; }
        .btn-admin:hover { background: #3a0f6b; }
        .btn-advance { background: var(--fedex-orange); color: #fff; border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 700; }
        .btn-del { background: #c53030; color: #fff; border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 700; text-decoration: none; }
    </style>
</head>
<body>
    <div class="top-accent"></div>
    <header>
        <div class="header-inner">
            <div class="logo">
                <span class="fed">Fed</span><span class="ex">Ex</span>
                <span class="logo-sub">Tracking</span>
            </div>
            <div style="font-size: 13px;">
                <a href="/control-panel-8471" style="color: #666;">Admin</a>
            </div>
        </div>
    </header>
    <nav>
        <div class="nav-inner">
            <a href="/" class="active">TRACK</a>
            <a href="#" onclick="return false;">SHIP</a>
            <a href="#" onclick="return false;">LOCATIONS</a>
            <a href="#" onclick="return false;">SUPPORT</a>
        </div>
    </nav>
    <div class="container main-content">
        {{ content }}
    </div>
    <footer>
        <div class="footer-inner">
            <div class="footer-links">
                <a href="#">About FedEx</a>
                <a href="#">Careers</a>
                <a href="#">Investors</a>
                <a href="#">Privacy &amp; Security</a>
                <a href="#">Terms of Use</a>
            </div>
            <div class="copyright">&copy; 1995-{{ year }} FedEx. All rights reserved.</div>
        </div>
    </footer>
</body>
</html>
"""

HOME_TEMPLATE = """
<div class="search-card">
    <h1>Tracking</h1>
    <p>Enter your tracking number to see the latest status of your shipment.</p>
    <form method="POST" action="/track" class="input-group">
        <input type="text" name="tracking_number" placeholder="Tracking Number" required>
        <button class="btn-track" type="submit">TRACK</button>
    </form>
    {% if error %}
    <div class="error-msg">We could not find a shipment matching this tracking number. Please check the number and try again.</div>
    {% endif %}
</div>
"""

RESULT_TEMPLATE = """
<div class="result-card">
    <div class="result-header">
        <div class="label">Tracking Number</div>
        <div class="tn">{{ t['tracking_number'] }}</div>
        <div class="status">{{ t['status'] }}</div>
        <div class="eta">Estimated Delivery: <strong>{{ t['eta'] }}</strong></div>
    </div>
    <div class="progress-container">
        <div class="progress-bar">
            {% for i in range(5) %}<span class="{{ 'on' if i < progress_step else '' }}"></span>{% endfor %}
        </div>
        <div class="progress-labels">
            <span>Picked Up</span><span>In Transit</span><span>Out for Delivery</span><span>Delivered</span>
        </div>
    </div>
    <div class="details-grid">
        <div class="detail-item"><strong>Service</strong><span>{{ t['service_type'] }}</span></div>
        <div class="detail-item"><strong>Weight</strong><span>{{ t['weight'] }}</span></div>
        <div class="detail-item"><strong>Pieces</strong><span>{{ t['pieces'] }}</span></div>
        <div class="detail-item"><strong>Reference</strong><span>{{ t['reference'] }}</span></div>
        <div class="detail-item"><strong>Ship To</strong><span>{{ t['recipient_name'] }}<br>{{ t['recipient_address'] }}</span></div>
        <div class="detail-item"><strong>Shipped From</strong><span>{{ t['sender_name'] }}</span></div>
    </div>
    <div class="timeline-section">
        <div class="timeline-title">Shipment Progress</div>
        {% for e in events %}
        <div class="event-row">
            <div class="loc-icon"></div>
            <div class="event-time-col">{{ e['timestamp'] }}</div>
            <div class="event-info-col">
                <div class="event-desc">{{ e['description'] }}</div>
                <div class="event-loc">{{ e['location'] }}</div>
                {% if e['details'] %}<div class="event-det">{{ e['details'] }}</div>{% endif %}
            </div>
        </div>
        {% endfor %}
    </div>
</div>
<div class="disclaimer">Delivery times are estimates and not guaranteed. Shipment progress is updated as scans occur throughout the FedEx network.</div>
"""

ADMIN_LOGIN_TEMPLATE = """
<div class="admin-card" style="max-width: 420px; margin-top: 40px;">
    <h1>Admin Login</h1>
    {% if error %}<p style="color:#c53030; font-weight:700;">Incorrect username or password.</p>{% endif %}
    <form method="POST" action="/control-panel-8471/login">
        <label style="font-size:12px; font-weight:700;">USERNAME</label>
        <input type="text" name="username" required>
        <label style="font-size:12px; font-weight:700; display:block; margin-top:12px;">PASSWORD</label>
        <input type="password" name="password" required>
        <button class="btn-admin" type="submit" style="margin-top:16px;">LOG IN</button>
    </form>
</div>
"""

ADMIN_DASHBOARD_TEMPLATE = """
<div class="admin-card">
    <h1>Admin Panel</h1>
    <div style="background:#f9f9f9; padding:20px; border:1px solid #ddd; margin-bottom:24px;">
        <form method="POST" action="/control-panel-8471/create" style="display:grid; gap:10px; grid-template-columns:1fr 1fr;">
            <input name="sender_name" placeholder="Sender Name" required>
            <input name="recipient_name" placeholder="Recipient Name" required>
            <input name="recipient_address" placeholder="Recipient Address (City, ST)" required style="grid-column:span 2;">
            <select name="service_type">
                <option>FedEx Priority Overnight</option>
                <option>FedEx 2Day</option>
                <option>FedEx Express Saver</option>
                <option>FedEx Ground</option>
                <option>FedEx Home Delivery</option>
            </select>
            <select name="weight">
                <option>1 lb</option><option>3 lb</option><option>5 lb</option>
                <option>8 lb</option><option>12 lb</option><option>25 lb</option>
            </select>
            <button class="btn-admin" type="submit" style="grid-column:span 2;">CREATE TRACKING</button>
        </form>
    </div>
    <table>
        <tr><th>Tracking #</th><th>Recipient</th><th>Status</th><th>ETA</th><th>Actions</th></tr>
        {% for r in rows %}
        <tr>
            <td><a href="/t/{{ r['tracking_number'] }}">{{ r['tracking_number'] }}</a></td>
            <td>{{ r['recipient_name'] }}</td>
            <td>{{ r['status'] }}</td>
            <td>{{ r['eta'] }}</td>
            <td>
                <form action="/control-panel-8471/advance/{{ r['tracking_number'] }}" method="POST" style="display:inline;">
                    <button class="btn-advance" type="submit">Advance</button>
                </form>
                <a class="btn-del" href="/control-panel-8471/delete/{{ r['tracking_number'] }}">Delete</a>
            </td>
        </tr>
        {% endfor %}
    </table>
</div>
"""

def page(content, title="FedEx | Tracking", **ctx):
    return render_template_string(BASE_TEMPLATE, content=content, title=title,
                                  year=datetime.datetime.now().year, **ctx)

# --- ROUTES ---

@app.before_request
def ensure_db():
    init_db()

@app.route("/", methods=["GET"])
def home():
    return page(render_template_string(HOME_TEMPLATE, error=False))

@app.route("/track", methods=["POST"])
def track_submit():
    tn = request.form.get("tracking_number", "").strip()
    if not tn:
        return page(render_template_string(HOME_TEMPLATE, error=False))
    return redirect(f"/t/{quote(tn)}")

@app.route("/t/<path:tracking_number>")
def result(tracking_number):
    conn = get_db()
    row = conn.execute("SELECT * FROM trackings WHERE tracking_number=?", (tracking_number,)).fetchone()
    if not row:
        conn.close()
        return page(render_template_string(HOME_TEMPLATE, error=True)), 404
    events = conn.execute("SELECT * FROM events WHERE tracking_number=? ORDER BY id DESC", (tracking_number,)).fetchall()
    conn.close()
    progress_step = 1
    if row["status"] == "In transit": progress_step = 2
    elif row["status"] == "Arrived at FedEx location": progress_step = 3
    elif row["status"] == "Out for delivery": progress_step = 4
    elif row["status"] == "Delivered": progress_step = 5
    return page(render_template_string(RESULT_TEMPLATE, t=row, events=events, progress_step=progress_step),
                title="Tracking Results | FedEx")

@app.route("/control-panel-8471", methods=["GET"])
def admin():
    if not session.get("admin"):
        return redirect("/control-panel-8471/login")
    conn = get_db()
    rows = conn.execute("SELECT * FROM trackings ORDER BY id DESC").fetchall()
    conn.close()
    return page(render_template_string(ADMIN_DASHBOARD_TEMPLATE, rows=rows),
                title="Admin | FedEx")

@app.route("/control-panel-8471/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USER and request.form.get("password") == ADMIN_PASS:
            session["admin"] = True
            return redirect("/control-panel-8471")
        return page(render_template_string(ADMIN_LOGIN_TEMPLATE, error=True)), 401
    return page(render_template_string(ADMIN_LOGIN_TEMPLATE, error=False), title="Admin Login | FedEx")

@app.route("/control-panel-8471/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/control-panel-8471/login")

@app.route("/control-panel-8471/create", methods=["POST"])
def admin_create():
    if not session.get("admin"):
        return redirect("/control-panel-8471/login")
    tn = gen_tracking_number()
    now = datetime.datetime.now()
    days = random.choice([1, 2, 3])
    eta = now + datetime.timedelta(days=days)
    eta_str = eta.strftime("%b %d") + " by " + ("10:30 am" if days == 1 else ("4:30 pm" if days == 2 else "8:00 pm"))
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO trackings (tracking_number, sender_name, recipient_name, recipient_address,
        service_type, weight, pieces, reference, status, created_at, eta) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (tn, request.form.get("sender_name", ""), request.form.get("recipient_name", ""),
         request.form.get("recipient_address", ""), request.form.get("service_type", "FedEx Ground"),
         request.form.get("weight", "1 lb"), "1", rand_ref(),
         "Shipment information sent to FedEx", fmt_ts(now), eta_str))
    conn.commit()
    conn.close()
    city, fac = random.choice(CITIES)
    add_event(tn, now, f"{fac}, {city}", "Shipment information sent to FedEx",
              f"Reference: {rand_ref()}")
    return redirect(f"/t/{tn}")

@app.route("/control-panel-8471/advance/<path:tracking_number>", methods=["POST"])
def admin_advance(tracking_number):
    if not session.get("admin"):
        return redirect("/control-panel-8471/login")
    conn = get_db()
    row = conn.execute("SELECT * FROM trackings WHERE tracking_number=?", (tracking_number,)).fetchone()
    if not row:
        conn.close()
        return redirect("/control-panel-8471")
    order = ["Shipment information sent to FedEx", "Picked up", "In transit",
             "Arrived at FedEx location", "Out for delivery", "Delivered"]
    try:
        idx = order.index(row["status"])
    except ValueError:
        idx = 0
    new_idx = min(idx + 1, len(order) - 1)
    new_status = order[new_idx]
    city, fac = random.choice(CITIES)
    now = datetime.datetime.now()
    details = "Left at front door - Signature not required" if new_status == "Delivered" else ""
    conn.execute("UPDATE trackings SET status=? WHERE tracking_number=?", (new_status, tracking_number))
    conn.commit()
    conn.close()
    add_event(tracking_number, now, f"{fac}, {city}", new_status, details)
    return redirect(f"/t/{tracking_number}")

@app.route("/control-panel-8471/delete/<path:tracking_number>")
def admin_delete(tracking_number):
    if not session.get("admin"):
        return redirect("/control-panel-8471/login")
    conn = get_db()
    conn.execute("DELETE FROM trackings WHERE tracking_number=?", (tracking_number,))
    conn.execute("DELETE FROM events WHERE tracking_number=?", (tracking_number,))
    conn.commit()
    conn.close()
    return redirect("/control-panel-8471")

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
