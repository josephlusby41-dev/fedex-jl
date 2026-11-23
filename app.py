import os, re, random, string, sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Flask, render_template_string, request, redirect, url_for, abort
from markupsafe import escape

app = Flask(__name__)
DB = os.environ.get("DB_PATH", "track.db")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "changeme")
STATUSES = (
    "Label created", "Picked up", "In transit", "At local facility",
    "Out for delivery", "Delivered", "Exception",
)
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"
STATE_ZONES = {
    "AK": "America/Anchorage", "AL": "America/Chicago",
    "AR": "America/Chicago", "AZ": "America/Phoenix",
    "CA": "America/Los_Angeles", "CO": "America/Denver",
    "CT": "America/New_York", "DE": "America/New_York",
    "FL": "America/New_York", "GA": "America/New_York",
    "HI": "Pacific/Honolulu", "IA": "America/Chicago",
    "ID": "America/Boise", "IL": "America/Chicago",
    "IN": "America/Indiana/Indianapolis", "KS": "America/Chicago",
    "KY": "America/New_York", "LA": "America/Chicago",
    "MA": "America/New_York", "MD": "America/New_York",
    "ME": "America/New_York", "MI": "America/Detroit",
    "MN": "America/Chicago", "MO": "America/Chicago",
    "MS": "America/Chicago", "MT": "America/Denver",
    "NC": "America/New_York", "ND": "America/Chicago",
    "NE": "America/Chicago", "NH": "America/New_York",
    "NJ": "America/New_York", "NM": "America/Denver",
    "NV": "America/Los_Angeles", "NY": "America/New_York",
    "OH": "America/New_York", "OK": "America/Chicago",
    "OR": "America/Los_Angeles", "PA": "America/New_York",
    "RI": "America/New_York", "SC": "America/New_York",
    "SD": "America/Chicago", "TN": "America/Chicago",
    "TX": "America/Chicago", "UT": "America/Denver",
    "VA": "America/New_York", "VT": "America/New_York",
    "WA": "America/Los_Angeles", "WI": "America/Chicago",
    "WV": "America/New_York", "WY": "America/Denver",
}

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init():
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute("""CREATE TABLE IF NOT EXISTS pkgs(
            num TEXT PRIMARY KEY, status TEXT, origin TEXT, dest TEXT,
            created TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, num TEXT, [when] TEXT,
            text TEXT, loc TEXT, out_of_order INTEGER NOT NULL DEFAULT 0,
            city TEXT, state TEXT, tz TEXT)""")
        columns = {column["name"] for column in c.execute("PRAGMA table_info(events)")}
        if "out_of_order" not in columns:
            c.execute("ALTER TABLE events ADD COLUMN out_of_order INTEGER NOT NULL DEFAULT 0")
        for column in ("city", "state", "tz"):
            if column not in columns:
                c.execute(f"ALTER TABLE events ADD COLUMN {column} TEXT")
        c.execute("CREATE INDEX IF NOT EXISTS events_num_when ON events(num, [when])")
init()

