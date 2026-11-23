import os
import sqlite3
import datetime
import random
import string
from flask import Flask, request, redirect, url_for, session, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

# Database configuration
DB_PATH = os.environ.get("DB_PATH", "/tmp/fedex.db")

# Admin credentials
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "Deebaby25!")

CITIES = ["MEMPHIS, TN", "DALLAS, TX", "ATLANTA, GA", "INDIANAPOLIS, IN", "OAKLAND, CA", "GREENVILLE, SC"]

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fmt_ts(dt):
    return dt.strftime("%b %d, %Y %I:%M %p").upper()

def add_event_internal(c, tn, dt, location, description, details=""):
    c.execute("""INSERT INTO events (tracking_number, timestamp, location, description, details)
                 VALUES (?, ?, ?, ?, ?)""",
              (tn, fmt_ts(dt), location, description, details))

def init_db():
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
             "FedEx Ground", "4.2 lbs", "1", "PO-88213", "In transit - on time",
             fmt_ts(now), eta_str))
        add_event_internal(c, tn, now - datetime.timedelta(hours=6), "DALLAS, TX", "Picked up", "Tendered at FedEx origin facility")
        add_event_internal(c, tn, now - datetime.timedelta(hours=3), "DALLAS, TX", "In transit", "Departed FedEx location")
        conn.commit()
    conn.close()

