import os
import sqlite3
import random
import string
import datetime
from flask import Flask, request, render_template_string, redirect, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret-key-change-this")

# Database configuration
DB_PATH = os.environ.get("DB_PATH", "/tmp/fedex.db")

# Admin credentials (Change these in your Render Environment Variables for security)
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "Deebaby25!")

# Mock Data Configuration
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

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    conn = get_db()
    c = conn.cursor()
    
    # Create tables if they don't exist
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
    
    # Seed demo data if table is empty
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
             fmt_ts(now), eta_str)
        )
        
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

# --- HTML TEMPLATES ---

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        body { font-family: 'Roboto', Arial, sans-serif; margin: 0; padding: 0; background-color: #f2f2f2; color: #333; }
        header { background-color: #4d148c; color: white; padding: 15px 0; }
        .container { max-width: 1000px; margin: 0 auto; padding: 0 20px; }
        .header-content { display: flex; justify-content: space-between; align-items: center; }
        .logo { font-size: 24px; font-weight: bold; letter-spacing: -1px; }
        .logo span { color: #ff6600; }
        nav a { color: white; text-decoration: none; margin-left: 20px; font-size: 14px; font-weight: 500; }
        nav a:hover { text-decoration: underline; }
        
        .main-content { background: white; min-height: 400px; padding: 40px 20px; margin-top: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
        
        .search-box { text-align: center; margin-bottom: 30px; }
        .search-box h1 { font-size: 28px; margin-bottom: 20px; color: #333; }
        .input-group { display: inline-flex; gap: 10px; }
        input[type="text"] { padding: 12px 15px; width: 300px; border: 1px solid #ccc; border-radius: 4px; font-size: 16px; }
        button { background-color: #ff6600; color: white; border: none; padding: 12px 25px; font-size: 16px; font-weight: bold; border-radius: 4px; cursor: pointer; }
        button:hover { background-color: #e55b00; }
        
        .error-msg { background-color: #fcebeb; border: 1px solid #f5c6cb; color: #721c24; padding: 15px; border-radius: 4px; margin-top: 20px; text-align: left; max-width: 600px; margin-left: auto; margin-right: auto; }
        
        .result-card { max-width: 800px; margin: 0 auto; border: 1px solid #ddd; background: #fff; }
        .result-header { padding: 20px; border-bottom: 1px solid #eee; }
        .result-header h2 { margin: 0; font-size: 20px; color: #4d148c; }
        .result-header .status { font-size: 18px; font-weight: bold; color: #333; margin-top: 5px; }
        .result-header .eta { font-size: 14px; color: #666; margin-top: 5px; }
        
        .result-details { padding: 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; font-size: 14px; }
        .detail-col strong { display: block; color: #666; font-size: 12px; margin-bottom: 4px; }
        
        .timeline { padding: 20px; }
        .timeline h3 { font-size: 14px; text-transform: uppercase; color: #666; margin-bottom: 15px; letter-spacing: 1px; }
        .event { display: flex; gap: 20px; padding-bottom: 15px; margin-bottom: 15px; border-bottom: 1px solid #f0f0f0; }
        .event:last-child { border-bottom: none; }
        .event-time { min-width: 140px; font-size: 13px; color: #666; }
        .event-info { flex: 1; }
        .event-desc { font-weight: bold; font-size: 14px; color: #333; }
        .event-loc { font-size: 13px; color: #666; margin-top: 2px; }
        
        footer { text-align: center; padding: 20px; font-size: 12px; color: #666; margin-top: 40px; }
    </style>
</head>
<body>
    <header>
        <div class="container header-content">
            <div class="logo">Fed<span>Ex</span></div>
            <nav>
                <a href="/">Tracking</a>
                <a href="#">Shipping</a>
                <a href="#">Locations</a>
                <a href="/admin">Support</a>
            </nav>
        </div>
    </header>

    <div class="container main-content">
        {{ content | safe }}
    </div>

    <footer>
        &copy; 1995-2026 FedEx. All rights reserved.
    </footer>
</body>
</html>
"""

INDEX_TEMPLATE = """
<div class="search-box">
    <h1>Track Your Shipment</h1>
    <form action="/" method="post" class="input-group">
        <input type="text" name="tracking_number" value="{{ tn }}" placeholder="Enter tracking number" required>
        <button type="submit">TRACK SHIPMENT</button>
    </form>
</div>

{% if error %}
<div class="error-msg">
    {{ error }}
</div>
{% endif %}

{% if tracking %}
<div class="result-card">
    <div class="result-header">
        <h2>{{ tracking['tracking_number'] }}</h2>
        <div class="status">{{ tracking['status'] }}</div>
        <div class="eta">Estimated Delivery: <strong>{{ tracking['eta'] }}</strong></div>
    </div>
    
    <div class="result-details">
        <div class="detail-col">
            <strong>FROM</strong>
            {{ tracking['sender_name'] }}
        </div>
        <div class="detail-col">
            <strong>TO</strong>
            {{ tracking['recipient_name'] }}<br>
            {{ tracking['recipient_address'] }}
        </div>
        <div class="detail-col">
            <strong>SERVICE</strong>
            {{ tracking['service_type'] }}
        </div>
        <div class="detail-col">
            <strong>WEIGHT</strong>
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
                <div class="event-loc">{{ e['location'] }}{% if e['details'] %} — {{ e['details'] }}{% endif %}</div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
{% endif %}
"""

ADMIN_LOGIN_TEMPLATE = """
<div style="max-width: 400px; margin: 50px auto; background: white; padding: 30px; border: 1px solid #ddd; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
    <h2 style="margin-top: 0; color: #4d148c;">Admin Login</h2>
    {% if error %}
    <div style="color: red; margin-bottom: 15px; font-size: 14px;">{{ error }}</div>
    {% endif %}
    <form method="post">
        <div style="margin-bottom: 15px;">
            <label style="display: block; margin-bottom: 5px; font-weight: bold;">Username</label>
            <input type="text" name="username" style="width: 100%; padding: 8px; box-sizing: border-box;">
        </div>
        <div style="margin-bottom: 15px;">
            <label style="display: block; margin-bottom: 5px; font-weight: bold;">Password</label>
            <input type="password" name="password" style="width: 100%; padding: 8px; box-sizing: border-box;">
        </div>
        <button type="submit" style="width: 100%; background: #4d148c; color: white; border: none; padding: 10px; cursor: pointer;">Login</button>
    </form>
</div>
"""

ADMIN_DASHBOARD_TEMPLATE = """
<div style="max-width: 900px; margin: 0 auto;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h2 style="margin: 0; color: #4d148c;">Admin Dashboard</h2>
        <a href="/admin/logout" style="color: #666; text-decoration: none; font-size: 14px;">Logout</a>
    </div>
    
    <div style="background: #f9f9f9; padding: 20px; border: 1px solid #ddd; margin-bottom: 30px;">
        <h3 style="margin-top: 0;">Create New Shipment</h3>
        <form action="/admin/create" method="post" style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
            <div>
                <label style="display: block; font-size: 12px; font-weight: bold; margin-bottom: 4px;">Sender Name</label>
                <input type="text" name="sender_name" value="ACME CORP" style="width: 100%; padding: 6px; box-sizing: border-box;">
            </div>
            <div>
                <label style="display: block; font-size: 12px; font-weight: bold; margin-bottom: 4px;">Recipient Name</label>
                <input type="text" name="recipient_name" value="John Doe" style="width: 100%; padding: 6px; box-sizing: border-box;">
            </div>
            <div style="grid-column: span 2;">
                <label style="display: block; font-size: 12px; font-weight: bold; margin-bottom: 4px;">Recipient Address</label>
                <input type="text" name="recipient_address" value="123 Main St, Anytown, USA" style="width: 100%; padding: 6px; box-sizing: border-box;">
            </div>
            <div>
                <label style="display: block; font-size: 12px; font-weight: bold; margin-bottom: 4px;">Service Type</label>
                <select name="service_type" style="width: 100%; padding: 6px; box-sizing: border-box;">
                    <option>FedEx Ground</option>
                    <option>FedEx Express Saver</option>
                    <option>FedEx 2Day</option>
                    <option>FedEx Standard Overnight</option>
                </select>
            </div>
            <div>
                <label style="display: block; font-size: 12px; font-weight: bold; margin-bottom: 4px;">Weight</label>
                <input type="text" name="weight" value="2.5 lbs" style="width: 100%; padding: 6px; box-sizing: border-box;">
            </div>
            <div style="grid-column: span 2;">
                <button type="submit" style="background: #4d148c; color: white; border: none; padding: 10px 20px; cursor: pointer; font-weight: bold;">Generate Tracking Number</button>
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
                <td style="padding: 10px;"><a href="/admin/track/{{ t['tracking_number'] }}">{{ t['tracking_number'] }}</a></td>
                <td style="padding: 10px;">{{ t['recipient_name'] }}</td>
                <td style="padding: 10px;">{{ t['status'] }}</td>
                <td style="padding: 10px;">{{ t['eta'] }}</td>
                <td style="padding: 10px;">
                    <form action="/admin/advance/{{ t['tracking_number'] }}" method="post" style="display: inline;">
                        <button type="submit" style="background: #ff6600; color: white; border: none; padding: 6px 12px; cursor: pointer; font-size: 12px;">Advance Status</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""

ADMIN_TRACK_TEMPLATE = """
<div style="max-width: 900px; margin: 0 auto;">
    <a href="/admin" style="color: #4d148c; text-decoration: none; font-size: 14px;">&larr; Back to Dashboard</a>
    <h2 style="color: #4d148c;">Manage: {{ tracking['tracking_number'] }}</h2>

    <div style="background: #f9f9f9; padding: 20px; border: 1px solid #ddd; margin-bottom: 20px;">
        <p><strong>Status:</strong> {{ tracking['status'] }}</p>
        <p><strong>ETA:</strong> {{ tracking['eta'] }}</p>
        <p><strong>Recipient:</strong> {{ tracking['recipient_name'] }} — {{ tracking['recipient_address'] }}</p>
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
            <strong>{{ e['timestamp'] }}</strong> — {{ e['description'] }} ({{ e['location'] }})
            {% if e['details'] %}<br><small style="color: #666;">{{ e['details'] }}</small>{% endif %}
        </div>
        {% endfor %}
    </div>
</div>
"""

# --- ROUTES ---

@app.route("/", methods=["GET", "POST"])
def index():
    tracking = None
    events = []
    error = None
    tn = request.form.get("tracking_number", "") if request.method == "POST" else request.args.get("tn", "")

    if request.method == "POST" and tn:
        conn = get_db()
        tracking = conn.execute("SELECT * FROM trackings WHERE tracking_number = ?", (tn.strip(),)).fetchone()
        if tracking:
            events = conn.execute(
                "SELECT * FROM events WHERE tracking_number = ? ORDER BY id DESC", (tn.strip(),)
            ).fetchall()
        else:
            error = "Tracking number not found. Please check the number and try again. If your shipment was recently created, it may take a few minutes to appear in the system."
        conn.close()

    content = render_template_string(INDEX_TEMPLATE, tracking=tracking, events=events, error=error, tn=tn)
    return render_template_string(BASE_TEMPLATE, content=content, title="FedEx Tracking")


@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    trackings = conn.execute("SELECT * FROM trackings ORDER BY id DESC").fetchall()
    conn.close()
    content = render_template_string(ADMIN_DASHBOARD_TEMPLATE, trackings=trackings)
    return render_template_string(BASE_TEMPLATE, content=content, title="Admin Dashboard")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USER and request.form.get("password") == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "Invalid credentials."
    content = render_template_string(ADMIN_LOGIN_TEMPLATE, error=error)
    return render_template_string(BASE_TEMPLATE, content=content, title="Admin Login")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin/create", methods=["POST"])
def admin_create():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    tn = gen_tracking_number()
    now = datetime.datetime.now()
    eta = now + datetime.timedelta(days=random.randint(2, 5))
    eta_str = eta.strftime("%b %d") + " by 4:30 pm"

    city, facility = random.choice(CITIES)

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO trackings
            (tracking_number, sender_name, recipient_name, recipient_address, service_type, weight, pieces, reference, status, created_at, eta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tn,
             request.form.get("sender_name", "ACME CORP"),
             request.form.get("recipient_name", "John Doe"),
             request.form.get("recipient_address", "123 Main St"),
             request.form.get("service_type", "FedEx Ground"),
             request.form.get("weight", "2.5 lbs"),
             "1",
             rand_ref(),
             "Shipment information sent to FedEx",
             fmt_ts(now),
             eta_str)
        )
        add_event_internal(c, tn, now, city, "Shipment information sent to FedEx",
                           f"{facility} — Reference: {rand_ref()}")
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/track/<tn>")
def admin_track(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    tracking = conn.execute("SELECT * FROM trackings WHERE tracking_number = ?", (tn,)).fetchone()
    events = conn.execute("SELECT * FROM events WHERE tracking_number = ? ORDER BY id DESC", (tn,)).fetchall()
    conn.close()
    if not tracking:
        return redirect(url_for("admin"))
    content = render_template_string(ADMIN_TRACK_TEMPLATE, tracking=tracking, events=events)
    return render_template_string(BASE_TEMPLATE, content=content, title="Manage Shipment")


@app.route("/admin/update/<tn>", methods=["POST"])
def admin_update(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    new_status = request.form.get("status", "").strip()
    if new_status:
        conn = get_db()
        conn.execute("UPDATE trackings SET status = ? WHERE tracking_number = ?", (new_status, tn))
        conn.commit()
        conn.close()
    return redirect(url_for("admin_track", tn=tn))


@app.route("/admin/add_event/<tn>", methods=["POST"])
def admin_add_event(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    now = datetime.datetime.now()
    add_event(
        tn, now,
        request.form.get("location", "").upper(),
        request.form.get("description", ""),
        request.form.get("details", "")
    )
    return redirect(url_for("admin_track", tn=tn))


@app.route("/admin/advance/<tn>", methods=["POST"])
def admin_advance(tn):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    STAGES = [
        "Shipment information sent to FedEx",
        "Picked up",
        "In transit - on time",
        "Arrived at FedEx location",
        "Out for delivery",
        "Delivered",
    ]

    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT status FROM trackings WHERE tracking_number = ?", (tn,)).fetchone()
    if row:
        try:
            idx = STAGES.index(row["status"])
            new_idx = min(idx + 1, len(STAGES) - 1)
        except ValueError:
            new_idx = 1
        new_status = STAGES[new_idx]
        now = datetime.datetime.now()
        city, facility = random.choice(CITIES)
        c.execute("UPDATE trackings SET status = ? WHERE tracking_number = ?", (new_status, tn))
        details = "Delivered — Signed for by: FRONT DESK" if new_status == "Delivered" else facility
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