@app.template_filter()
def scan_time(event):
    if not event["tz"]:
        return f'{event["when"]} UTC'
    instant = datetime.strptime(event["when"], TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    local = instant.astimezone(ZoneInfo(event["tz"]))
    offset = local.strftime("%z")
    return f'{local:%a %d %b, %H:%M} local (UTC{offset[:3]}:{offset[3:]})'

@app.template_filter()
def scan_location(event):
    if event["city"] and event["state"]:
        return f'{event["city"]}, {event["state"]}'
    return event["loc"] or ""

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
<div class="ev"><b>{{e['text']}}</b><span>{{ e | scan_time }}</span>
{% if e | scan_location %}<div>{{ e | scan_location }}</div>{% endif %}</div>
{% else %}<div class="ev">No activity yet.</div>{% endfor %}</div></section>""")

ADMIN = BASE % ("Admin", CSS + """
.panel .warning{color:#826031}
.panel .box select{padding:13px 15px;border:1px solid #ccc;border-radius:4px;font-size:15px}
.panel .location-chips{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.panel .location-chips button{padding:8px 12px;border:1px solid #ccc;border-radius:16px;background:white;cursor:pointer}
""", """
<section class="hero panel"><h1>Admin</h1>
<p><a href="{{ url_for('home') }}">Back to tracking</a></p>
{% if error %}<p class="alert err" role="alert">{{ error }}</p>{% endif %}
<form method="post" action="{{ url_for('panel_add', k=k) }}" class="box">
<input id="package-number" name="num" placeholder="Tracking number (blank = auto)">
<button type="button" id="generate-number">Generate</button>
<p id="generate-error" role="status"></p>
<select name="status" aria-label="Initial status">
{% for status in statuses %}<option>{{ status }}</option>{% endfor %}</select>
<input name="origin" placeholder="Origin city"><input name="dest" placeholder="Destination city">
<button>Create package</button></form>
{% if pkgs %}<h3 style="margin:24px 0 8px">Packages</h3>
<table><tr><th>Number</th><th>Status</th><th>Route</th><th>Since newest event</th><th>Actions</th></tr>
{% for p in pkgs %}<tr><td><a href="{{ url_for('result', num=p['num']) }}">{{p['num']}}</a>
{% set scans = events.get(p['num'], ()) %}
{% if scans %}<details><summary>Scans ({{ scans | length }})</summary>
{% for event in scans %}
<div class="ev"><b>{{ event['text'] }}</b>{{ event | scan_time }}
{% if event | scan_location %}<div>{{ event | scan_location }}</div>{% endif %}
{% if event['tz'] %}<small>{{ event['when'] }} UTC</small>{% endif %}
{% if event['out_of_order'] %}<div class="warning">Saved out of order</div>{% endif %}</div>
{% endfor %}</details>{% endif %}</td>
<td>{{p['status']}}</td><td>{{p['origin']}}→{{p['dest']}}</td>
<td{% if p['idle_hours'] is not none and p['idle_hours'] > 48 %} class="warning"{% endif %}>
{% if p['idle_hours'] is none %}No dated events{% else %}{{ '%0.1f' | format(p['idle_hours']) }} h{% if p['idle_hours'] > 48 %} · Over 48 h{% endif %}{% endif %}</td>
<td><form method="post" action="{{ url_for('panel_delete', k=k) }}"
onsubmit="return confirm('Delete this package and all its events?')">
<input type="hidden" name="num" value="{{ p['num'] }}"><button>Delete package</button>
</form></td></tr>{% endfor %}</table>{% endif %}
<h3 style="margin:28px 0 8px">Add event</h3>
<div id="location-chips" class="location-chips" aria-label="Recent scan locations"></div>
<form id="event-form" method="post" action="{{ url_for('panel_event', k=k) }}" class="box">
<input name="num" aria-label="Tracking number" placeholder="Tracking number" list="event-packages" required>
<datalist id="event-packages">{% for p in pkgs %}<option value="{{ p['num'] }}">{% endfor %}</datalist>
<input name="text" placeholder="Event text (e.g. Customs clearance)" required>
<input name="city" aria-label="City" placeholder="City">
<select name="state" aria-label="State"><option value="">State</option>
{% for state in states %}<option>{{ state }}</option>{% endfor %}</select>
<input name="when" aria-label="Local timestamp" placeholder="YYYY-MM-DD HH:MM (local)">
<button type="button" id="stamp-now">Now</button>
<select name="status" aria-label="New status"><option value="">Keep current status</option>
{% for status in statuses %}<option>{{ status }}</option>{% endfor %}</select>
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
const eventForm = document.getElementById('event-form');
const {num, city, state, when, status} = eventForm.elements;
const packageScans = {{ package_scans | tojson }};
const stateZones = {{ state_zones | tojson }};
const chips = document.getElementById('location-chips');

function updateLocalTime() {
  const previous = packageScans[num.value.trim()]?.locations[0];
  const zone = stateZones[state.value || previous?.[1]];
  when.placeholder = zone
    ? new Intl.DateTimeFormat('sv-SE', {
        timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
      }).format(new Date())
    : 'YYYY-MM-DD HH:MM (local)';
}

function updatePackage() {
  const selected = packageScans[num.value.trim()];
  status.value = selected?.status || '';
  if (status.selectedIndex < 0) status.value = '';
  chips.replaceChildren();
  for (const [recentCity, recentState] of selected?.locations || []) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.textContent = recentCity + ', ' + recentState;
    chip.addEventListener('click', () => {
      city.value = recentCity;
      state.value = recentState;
      updateLocalTime();
    });
    chips.append(chip);
  }
  updateLocalTime();
}

num.addEventListener('input', updatePackage);
state.addEventListener('change', updateLocalTime);
document.getElementById('stamp-now').addEventListener('click', () => {
  when.value = '';
  updateLocalTime();
});
updatePackage();
setInterval(updateLocalTime, 1000);
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

def event_timestamp(value, zone=timezone.utc):
    if not value:
        return datetime.now(zone).astimezone(timezone.utc).strftime(TIMESTAMP_FORMAT)
    try:
        parsed = datetime.strptime(value, TIMESTAMP_FORMAT)
    except ValueError:
        abort(400, "Use YYYY-MM-DD HH:MM for the timestamp.")
    if parsed.strftime(TIMESTAMP_FORMAT) != value:
        abort(400, "Use YYYY-MM-DD HH:MM for the timestamp.")
    instant = parsed.replace(tzinfo=zone).astimezone(timezone.utc)
    if instant.astimezone(zone).replace(tzinfo=None) != parsed:
        abort(400, "That local time does not exist in the selected time zone.")
    return instant.strftime(TIMESTAMP_FORMAT)

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
    if not p: return render_template_string(TRACKPAGE, msg=f'<p class="alert err">No package {escape(num)}</p>')
    ev = c.execute("SELECT * FROM events WHERE num=? ORDER BY [when] DESC, id DESC", (num,)).fetchall()
    return render_template_string(RESULT, p=p, ev=ev)

@app.route("/panel")
def panel():
    guard()
    return render_panel()

def render_panel(error=None):
    with db() as c:
        pkgs = c.execute("""
            SELECT p.*, MAX(0, (julianday('now') - (
                SELECT MAX(julianday(e.[when])) FROM events e WHERE e.num=p.num
            )) * 24) AS idle_hours
            FROM pkgs p ORDER BY p.created DESC
        """).fetchall()
        events = {}
        for event in c.execute("SELECT * FROM events ORDER BY [when] DESC, id DESC"):
            events.setdefault(event["num"], []).append(event)
    package_scans = {}
    for package in pkgs:
        locations = []
        seen = set()
        for event in events.get(package["num"], ()):
            if not event["city"] or not event["state"]:
                continue
            location = (event["city"].casefold(), event["state"])
            if location not in seen:
                seen.add(location)
                locations.append((event["city"], event["state"]))
                if len(locations) == 5:
                    break
        package_scans[package["num"]] = {"status": package["status"], "locations": locations}
    return render_template_string(ADMIN, k=ADMIN_KEY, pkgs=pkgs, events=events,
                                  statuses=STATUSES, states=STATE_ZONES, state_zones=STATE_ZONES,
                                  package_scans=package_scans, error=error)

@app.route("/panel/add", methods=["POST"])
def panel_add():
    guard()
    num = request.form.get("num", "").strip() or gen()
    if not re.fullmatch(r"\d{10,22}", num):
        abort(400, "Use 10 to 22 digits for the tracking number.")
    status = request.form.get("status") or STATUSES[0]
    if status not in STATUSES:
        abort(400, "Choose a status from the list.")
    origin = request.form.get("origin") or "-"
    dest = request.form.get("dest") or "-"
    with db() as c:
        inserted = c.execute("INSERT INTO pkgs(num,status,origin,dest) VALUES(?,?,?,?) ON CONFLICT(num) DO NOTHING",
                             (num, status, origin, dest))
        if not inserted.rowcount:
            abort(409, "That tracking number already exists.")
        c.execute("INSERT INTO events(num,text,loc,[when]) VALUES(?,?,?,?)",
                  (num, "Label created", origin, event_timestamp("")))
    return redirect(url_for("panel", k=ADMIN_KEY))

@app.route("/panel/event", methods=["POST"])
def panel_event():
    guard()
    num = request.form["num"].strip()
    local_time = request.form.get("when", "").strip()
    status = request.form.get("status", "")
    if status and status not in STATUSES:
        abort(400, "Choose a status from the list.")
    city = request.form.get("city", "").strip()
    state = request.form.get("state", "").strip().upper()
    if (city or state) and (not city or state not in STATE_ZONES):
        return render_panel("Enter a city and select a state, or leave both blank to reuse the last location."), 400
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        if not c.execute("SELECT 1 FROM pkgs WHERE num=?", (num,)).fetchone():
            abort(404, "Package not found.")
        if city:
            tz = STATE_ZONES[state]
        else:
            prior = c.execute("""
                SELECT city, state, tz FROM events
                WHERE num=? AND city IS NOT NULL AND state IS NOT NULL AND tz IS NOT NULL
                ORDER BY [when] DESC, id DESC LIMIT 1
            """, (num,)).fetchone()
            if prior is None:
                return render_panel("Enter a city and state for the first scan with a location."), 400
            city, state, tz = prior
        when = event_timestamp(local_time, ZoneInfo(tz))
        out_of_order = c.execute(
            "SELECT EXISTS(SELECT 1 FROM events WHERE num=? AND julianday([when]) > julianday(?))",
            (num, when),
        ).fetchone()[0]
        c.execute("""
            INSERT INTO events(num,text,loc,[when],out_of_order,city,state,tz) VALUES(?,?,?,?,?,?,?,?)
        """, (num, request.form["text"], f"{city}, {state}", when, out_of_order, city, state, tz))
        if status:
            c.execute("UPDATE pkgs SET status=? WHERE num=?", (status, num))
    return redirect(url_for("panel", k=ADMIN_KEY))

@app.route("/panel/delete", methods=["POST"])
def panel_delete():
    guard()
    num = request.form["num"]
    with db() as c:
        c.execute("DELETE FROM events WHERE num=?", (num,))
        c.execute("DELETE FROM pkgs WHERE num=?", (num,))
    return redirect(url_for("panel", k=ADMIN_KEY))

if __name__ == "__main__": app.run(debug=True)