def rand_ref():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
   <meta charset="UTF-8">
   <meta name="viewport" content="width=device-width, initial-scale=1.0">
   <title>{{ title }}</title>
   <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' fill='%234d148c' rx='4'/><text x='16' y='22' font-size='13' font-weight='700' font-style='italic' text-anchor='middle' fill='white' font-family='Arial'>Fx</text></svg>">
   <style>
        * { box-sizing: border-box; }
        body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 0; padding: 0; background: linear-gradient(#f8f8f8, #f2f2f2); color: #333; }
        a { color: #4d148c; }
        header { background-color: #ffffff; border-bottom: 1px solid #e5e5e5; padding: 0; }
        .container { max-width: 1000px; margin: 0 auto; padding: 0 20px; }
        .header-content { display: flex; justify-content: space-between; align-items: center; padding: 14px 0; }
        .logo { font-size: 30px; font-weight: 800; letter-spacing: -2px; font-style: italic; }
        .logo .fed { color: #4d148c; }
        .logo .ex { color: #ff6600; }
        .logo small { display: block; font-size: 9px; font-style: normal; letter-spacing: 2px; color: #666; text-transform: uppercase; margin-top: -2px; }
        nav { background: #4d148c; }
        nav .container { display: flex; }
        nav a { color: white; text-decoration: none; padding: 12px 18px; font-size: 14px; font-weight: 600; display: block; }
        nav a:hover { background: #3a0f6b; }
        nav a.active { background: #ff6600; }
        .main-content { background: white; min-height: 400px; padding: 40px 20px; margin-top: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); border-radius: 2px; }
        .search-box { text-align: center; margin-bottom: 30px; }
        .search-box h1 { font-size: 26px; margin-bottom: 6px; color: #333; font-weight: 600; }
        .search-box .sub { color: #777; font-size: 14px; margin-bottom: 24px; }
        .input-group { display: inline-flex; gap: 10px; }
        input[type="text"] { padding: 12px 15px; width: 320px; border: 1px solid #bbb; border-radius: 3px; font-size: 16px; }
        input[type="text"]:focus { outline: none; border-color: #4d148c; box-shadow: 0 0 0 2px rgba(77,20,140,0.15); }
        button { background-color: #ff6600; color: white; border: none; padding: 12px 28px; font-size: 15px; font-weight: bold; border-radius: 3px; cursor: pointer; }
        button:hover { background-color: #e55b00; }
        .error-msg { background-color: #fdf2f2; border-left: 4px solid #cc0000; color: #721c24; padding: 15px 18px; border-radius: 3px; margin-top: 20px; text-align: left; max-width: 600px; margin-left: auto; margin-right: auto; font-size: 14px; }
        .result-card { max-width: 820px; margin: 0 auto; border: 1px solid #ddd; background: #fff; }
        .result-header { padding: 22px; border-bottom: 1px solid #eee; background: #fafafa; }
        .result-header h2 { margin: 0; font-size: 16px; color: #666; font-weight: 500; }
        .result-header .status { font-size: 20px; font-weight: 700; color: #333; margin-top: 4px; }
        .result-header .eta { font-size: 14px; color: #666; margin-top: 4px; }
        .progress-bar { display: flex; gap: 4px; padding: 0 22px 16px; background: #fafafa; }
        .progress-bar span { flex: 1; height: 5px; background: #ddd; border-radius: 3px; }
        .progress-bar span.on { background: #ff6600; }
        .progress-labels { display: flex; justify-content: space-between; max-width: 820px; margin: 0 auto; padding: 6px 22px 0; font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: .5px; }
        .result-details { padding: 20px 22px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 20px; font-size: 14px; }
        .detail-col strong { display: block; color: #999; font-size: 11px; margin-bottom: 4px; text-transform: uppercase; letter-spacing: .5px; }
        .timeline { padding: 22px; }
        .timeline h3 { font-size: 13px; text-transform: uppercase; color: #666; margin-bottom: 15px; letter-spacing: 1px; }
        .event { display: flex; gap: 20px; padding-bottom: 15px; margin-bottom: 15px; border-bottom: 1px solid #f0f0f0; }
        .event:last-child { border-bottom: none; }
        .event-time { min-width: 150px; font-size: 13px; color: #666; }
        .event-info { flex: 1; }
        .event-desc { font-weight: bold; font-size: 14px; color: #333; }
        .event-loc { font-size: 13px; color: #666; margin-top: 2px; }
        .event-loc::before { content:"\\1F4CD "; margin-right: 2px; }
        .disclaimer { max-width: 820px; margin: 24px auto 0; font-size: 12px; color: #888; line-height: 1.5; }
        footer { background: #4d148c; color: #fff; margin-top: 40px; }
        footer .fcontainer { max-width: 1000px; margin: 0 auto; padding: 26px 20px; }
        footer .flinks { display: flex; flex-wrap: wrap; gap: 8px 24px; font-size: 13px; margin-bottom: 18px; }
        footer .flinks a { color: #fff; text-decoration: none; opacity: .9; }
        footer .flinks a:hover { text-decoration: underline; }
        footer .tagline { font-size: 13px; opacity: .7; }
        footer .legal { font-size: 11px; opacity: .6; margin-top: 10px; line-height: 1.6; }
   </style>
</head>
<body>
   <header>
       <div class="container header-content">
            <div class="logo"><span class="fed">Fed</span><span class="ex">Ex</span><small>Tracking</small></div>
       </div>
   </header>
    <nav>
        <div class="container">
            <a href="/" class="active">TRACKING</a>
            <a href="#">SHIPPING</a>
            <a href="#">LOCATIONS</a>
            <a href="#">SUPPORT</a>
        </div>
    </nav>

   <div class="container main-content">
       {{ content | safe }}
   </div>

   <footer>
        <div class="fcontainer">
            <div class="flinks">
                <a href="#">About FedEx</a>
                <a href="#">Careers</a>
                <a href="#">Privacy &amp; Security</a>
                <a href="#">Terms of Use</a>
                <a href="#">Site Map</a>
                <a href="#">Contact Us</a>
            </div>
            <div class="tagline">FedEx. Solutions that matter.</div>
            <div class="legal">&copy; 1995-2026 FedEx. All rights reserved. This site is protected by reCAPTCHA and the Google Privacy Policy and Terms of Service apply.</div>
        </div>
   </footer>
</body>
</html>
"""

INDEX_TEMPLATE = """
<div class="search-box">
   <h1>Track Your Shipment</h1>
   <div class="sub">Enter your tracking number to see the latest status of your shipment.</div>
   <form action="/" method="post" class="input-group">
        <input type="text" name="tracking_number" value="{{ tn }}" placeholder="Enter tracking number" required autofocus>
        <button type="submit">TRACK</button>
   </form>
   {% if error %}<div class="error-msg">{{ error }}</div>{% endif %}
</div>

{% if tracking %}
<div class="result-card">
   <div class="result-header">
       <h2>Tracking Number: {{ tracking['tracking_number'] }}</h2>
       <div class="status">{{ tracking['status'] }}</div>
       <div class="eta">Estimated Delivery: <strong>{{ tracking['eta'] }}</strong></div>
   </div>
    <div class="progress-bar">
        <span class="{% if 'Delivered' in tracking['status'] or 'Out for delivery' in tracking['status'] or 'In transit' in tracking['status'] %}on{% endif %}"></span>
        <span class="{% if 'Out for delivery' in tracking['status'] or 'Delivered' in tracking['status'] %}on{% endif %}"></span>
        <span class="{% if 'Delivered' in tracking['status'] %}on{% endif %}"></span>
    </div>
    <div class="progress-labels"><span>In Transit</span><span>Out for Delivery</span><span>Delivered</span></div>
   <div class="result-details">
       <div class="detail-col">
           <strong>From</strong>
           {{ tracking['sender_name'] }}
       </div>
       <div class="detail-col">
           <strong>To</strong>
           {{ tracking['recipient_name'] }}<br>
           {{ tracking['recipient_address'] }}
       </div>
       <div class="detail-col">
           <strong>Service</strong>
           {{ tracking['service_type'] }}
       </div>
       <div class="detail-col">
           <strong>Weight</strong>
           {{ tracking['weight'] }}
       </div>
   </div>
   <div class="timeline">
       <h3>Travel History</h3>
       {% for e in events %}
       <div class="event">
           <div class="event-time">{{ e['timestamp'] }}</div>
           <div class="event-info">
               <div class="event-desc">{{ e['description'] }}</div>
                <div class="event-loc">{{ e['location'] }}{% if e['details'] %} - {{ e['details'] }}{% endif %}</div>
           </div>
       </div>
       {% endfor %}
   </div>
</div>
<div class="disclaimer">
    Shipment tracking information is provided as a convenience. Delivery times are estimates and not guaranteed. For assistance, contact FedEx Customer Service at 1-800-GoFedEx.
</div>
{% endif %}
"""

ADMIN_DASHBOARD_TEMPLATE = """
<div style="max-width: 900px; margin: 0 auto;">
   <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
       <h2 style="margin: 0; color: #4d148c;">Admin Dashboard</h2>
        <a href="/control-panel-8471/logout" style="color: #666; text-decoration: none; font-size: 14px;">Logout</a>
   </div>
   <div style="background: #f9f9f9; padding: 20px; border: 1px solid #ddd; margin-bottom: 30px;">
       <h3 style="margin-top: 0;">Create New Shipment</h3>
       <form action="/admin/create" method="post" style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
           <input type="text" name="tracking_number" placeholder="Tracking Number (auto if blank)" style="padding: 8px;">
           <input type="text" name="sender_name" placeholder="Sender Name" style="padding: 8px;" required>
           <input type="text" name="recipient_name" placeholder="Recipient Name" style="padding: 8px;" required>
           <input type="text" name="recipient_address" placeholder="Recipient Address" style="padding: 8px;" required>
           <input type="text" name="service_type" placeholder="Service Type (e.g. FedEx Ground)" style="padding: 8px;" required>
           <input type="text" name="weight" placeholder="Weight (e.g. 4.2 lbs)" style="padding: 8px;" required>
           <input type="text" name="pieces" placeholder="Pieces" style="padding: 8px;" required>
           <input type="text" name="reference" placeholder="Reference (auto if blank)" style="padding: 8px;">
           <input type="text" name="origin_city" placeholder="Origin City (e.g. GREENVILLE, SC)" style="padding: 8px;" required>
           <input type="text" name="status" placeholder="Initial Status (e.g. In transit - on time)" style="padding: 8px;" required>
           <div style="grid-column: 1 / -1;">
               <button type="submit" style="width: 100%;">Create Shipment</button>
           </div>
       </form>
   </div>
    <h3>Existing Shipments</h3>
   <table style="width: 100%; border-collapse: collapse; background: white; border: 1px solid #ddd;">
       <thead>
           <tr style="background: #4d148c; color: white; text-align: left;">
               <th style="padding: 10px;">Tracking #</th>
               <th style="padding: 10px;">Recipient</th>
               <th style="padding: 10px;">Status</th>
               <th style="padding: 10px;">ETA</th>
               <th style="padding: 10px;">Actions</th>
           </tr>
       </thead>
       <tbody>
           {% for t in trackings %}
           <tr style="border-bottom: 1px solid #eee;">
               <td style="padding: 10px;"><a href="/control-panel-8471/track/{{ t['tracking_number'] }}">{{ t['tracking_number'] }}</a></td>
               <td style="padding: 10px;">{{ t['recipient_name'] }}</td>
               <td style="padding: 10px;">{{ t['status'] }}</td>
               <td style="padding: 10px;">{{ t['eta'] }}</td>
               <td style="padding: 10px;"><a href="/control-panel-8471/track/{{ t['tracking_number'] }}">Manage</a></td>
           </tr>
           {% endfor %}
       </tbody>
   </table>
</div>
"""

ADMIN_TRACK_TEMPLATE = """
<div style="max-width: 900px; margin: 0 auto;">
    <a href="/control-panel-8471" style="color: #4d148c; text-decoration: none; font-size: 14px;">&larr; Back to Dashboard</a>
   <h2 style="color: #4d148c;">Manage: {{ tracking['tracking_number'] }}</h2>

   <div style="background: #f9f9f9; padding: 20px; border: 1px solid #ddd; margin-bottom: 20px;">
       <p><strong>Status:</strong> {{ tracking['status'] }}</p>
       <p><strong>ETA:</strong> {{ tracking['eta'] }}</p>
        <p><strong>Recipient:</strong> {{ tracking['recipient_name'] }} - {{ tracking['recipient_address'] }}</p>
       <form action="/admin/update/{{ tracking['tracking_number'] }}" method="post" style="display: flex; gap: 10px; margin-top: 15px;">
           <input type="text" name="status" value="{{ tracking['status'] }}" placeholder="New status" style="flex: 1; padding: 8px;">
           <button type="submit" style="background: #4d148c; color: white; border: none; padding: 8px 15px; cursor: pointer;">Update Status</button>
       </form>
   </div>

   <h3 style="color: #4d148c;">Add Event</h3>
   <form action="/admin/add_event/{{ tracking['tracking_number'] }}" method="post" style="background: #f9f9f9; padding: 20px; border: 1px solid #ddd; margin-bottom: 30px; display: grid; gap: 10px;">
       <input type="text" name="location" placeholder="Location (e.g. MEMPHIS, TN)" style="padding: 8px;" required>
       <input type="text" name="description" placeholder="Description (e.g. Arrived at FedEx location)" style="padding: 8px;" required>
       <input type="text" name="details" placeholder="Details (optional)" style="padding: 8px;">
       <button type="submit" style="background: #ff6600; color: white; border: none; padding: 10px; cursor: pointer; font-weight: bold;">Add Event</button>
   </form>

   <h3 style="color: #4d148c;">Shipment Events</h3>
   <div style="background: white; border: 1px solid #ddd; padding: 20px;">
       {% for e in events %}
       <div style="padding: 10px 0; border-bottom: 1px solid #f0f0f0;">
            <strong>{{ e['timestamp'] }}</strong> - {{ e['description'] }} ({{ e['location'] }})
           {% if e['details'] %}<br><small style="color: #666;">{{ e['details'] }}</small>{% endif %}
       </div>
       {% endfor %}
   </div>
</div>
"""

ADMIN_LOGIN_TEMPLATE = """
<div style="max-width: 400px; margin: 60px auto; background: white; border: 1px solid #ddd; padding: 30px; box-shadow: 0 1px 4px rgba(0,0,0,0.08);">
    <h2 style="color: #4d148c; margin-top: 0;">Admin Login</h2>
    {% if error %}<div class="error-msg" style="margin-top: 0;">{{ error }}</div>{% endif %}
    <form action="/control-panel-8471/login" method="post" style="display: grid; gap: 12px; margin-top: 15px;">
        <input type="text" name="username" placeholder="Username" style="padding: 10px;" required>
        <input type="password" name="password" placeholder="Password" style="padding: 10px;" required>
        <button type="submit" style="width: 100%;">Login</button>
    </form>
</div>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    tracking = None
    events = []
    error = None
    tn = request.form.get("tracking_number", "").strip() if request.method == "POST" else ""
    if tn:
        conn = get_db()
        tracking = conn.execute("SELECT * FROM trackings WHERE tracking_number = ?", (tn,)).fetchone()
        if tracking:
            events = conn.execute(
                "SELECT * FROM events WHERE tracking_number = ? ORDER BY id DESC", (tn,)
            ).fetchall()
        else:
            error = "We could not find a shipment matching this tracking number. Please check the number and try again."
        conn.close()

    title = "Tracking Results | FedEx" if tracking else "Tracking | FedEx"
    content = render_template_string(INDEX_TEMPLATE, tracking=tracking, events=events, error=error, tn=tn)
    return render_template_string(BASE_TEMPLATE, content=content, title=title)

@app.route("/control-panel-8471")
def admin():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    trackings = conn.execute("SELECT * FROM trackings ORDER BY id DESC").fetchall()
    conn.close()
    content = render_template_string(ADMIN_DASHBOARD_TEMPLATE, trackings=trackings)
    return render_template_string(BASE_TEMPLATE, content=content, title="Admin Dashboard")

@app.route("/control-panel-8471/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USER and request.form.get("password") == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "Invalid credentials."
    content = render_template_string(ADMIN_LOGIN_TEMPLATE, error=error)
    return render_template_string(BASE_TEMPLATE, content=content, title="Admin Login")

@app.route("/control-panel-8471/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

@app.route("/admin/create", methods=["POST"])
def admin_create():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    now = datetime.datetime.now()
    tn = request.form.get("tracking_number", "").strip() or "".join(random.choices(string.digits, k=12))
    reference = request.form.get("reference", "").strip() or rand_ref()
    city = request.form.get("origin_city", "").strip() or random.choice(CITIES)
    facility = f"FedEx location in {city}"
    eta = now + datetime.timedelta(days=random.randint(1, 5))
    eta_str = eta.strftime("%b %d") + " by 4:30 pm"
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO trackings
            (tracking_number, sender_name, recipient_name, recipient_address, service_type, weight, pieces, reference, status, created_at, eta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tn, request.form.get("sender_name"), request.form.get("recipient_name"),
             request.form.get("recipient_address"), request.form.get("service_type"),
             request.form.get("weight"), request.form.get("pieces"), reference,
             request.form.get("status"), fmt_ts(now), eta_str))
        add_event_internal(c, tn, now, city, "Shipment information sent to FedEx",
                           facility + " - Reference: " + rand_ref())
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for("admin"))

@app.route("/control-panel-8471/track/<tn>")
def admin_track(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    tracking = conn.execute("SELECT * FROM trackings WHERE tracking_number = ?", (tn,)).fetchone()
    events = conn.execute("SELECT * FROM events WHERE tracking_number = ? ORDER BY id DESC", (tn,)).fetchall()
    conn.close()
    content = render_template_string(ADMIN_TRACK_TEMPLATE, tracking=tracking, events=events)
    return render_template_string(BASE_TEMPLATE, content=content, title="Manage Shipment")

@app.route("/admin/update/<tn>", methods=["POST"])
def admin_update(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    conn.execute("UPDATE trackings SET status = ? WHERE tracking_number = ?", (request.form.get("status"), tn))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_track", tn=tn))

@app.route("/admin/add_event/<tn>", methods=["POST"])
def admin_add_event(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    add_event_internal(conn.cursor(), tn, datetime.datetime.now(),
                       request.form.get("location"), request.form.get("description"),
                       request.form.get("details", ""))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_track", tn=tn))

@app.route("/admin/advance/<tn>", methods=["POST"])
def admin_advance(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    status_flow = ["Shipment information sent to FedEx", "Picked up", "In transit - on time",
                   "In transit - on time", "Out for delivery", "Delivered"]
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT status FROM trackings WHERE tracking_number = ?", (tn,)).fetchone()
    if row:
        try:
            idx = status_flow.index(row["status"])
            new_status = status_flow[min(idx + 1, len(status_flow) - 1)]
        except ValueError:
            new_status = "In transit - on time"
        now = datetime.datetime.now()
        city, facility = random.choice(CITIES), "FedEx facility"
        c.execute("UPDATE trackings SET status = ? WHERE tracking_number = ?", (new_status, tn))
        details = "Delivered - Signed for by: FRONT DESK" if new_status == "Delivered" else facility
        add_event_internal(c, tn, now, city, new_status, details)
        if new_status == "Delivered":
            c.execute("UPDATE trackings SET eta = ? WHERE tracking_number = ?", ("Delivered " + fmt_ts(now), tn))
        conn.commit()
    conn.close()
    return redirect(url_for("admin"))

# Initialize database on startup
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
