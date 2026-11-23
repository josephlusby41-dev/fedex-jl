from flask import Flask, request, render_template_string, redirect, session
import sqlite3, os, random, datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-please")
DB_PATH = "/tmp/fedex.db"

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "fedex123")

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

def init_db():
    conn = sqlite3.connect(DB_PATH)
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
        notes TEXT
    )""")
    conn.commit()
    conn.close()

def gen_tracking_number():
    return str(random.randint(700000000000, 799999999999))

def rand_ref():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8)) if False else "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))

def fmt_ts(dt):
    return dt.strftime("%b %d, %Y %I:%M %p").replace("AM", "am").replace("PM", "pm")

def add_event(tracking_number, dt, location, description, notes=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO events (tracking_number, timestamp, location, description, notes) VALUES (?,?,?,?,?)",
              (tracking_number, fmt_ts(dt), location, description, notes))
    conn.commit()
    conn.close()

PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tracking Results | FedEx</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; font-family: Arial, Helvetica, sans-serif; }
  body { background:#fff; color:#333; }
  .topbar { background:#4d148c; height:10px; }
  nav { display:flex; align-items:center; padding:14px 40px; border-bottom:1px solid #e5e5e5; }
  .logo { font-weight:700; font-size:26px; font-style:italic; letter-spacing:-1px; }
  .logo .fed { color:#4d148c; } .logo .ex { color:#ff6600; }
  nav ul { list-style:none; display:flex; gap:26px; margin-left:55px; font-size:14px; font-weight:700; }
  nav ul li a { text-decoration:none; color:#333; }
  nav .right { margin-left:auto; font-size:14px; }
  .breadcrumb { padding:16px 40px; font-size:13px; color:#666; }
  .page { max-width:980px; margin:0 auto; padding:0 20px 60px; }
  h1 { color:#4d148c; font-size:28px; margin:10px 0 20px; font-weight:700; }
  .summary { border:1px solid #ddd; border-radius:4px; margin-bottom:28px; }
  .summary .head { background:#4d148c; color:#fff; padding:16px 22px; display:flex; justify-content:space-between; flex-wrap:wrap; }
  .summary .head .status { font-size:18px; font-weight:700; }
  .summary .head .tn { font-size:13px; opacity:.9; }
  .summary .body { padding:22px; display:flex; gap:40px; flex-wrap:wrap; font-size:14px; }
  .summary .body div b { display:block; color:#888; font-size:11px; text-transform:uppercase; margin-bottom:4px; letter-spacing:.5px; }
  .timeline { border:1px solid #ddd; border-radius:4px; padding:24px; }
  .timeline h2 { color:#4d148c; font-size:18px; margin-bottom:18px; }
  .ev { display:flex; gap:18px; padding:12px 0; border-bottom:1px solid #f0f0f0; }
  .ev:last-child { border-bottom:none; }
  .ev .dot { width:14px; height:14px; border-radius:50%; background:#ff6600; margin-top:4px; flex-shrink:0; position:relative; }
  .ev .dot::after { content:""; position:absolute; left:6px; top:14px; height:calc(100% + 8px); width:2px; background:#ddd; }
  .ev:last-child .dot::after { display:none; }
  .ev .when { width:190px; flex-shrink:0; font-size:13px; color:#555; }
  .ev .what { font-size:14px; }
  .ev .what b { display:block; }
  .ev .what span { color:#777; font-size:13px; }
  .btn { background:#4d148c; color:#fff; border:none; padding:12px 30px; font-size:15px; font-weight:700; border-radius:24px; cursor:pointer; margin-top:16px; }
  .btn:hover { background:#3a0f6b; }
  footer { background:#4d148c; color:#fff; padding:30px 40px; margin-top:50px; font-size:13px; }
  .err { color:#c00; text-align:center; margin:20px; font-weight:700; }
  input[type=text], input:not([type]) { width:100%; padding:13px; font-size:15px; border:1px solid #999; border-radius:4px; }
  label { font-weight:700; display:block; margin-bottom:8px; font-size:13px; letter-spacing:.5px; }
</style>
</head>
<body>
<div class="topbar"></div>
<nav>
  <div class="logo"><span class="fed">Fed</span><span class="ex">Ex</span></div>
  <ul>
    <li><a href="/">Tracking</a></li>
    <li><a href="#">Shipping</a></li>
    <li><a href="#">Locations</a></li>
    <li><a href="#">Support</a></li>
  </ul>
  <div class="right">Log In &nbsp;|&nbsp; Create Account</div>
</nav>
{{ content }}
<footer>&copy; 1995-{{ year }} FedEx. All rights reserved.</footer>
</body>
</html>
"""

