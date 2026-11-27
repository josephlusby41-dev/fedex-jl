import os
import sqlite3
import datetime
import random
import string
from functools import wraps
from flask import Flask, request, redirect, url_for, session, render_template_string, flash, abort

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

# Database configuration
DB_PATH = os.environ.get("DB_PATH", "/tmp/fedex.db")

# Admin credentials
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "Deebaby25!")

CITIES = ["MEMPHIS, TN", "DALLAS, TX", "ATLANTA, GA", "INDIANAPOLIS, IN", "OAKLAND, CA", "GREENVILLE, SC"]

SERVICES = [
    "FedEx Ground",
    "FedEx Express Saver",
    "FedEx 2Day",
    "FedEx Standard Overnight",
    "FedEx Priority Overnight",
    "FedEx First Overnight",
    "FedEx 2Day AM",
    "FedEx Home Delivery",
    "FedEx International Priority",
    "FedEx International Economy",
    "FedEx SmartPost",
    "FedEx Freight"
]

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fmt_ts(dt):
    return dt.strftime("%b %d, %Y %I:%M %p").upper()

def parse_dt(date_str, time_str):
    """Parse date (YYYY-MM-DD) and time (HH:MM) strings into datetime. Falls back to now."""
    try:
        return datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except Exception:
        return datetime.datetime.now()