HOME = """
<div class="breadcrumb">Home &gt; Tracking</div>
<div class="page">
  <h1>Tracking</h1>
  <div class="summary" style="padding:26px;">
    <form method="POST" action="/track">
      <label for="tn">TRACKING NUMBER</label>
      <input type="text" id="tn" name="tracking_number" placeholder="Enter tracking number" required>
      <button class="btn" type="submit">TRACK SHIPMENT</button>
    </form>
  </div>
  {% if error %}<p class="err">We could not find a shipment matching this tracking number. Please check the number and try again.</p>{% endif %}
</div>
"""

RESULT = """
<div class="breadcrumb">Home &gt; Tracking &gt; Tracking Results</div>
<div class="page">
  <h1>Tracking Results</h1>
  <div class="summary">
    <div class="head">
      <div class="status">{{ tracking.status }}</div>
      <div class="tn">Tracking Number: {{ tracking.tracking_number }}</div>
    </div>
    <div class="body">
      <div><b>Estimated Delivery</b>{{ tracking.eta }}</div>
      <div><b>Service Type</b>{{ tracking.service_type }}</div>
      <div><b>Weight</b>{{ tracking.weight }}</div>
      <div><b>Pieces</b>{{ tracking.pieces }}</div>
      <div><b>Reference</b>{{ tracking.reference }}</div>
      <div><b>Ship To</b>{{ tracking.recipient_name }}<br>{{ tracking.recipient_address }}</div>
      <div><b>Shipped From</b>{{ tracking.sender_name }}</div>
    </div>
  </div>
  <div class="timeline">
    <h2>Shipment Progress</h2>
    {% for e in events %}
    <div class="ev">
      <div class="dot"></div>
      <div class="when">{{ e.timestamp }}</div>
      <div class="what"><b>{{ e.description }}</b><span>{{ e.location }}{% if e.notes %} &mdash; {{ e.notes }}{% endif %}</span></div>
    </div>
    {% endfor %}
  </div>
</div>
"""

@app.route("/", methods=["GET"])
def home():
    return render_template_string(PAGE, content=render_template_string(HOME, error=False), year=datetime.datetime.now().year)

@app.route("/track", methods=["POST"])
def track():
    tn = request.form.get("tracking_number", "").strip()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM trackings WHERE tracking_number=?", (tn,))
    row = c.fetchone()
    events = c.execute("SELECT * FROM events WHERE tracking_number=? ORDER BY id DESC", (tn,)).fetchall()
    conn.close()
    if not row:
        return render_template_string(PAGE, content=render_template_string(HOME, error=True), year=datetime.datetime.now().year)
    return render_template_string(PAGE, content=render_template_string(RESULT, tracking=row, events=events), year=datetime.datetime.now().year)

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return render_template_string(PAGE, content="""
        <div class="page" style="max-width:480px;margin-top:60px;">
        <div class="summary" style="padding:26px;"><form method="POST" action="/admin">
          <label>USERNAME</label><input name="username" required>
          <label style="margin-top:14px;">PASSWORD</label><input type="password" name="password" required>
          <button class="btn" type="submit">LOG IN</button>
        </form></div></div>""", year=datetime.datetime.now().year)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM trackings ORDER BY id DESC").fetchall()
    conn.close()
    items = "".join(
        f"<tr><td>{r['tracking_number']}</td><td>{r['recipient_name']}</td><td>{r['status']}</td><td>{r['eta']}</td>"
        f"<td><a href='/advance/{r['tracking_number']}'>Advance Scan</a></td></tr>" for r in rows)
    content = f"""<div class="page"><h1>Admin Panel</h1>
    <div class="summary" style="padding:20px;margin-bottom:24px;">
    <form method="POST" action="/admin/create" style="display:grid;gap:10px;grid-template-columns:1fr 1fr;">
      <input name="sender_name" placeholder="Sender Name (Company/Shipper)" required>
      <input name="recipient_name" placeholder="Recipient Name" required>
      <input name="recipient_address" placeholder="Recipient Address (City, ST)" required style="grid-column:span 2;">
      <select name="service_type" style="padding:12px;">
        <option>FedEx Priority Overnight&reg;</option>
        <option>FedEx 2Day&reg;</option>
        <option>FedEx Express Saver&reg;</option>
        <option>FedEx Ground&reg;</option>
        <option>FedEx Home Delivery&reg;</option>
      </select>
      <select name="weight" style="padding:12px;">
        <option>1 lb / 0.5 kg</option><option>3 lb / 1.4 kg</option><option>5 lb / 2.3 kg</option>
        <option>8 lb / 3.6 kg</option><option>12 lb / 5.4 kg</option><option>25 lb / 11.3 kg</option>
      </select>
      <button class="btn" type="submit" style="grid-column:span 2;">CREATE TRACKING</button>
    </form></div>
    <table style="width:100%;border-collapse:collapse;">
    <tr style="background:#4d148c;color:#fff;"><th style="padding:10px;text-align:left;">Tracking #</th><th style="padding:10px;text-align:left;">Recipient</th><th style="padding:10px;text-align:left;">Status</th><th style="padding:10px;text-align:left;">ETA</th><th></th></tr>
    {items}</table></div>"""
    return render_template_string(PAGE, content=content, year=datetime.datetime.now().year)

@app.route("/admin", methods=["POST"])
def admin_login():
    if request.form["username"] == ADMIN_USER and request.form["password"] == ADMIN_PASS:
        session["admin"] = True
    return redirect("/admin")

@app.route("/admin/create", methods=["POST"])
def admin_create():
    if not session.get("admin"):
        return redirect("/admin")
    tn = gen_tracking_number()
    now = datetime.datetime.now()
    days = random.choice([1, 2, 3])
    eta = now + datetime.timedelta(days=days)
    eta_str = eta.strftime("%b %d") + " by " + ("10:30 am" if days == 1 else ("4:30 pm" if days == 2 else "8:00 pm"))
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO trackings (tracking_number, sender_name, recipient_name, recipient_address, service_type, weight, pieces, reference, status, created_at, eta) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
              (tn, request.form["sender_name"], request.form["recipient_name"], request.form["recipient_address"],
               request.form["service_type"], request.form["weight"], "1", rand_ref(), "In Transit - On Time",
               fmt_ts(now), eta_str))
    conn.commit()
    conn.close()
    # seed realistic initial scans
    city, fac = random.choice(CITIES[:4])
    add_event(tn, now - datetime.timedelta(hours=random.randint(20, 30)), f"{city}", "Shipment information sent to FedEx")
    add_event(tn, now - datetime.timedelta(hours=random.randint(8, 18)), f"{city} - {fac}", "Picked up", "Shipment picked up from shipper")
    add_event(tn, now - datetime.timedelta(hours=random.randint(2, 7)), f"{city} - {fac}", "Arrived at FedEx location")
    return redirect("/admin")

@app.route("/advance/<tracking_number>")
def advance(tracking_number):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    count = c.execute("SELECT COUNT(*) FROM events WHERE tracking_number=?", (tracking_number,)).fetchone()[0]
    if count < 7:
        stage = [
            ("In transit", random.choice(CITIES[4:]), "Departed FedEx location", "In transit to destination"),
            (None, random.choice(CITIES[4:]), "Arrived at FedEx hub", ""),
            (None, random.choice(CITIES[4:]), "In transit", "On the way to destination city"),
            (None, "Local destination city", "Arrived at local FedEx facility", ""),
            (None, "Local destination city", "On FedEx vehicle for delivery", "Delivery scheduled today by end of day"),
            ("Out for Delivery", "Local destination city", "Out for delivery", "On FedEx vehicle for delivery"),
            ("Delivered", "Local destination city", "Delivered", "Left at front door - Signature not required"),
        ][count]
        now = datetime.datetime.now()
        add_event(tracking_number, now, stage[1], stage[2], stage[3])
        if stage[0]:
            c.execute("UPDATE trackings SET status=? WHERE tracking_number=?", (stage[0], tracking_number))
            conn.commit()
    conn.close()
    return redirect("/admin")

import string
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