def add_event_internal(c, tn, dt, location, description, details="", exception=0):
    c.execute("""INSERT INTO events (tracking_number, timestamp, location, description, details, exception)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (tn, fmt_ts(dt), location, description, details, exception))

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
        details TEXT,
        exception INTEGER DEFAULT 0
    )""")
    # Upgrade old databases that lack the exception column on events
    cols = [r[1] for r in c.execute("PRAGMA table_info(events)").fetchall()]
    if "exception" not in cols:
        c.execute("ALTER TABLE events ADD COLUMN exception INTEGER DEFAULT 0")
    # Upgrade old databases that lack the exception columns on trackings
    tcols = [r[1] for r in c.execute("PRAGMA table_info(trackings)").fetchall()]
    if "exception" not in tcols:
        c.execute("ALTER TABLE trackings ADD COLUMN exception TEXT")
    if "exception_at" not in tcols:
        c.execute("ALTER TABLE trackings ADD COLUMN exception_at TEXT")
    if "prev_status" not in tcols:
        c.execute("ALTER TABLE trackings ADD COLUMN prev_status TEXT")
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
            (tn, "ACME WIDGETS LLC", "MICHAEL HARRIS", "2814 OAK LN, AUSTIN TX 78704",
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
   <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' fill='%23ffffff'/><text x='16' y='23' font-size='14' font-weight='700' font-style='italic' text-anchor='middle' font-family='Arial'><tspan fill='%234d148c'>Fe</tspan><tspan fill='%23ff6600'>dx</tspan></text></svg>">
   <style>
        * { box-sizing: border-box; }
        body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 0; padding: 0; background: #ffffff; color: #333; }
        a { color: #4d148c; }
        header { background-color: #ffffff; border-bottom: 1px solid #e5e5e5; padding: 0; }
        .container { max-width: 1000px; margin: 0 auto; padding: 0 20px; }
        .header-content { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; }
        .logo-wrap { display: flex; align-items: flex-end; gap: 18px; }
        .logo-svg { height: 34px; display: block; }
        .logo-sub { font-size: 15px; color: #6b6b6b; font-weight: 400; letter-spacing: .5px; padding-bottom: 3px; border-left: 1px solid #ddd; padding-left: 18px; height: 26px; display: flex; align-items: center; }
        .top-links { font-size: 13px; }
        .top-links a { color: #6b6b6b; text-decoration: none; margin-left: 22px; }
        .top-links a:hover { color: #4d148c; }
        nav { background: #4d148c; }
        nav .container { display: flex; }
        nav a { color: white; text-decoration: none; padding: 12px 18px; font-size: 14px; font-weight: 600; display: block; }
        nav a:hover { background: #3a0f6b; }
        nav a.active { background: transparent; box-shadow: inset 0 -4px 0 #ff6600; }
        .main-content { background: white; min-height: 400px; padding: 40px 20px; }
        .search-box { text-align: center; margin-bottom: 30px; }
        .search-box h1 { font-size: 26px; margin-bottom: 6px; font-weight: 500; }
        .search-box h1 .fed { color: #4d148c; font-style: italic; font-weight: 800; letter-spacing: -1px; }
        .search-box h1 .ex { color: #ff6600; font-style: italic; font-weight: 800; letter-spacing: -1px; }
        .search-box .sub { color: #75757a; font-size: 15px; margin-bottom: 24px; }
        .input-group { display: inline-flex; gap: 10px; }
        input[type="text"] { padding: 12px 15px; width: 340px; border: 1px solid #bdbcbd; border-radius: 3px; font-size: 16px; }
        input[type="text"]:focus { outline: none; border-color: #4d148c; box-shadow: 0 0 0 2px rgba(77,20,140,0.15); }
        button { background-color: #ff6600; color: white; border: none; padding: 12px 30px; font-size: 15px; font-weight: bold; border-radius: 3px; cursor: pointer; }
        button:hover { background-color: #e55b00; }
        .error-msg { background-color: #fdf2f2; border-left: 4px solid #cc0000; color: #721c24; padding: 15px 18px; border-radius: 3px; margin-top: 20px; text-align: left; max-width: 600px; margin-left: auto; margin-right: auto; font-size: 14px; }
        .flash-msg { max-width: 900px; margin: 0 auto 20px; padding: 12px 18px; border-radius: 3px; font-size: 14px; background: #f0fff4; border-left: 4px solid #2e7d32; color: #2e7d32; }
        .flash-msg.error { background: #fdf2f2; border-left-color: #cc0000; color: #721c24; }
        .result-card { max-width: 820px; margin: 0 auto; border: 1px solid #e0e0e0; background: #fff; }
        .result-card.has-exception { border-color: #e0b3b3; }
        .result-header { padding: 22px; border-bottom: 1px solid #eee; background: #fafafa; }
        .result-header.exc { background: #fdf3f3; border-bottom: 1px solid #f0d0d0; }
        .result-header h2 { margin: 0; font-size: 14px; color: #75757a; font-weight: 500; text-transform: uppercase; letter-spacing: .5px; }
        .result-header .status { font-size: 22px; font-weight: 700; color: #333; margin-top: 6px; }
        .result-header .status.exc { color: #cc0000; }
        .result-header .eta { font-size: 14px; color: #75757a; margin-top: 4px; }
        .progress-header { display: flex; align-items: center; justify-content: center; gap: 12px; background: #fafafa; padding: 18px 22px 8px; }
        .progress-header .mini-logo { height: 22px; display: block; }
        .progress-header .ph { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: #75757a; font-weight: 600; }
        .progress-bar { display: flex; gap: 4px; padding: 0 22px 0; background: #fafafa; }
        .progress-bar span { flex: 1; height: 5px; background: #ddd; border-radius: 3px; }
        .progress-bar span.on { background: #ff6600; }
        .progress-bar span.exc { background: #cc0000; }
        .progress-labels { display: flex; justify-content: space-between; max-width: 820px; margin: 0 auto; padding: 6px 22px 16px; background: #fafafa; font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: .5px; }
        .progress-labels span.exc { color: #cc0000; font-weight: 700; }
        .exc-banner { background: #fdf2f2; border-left: 4px solid #cc0000; padding: 14px 18px; margin: 0 22px 20px; color: #721c24; font-size: 14px; border-radius: 3px; }
        .exc-banner strong { display: block; margin-bottom: 4px; font-size: 12px; text-transform: uppercase; letter-spacing: .6px; }
        .exc-time { font-size: 12px; color: #a15c5c; margin-top: 6px; }
        .result-details { padding: 20px 22px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 20px; font-size: 14px; }
        .detail-col strong { display: block; color: #75757a; font-size: 11px; margin-bottom: 4px; text-transform: uppercase; letter-spacing: .5px; font-weight: 600; }
        .timeline { padding: 22px; }
        .timeline h3 { font-size: 13px; text-transform: uppercase; color: #75757a; margin-bottom: 18px; letter-spacing: 1px; font-weight: 600; }
        .event { display: flex; gap: 0; padding-bottom: 16px; margin-bottom: 16px; border-bottom: 1px solid #f0f0f0; position: relative; }
        .event:last-child { border-bottom: none; }
        .event-marker { min-width: 26px; padding-top: 4px; }
        .event-marker .dot { width: 9px; height: 9px; border-radius: 50%; background: #ff6600; display: block; }
        .event.exception .event-marker .dot { background: #cc0000; }
        .event.exception .event-desc { color: #cc0000; }
        .event.exception .event-loc { color: #a33; }
        .event-time { min-width: 165px; font-size: 13px; color: #75757a; padding-top: 2px; }
        .event-info { flex: 1; }
        .event-desc { font-weight: bold; font-size: 14px; color: #333; }
        .event-loc { font-size: 13px; color: #75757a; margin-top: 2px; }
        .disclaimer { max-width: 820px; margin: 24px auto 0; font-size: 12px; color: #888; line-height: 1.5; }
        .adm-exc { background: #fdf2f2; border: 1px solid #e0b3b3; padding: 16px; margin-bottom: 20px; }
        .adm-exc h3 { margin-top: 0; color: #cc0000; font-size: 15px; text-transform: uppercase; letter-spacing: .5px; }
        .exc-live { color: #cc0000; font-weight: 700; margin: 0 0 10px; font-size: 14px; }
        .exc-live small { color: #a15c5c; font-weight: 400; }
        .exc-form { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
        .exc-form input[type="text"] { flex: 1; min-width: 180px; padding: 8px; width: auto; font-size: 14px; }
        .btn-red { background: #cc0000; color: #fff; border: none; padding: 8px 14px; cursor: pointer; font-weight: 700; border-radius: 3px; font-size: 13px; }
        .btn-red:hover { background: #a80000; }
        .btn-clear { background: #fff; color: #cc0000; border: 1px solid #cc0000; padding: 8px 14px; cursor: pointer; font-weight: 700; border-radius: 3px; font-size: 13px; }
        .btn-clear:hover { background: #fdf2f2; }
        .btn-mini { background: #4d148c; color: #fff; border: none; padding: 5px 10px; cursor: pointer; font-weight: 700; border-radius: 3px; font-size: 12px; }
        .btn-mini:hover { background: #3a0f6b; }
        .btn-mini.danger { background: #cc0000; }
        .btn-mini.danger:hover { background: #a80000; }
        .actions { display: flex; gap: 6px; flex-wrap: wrap; }
        footer { background: #4d148c; color: #fff; margin-top: 40px; }
        footer .fcontainer { max-width: 1000px; margin: 0 auto; padding: 26px 20px; }
        footer .flinks { display: flex; flex-wrap: wrap; gap: 8px 24px; font-size: 13px; margin-bottom: 18px; }
        footer .flinks a { color: #fff; text-decoration: none; opacity: .9; }
        footer .flinks a:hover { text-decoration: underline; }
        footer .tagline { font-size: 13px; opacity: .7; }
        footer .legal { font-size: 11px; opacity: .6; margin-top: 10px; line-height: 1.6; }
        @media (max-width: 600px) {
            .logo-sub { display: none; }
            .input-group { flex-direction: column; }
            input[type="text"] { width: 100%; }
            .event-time { min-width: 110px; }
        }
   </style>
</head>
<body>
   <header>
       <div class="container header-content">
            <div class="logo-wrap">
                <svg class="logo-svg" viewBox="0 0 600 120" xmlns="http://www.w3.org/2000/svg" aria-label="FedEx">
                  <text x="0" y="88" font-family="Arial, Helvetica, sans-serif" font-size="100" font-weight="bold" font-style="italic" letter-spacing="-6"><tspan fill="#4d148c">Fed</tspan><tspan fill="#ff6600">Ex</tspan></text>
                </svg>
                <span class="logo-sub">Tracking</span>
            </div>
            <div class="top-links">
                <a href="#">Log In</a>
                <a href="#">Support</a>
            </div>
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
       {% with messages = get_flashed_messages(with_categories=true) %}
           {% for category, message in messages %}
               <div class="flash-msg{% if category == 'error' %} error{% endif %}">{{ message }}</div>
           {% endfor %}
       {% endwith %}
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
   <h1><span class="fed">Fed</span><span class="ex">Ex</span> Tracking</h1>
   <div class="sub">Enter your tracking number to see the latest status of your shipment.</div>
   <form action="/" method="post" class="input-group">
        <input type="text" name="tracking_number" value="{{ tn }}" placeholder="Enter tracking number" required autofocus>
        <button type="submit">TRACK</button>
   </form>
   {% if error %}<div class="error-msg">{{ error }}</div>{% endif %}
</div>

{% if tracking %}
{% set is_exc = tracking['exception'] %}
<div class="result-card{% if is_exc %} has-exception{% endif %}">
   <div class="result-header{% if is_exc %} exc{% endif %}">
       <h2>Tracking Number: {{ tracking['tracking_number'] }}</h2>
       <div class="status{% if is_exc %} exc{% endif %}">{{ tracking['status'] }}</div>
       <div class="eta{% if is_exc %} exc{% endif %}">{% if is_exc %}Estimated Delivery: <strong>Delayed</strong>{% else %}Estimated Delivery: <strong>{{ tracking['eta'] }}</strong>{% endif %}</div>
   </div>
    <div class="progress-header">
        <svg class="mini-logo" viewBox="0 0 600 120" xmlns="http://www.w3.org/2000/svg" aria-label="FedEx">
          <text x="0" y="88" font-family="Arial, Helvetica, sans-serif" font-size="100" font-weight="bold" font-style="italic" letter-spacing="-6"><tspan fill="#4d148c">Fed</tspan><tspan fill="#ff6600">Ex</tspan></text>
        </svg>
        <span class="ph">Shipment Progress</span>
    </div>
    <div class="progress-bar">
        <span class="{% if is_exc %}exc{% elif 'Delivered' in tracking['status'] or 'Out for delivery' in tracking['status'] or 'In transit' in tracking['status'] %}on{% endif %}"></span>
        <span class="{% if not is_exc and ('Out for delivery' in tracking['status'] or 'Delivered' in tracking['status']) %}on{% endif %}"></span>
        <span class="{% if not is_exc and 'Delivered' in tracking['status'] %}on{% endif %}"></span>
    </div>
    <div class="progress-labels">
        <span class="{% if is_exc %}exc{% endif %}">In Transit</span>
        <span>Out for Delivery</span>
        <span>Delivered</span>
    </div>
   {% if is_exc %}
   <div class="exc-banner">
       <strong>&#9888; Delivery Exception</strong>
       {{ tracking['exception'] }}
       {% if tracking['exception_at'] %}<div class="exc-time">Reported {{ tracking['exception_at'] }}</div>{% endif %}
   </div>
   {% endif %}
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
       <div class="event{% if e['exception'] %} exception{% endif %}">
           <div class="event-marker"><span class="dot"></span></div>
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
    Shipment tracking information is provided as a convenience. Delivery times are estimates and not guaranteed. For assistance, contact FedEx Customer Service at 1-800-555-0187.
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
           <select name="service_type" style="padding: 8px;" required>
               {% for s in services %}
               <option value="{{ s }}">{{ s }}</option>
               {% endfor %}
           </select>
           <input type="text" name="weight" placeholder="Weight (e.g. 4.2 lbs)" style="padding: 8px;" required>
           <input type="text" name="pieces" placeholder="Pieces" style="padding: 8px;" required>
           <input type="text" name="reference" placeholder="Reference (auto if blank)" style="padding: 8px;">
           <input type="text" name="origin_city" placeholder="Origin City (e.g. GREENVILLE, SC)" style="padding: 8px;" required>
           <input type="text" name="status" placeholder="Initial Status (e.g. In transit - on time)" style="padding: 8px;" required>
           <label style="font-size: 13px; color: #555;">Shipment Date &amp; Time</label>
           <div style="display: flex; gap: 10px;">
               <input type="date" name="ship_date" value="{{ today }}" style="padding: 8px; flex: 1;">
               <input type="time" name="ship_time" value="{{ now_time }}" style="padding: 8px; flex: 1;">
           </div>
           <label style="font-size: 13px; color: #555;">ETA Date</label>
           <input type="date" name="eta_date" value="{{ eta_default }}" style="padding: 8px;">
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
           <tr style="border-bottom: 1px solid #eee;{% if t['exception'] %} background: #fdf7f7;{% endif %}">
               <td style="padding: 10px;"><a href="/control-panel-8471/track/{{ t['tracking_number'] }}">{{ t['tracking_number'] }}</a></td>
               <td style="padding: 10px;">{{ t['recipient_name'] }}</td>
               <td style="padding: 10px;{% if t['exception'] %} color: #cc0000; font-weight: bold;{% endif %}">{{ t['status'] }}</td>
               <td style="padding: 10px;">{{ t['eta'] }}</td>
               <td style="padding: 10px;">
                   <div class="actions">
                       <a href="/control-panel-8471/track/{{ t['tracking_number'] }}">Manage</a>
                           <form action="/admin/advance/{{ t['tracking_number'] }}" method="post" style="display:inline;">
        <button type="submit" class="btn btn-small">Advance Status ▶</button>
    </form>
    <form action="/admin/delete/{{ t['tracking_number'] }}" method="post" style="display:inline;" onsubmit="return confirm('Delete this shipment?');">
        <button type="submit" class="btn btn-small btn-danger">Delete ✕</button>
    </form>
</td>
        </tr>
        {% endfor %}
    </table>

    <h2>All Shipments</h2>
    <table>
        <tr>
            <th>Tracking #</th>
            <th>Recipient</th>
            <th>Origin → Destination</th>
            <th>Status</th>
            <th>ETA</th>
            <th>Exception</th>
            <th>Actions</th>
        </tr>
        {% for s in shipments %}
        <tr>
            <td><a href="/admin/track/{{ s['tracking_number'] }}">{{ s['tracking_number'] }}</a></td>
            <td>{{ s['recipient_name'] }}</td>
            <td>{{ s['origin_city'] }}, {{ s['origin_state'] }} → {{ s['dest_city'] }}, {{ s['dest_state'] }}</td>
            <td>{{ s['status'] }}</td>
            <td>{{ s['eta_date'] }}</td>
            <td>{{ s['exception_reason'] or '—' }}</td>
            <td>
                <form action="/admin/update/{{ s['tracking_number'] }}" method="post" class="inline-form">
                    <select name="status">
                        {% for st in ['Label Created', 'Picked Up', 'In Transit', 'Out for Delivery', 'Delivered', 'Exception'] %}
                        <option value="{{ st }}" {% if s['status'] == st %}selected{% endif %}>{{ st }}</option>
                        {% endfor %}
                    </select>
                    <input type="date" name="eta_date" value="{{ s['eta_date'] }}">
                    <input type="text" name="location" placeholder="Current location" value="{{ s['current_location'] or '' }}">
                    <button type="submit" class="btn btn-small">Update</button>
                </form>
                <form action="/admin/delete/{{ s['tracking_number'] }}" method="post" style="display:inline;" onsubmit="return confirm('Delete this shipment?');">
                    <button type="submit" class="btn btn-small btn-danger">Delete</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
</div>
</body>
</html>
"""


# ---------------- ADMIN ROUTES ----------------

@app.route("/admin", methods=["GET"])
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    db = get_db()
    active = db.execute("SELECT * FROM shipments WHERE status != 'Delivered' ORDER BY eta_date").fetchall()
    all_shipments = db.execute("SELECT * FROM shipments ORDER BY created_at DESC").fetchall()
    return render_template_string(ADMIN_DASHBOARD_TEMPLATE, shipments=all_shipments, active=active)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        error = "Invalid credentials. Try again."
    return render_template_string(ADMIN_LOGIN_TEMPLATE, error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin/new", methods=["POST"])
def admin_new_shipment():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    tracking_number = request.form.get("tracking_number", "").strip()
    if not tracking_number:
        tracking_number = "FX" + "".join(random.choices(string.digits, k=10))
    db = get_db()
    existing = db.execute("SELECT 1 FROM shipments WHERE tracking_number = ?", (tracking_number,)).fetchone()
    if existing:
        flash_dup = True
    else:
        db.execute(
            """INSERT INTO shipments
            (tracking_number, recipient_name, recipient_email, recipient_phone,
             origin_city, origin_state, dest_city, dest_state, status, eta_date,
             current_location, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tracking_number,
                request.form.get("recipient_name", ""),
                request.form.get("recipient_email", ""),
                request.form.get("recipient_phone", ""),
                request.form.get("origin_city", ""),
                request.form.get("origin_state", ""),
                request.form.get("dest_city", ""),
                request.form.get("dest_state", ""),
                request.form.get("status", "Label Created"),
                request.form.get("eta_date", ""),
                request.form.get("current_location", ""),
                request.form.get("notes", ""),
            ),
        )
        db.commit()
        flash_dup = False
    db.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/update/<tn>", methods=["POST"])
def admin_update_shipment(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    db = get_db()
    db.execute(
        """UPDATE shipments SET status = ?, eta_date = ?, current_location = ? WHERE tracking_number = ?""",
        (
            request.form.get("status", "In Transit"),
            request.form.get("eta_date", ""),
            request.form.get("location", ""),
            tn,
        ),
    )
    db.commit()
    db.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/advance/<tn>", methods=["POST"])
def admin_advance_shipment(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    flow = ["Label Created", "Picked Up", "In Transit", "Out for Delivery", "Delivered"]
    db = get_db()
    row = db.execute("SELECT status FROM shipments WHERE tracking_number = ?", (tn,)).fetchone()
    if row and row["status"] in flow:
        idx = flow.index(row["status"])
        if idx < len(flow) - 1:
            db.execute("UPDATE shipments SET status = ? WHERE tracking_number = ?", (flow[idx + 1], tn))
            db.commit()
    db.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete/<tn>", methods=["POST"])
def admin_delete_shipment(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    db = get_db()
    db.execute("DELETE FROM shipments WHERE tracking_number = ?", (tn,))
    db.execute("DELETE FROM tracking_events WHERE tracking_number = ?", (tn,))
    db.commit()
    db.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/track/<tn>", methods=["GET", "POST"])
def admin_track(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    db = get_db()
    shipment = db.execute("SELECT * FROM shipments WHERE tracking_number = ?", (tn,)).fetchone()
    if not shipment:
        db.close()
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        status = request.form.get("status", "In Transit")
        location = request.form.get("location", "")
        details = request.form.get("details", "")
        exception = "exception" in request.form
        db.execute(
            "INSERT INTO tracking_events (tracking_number, status, location, details, is_exception) VALUES (?, ?, ?, ?, ?)",
            (tn, status, location, details, 1 if exception else 0),
        )
        db.execute("UPDATE shipments SET status = ?, current_location = ? WHERE tracking_number = ?", (status, location, tn))
        db.commit()

    events = db.execute(
        "SELECT * FROM tracking_events WHERE tracking_number = ? ORDER BY event_time DESC",
        (tn,),
    ).fetchall()
    db.close()
    return render_template_string(ADMIN_TRACK_TEMPLATE, s=shipment, events=events)


@app.route("/admin/set_exception/<tn>", methods=["POST"])
def admin_set_exception(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    reason = request.form.get("exception_reason", "Delivery exception")
    db = get_db()
    db.execute("UPDATE shipments SET status = 'Exception', exception_reason = ? WHERE tracking_number = ?", (reason, tn))
    db.execute(
        "INSERT INTO tracking_events (tracking_number, status, location, details, is_exception) VALUES (?, ?, ?, ?, 1)",
        (tn, "Exception", request.form.get("location", ""), reason),
    )
    db.commit()
    db.close()
    return redirect(url_for("admin_track", tn=tn))


@app.route("/admin/clear_exception/<tn>", methods=["POST"])
def admin_clear_exception(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    db = get_db()
    db.execute("UPDATE shipments SET status = 'In Transit', exception_reason = NULL WHERE tracking_number = ?", (tn,))
    db.commit()
    db.close()
    return redirect(url_for("admin_track", tn=tn))


# ---------------- MAIN ----------------

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
