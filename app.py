"""Many Hands - a volunteer sign-up and hour-tracking site (Flask + SQLite).

Run:  python app.py      then open http://127.0.0.1:5000
The first account you register becomes the admin (can post events).
"""
import hmac
import os
import secrets
import sqlite3
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get("DATABASE", os.path.join(BASE_DIR, "volunteer.db"))
CATEGORIES = ["Food", "Environment", "Education", "Seniors", "Animals", "Health"]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    location TEXT NOT NULL,
    date TEXT NOT NULL,            -- ISO date, YYYY-MM-DD
    hours REAL NOT NULL,
    spots INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS signups (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    UNIQUE (user_id, event_id)
);
CREATE TABLE IF NOT EXISTS logged_hours (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization TEXT NOT NULL,
    date TEXT NOT NULL,
    hours REAL NOT NULL
);
"""


# ---------- database helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(SCHEMA)
    if db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0:
        today = date.today()
        sample = [
            ("Neighborhood food bank sorting", "Sort and pack donated food for weekend distribution.", "Food", "Community Center", 3, 3, 12),
            ("Beach and river clean-up", "Bring gloves. Bags and water are provided.", "Environment", "Riverside Park", 6, 4, 25),
            ("After-school homework help", "Help primary school kids with reading and math.", "Education", "Public Library", 9, 2, 8),
            ("Tea and conversation with seniors", "Spend an afternoon playing games and chatting.", "Seniors", "Sunrise Care Home", 12, 2.5, 10),
            ("Animal shelter dog walking", "Walk and socialize shelter dogs. Closed shoes only.", "Animals", "Paws Shelter", 15, 2, 15),
            ("Community health fair helpers", "Greet visitors and guide them between stations.", "Health", "City Hall", 20, 4, 20),
        ]
        db.executemany(
            "INSERT INTO events (title, description, category, location, date, hours, spots) VALUES (?,?,?,?,?,?,?)",
            [(t, d, c, l, (today + timedelta(days=n)).isoformat(), h, s) for t, d, c, l, n, h, s in sample],
        )
    db.commit()
    db.close()


# ---------- security: CSRF token + current user ----------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def load_user_and_check_csrf():
    if request.method == "POST":
        sent = request.form.get("_csrf", "").encode()
        if not hmac.compare_digest(sent, session.get("_csrf", "").encode()):
            abort(400, "Your form expired. Go back, reload the page, and try again.")
    g.user = None
    if session.get("user_id"):
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Log in to continue.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# ---------- public pages ----------
@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    where, params = ["e.date >= ?"], [date.today().isoformat()]
    if q:
        where.append("(e.title LIKE ? OR e.description LIKE ? OR e.location LIKE ?)")
        params += [f"%{q}%"] * 3
    if category in CATEGORIES:
        where.append("e.category = ?")
        params.append(category)
    uid = g.user["id"] if g.user else -1
    events = get_db().execute(
        f"""SELECT e.*,
                   (SELECT COUNT(*) FROM signups s WHERE s.event_id = e.id) AS taken,
                   EXISTS (SELECT 1 FROM signups s WHERE s.event_id = e.id AND s.user_id = ?) AS mine
            FROM events e WHERE {' AND '.join(where)} ORDER BY e.date, e.id""",
        [uid] + params,
    ).fetchall()
    totals = get_db().execute(
        """SELECT COALESCE(SUM(e.hours), 0) AS hours, COUNT(DISTINCT s.user_id) AS people
           FROM signups s JOIN events e ON e.id = s.event_id WHERE e.date < ?""",
        (date.today().isoformat(),),
    ).fetchone()
    return render_template("index.html", events=events, q=q, category=category,
                           categories=CATEGORIES, totals=totals,
                           parse=date.fromisoformat)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or "@" not in email:
            flash("Enter your name and a valid email address.", "error")
        elif len(password) < 8:
            flash("Choose a password with at least 8 characters.", "error")
        else:
            db = get_db()
            first = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            try:
                cur = db.execute(
                    "INSERT INTO users (name, email, password_hash, is_admin) VALUES (?,?,?,?)",
                    (name, email, generate_password_hash(password), int(first)),
                )
                db.commit()
            except sqlite3.IntegrityError:
                flash("That email already has an account. Log in instead.", "error")
            else:
                session.clear()
                session["user_id"] = cur.lastrowid
                flash("Welcome to Many Hands." + (" You are the admin." if first else ""), "ok")
                return redirect(url_for("index"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("index"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------- volunteer actions ----------
@app.post("/events/<int:event_id>/signup")
@login_required
def signup(event_id):
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if event is None:
        abort(404)
    taken = db.execute("SELECT COUNT(*) FROM signups WHERE event_id = ?", (event_id,)).fetchone()[0]
    if event["date"] < date.today().isoformat():
        flash("That event has already happened.", "error")
    elif taken >= event["spots"]:
        flash("That event is full.", "error")
    else:
        try:
            db.execute("INSERT INTO signups (user_id, event_id) VALUES (?, ?)", (g.user["id"], event_id))
            db.commit()
            flash(f"You're signed up for {event['title']}.", "ok")
        except sqlite3.IntegrityError:
            flash("You already signed up for this event.", "error")
    return redirect(request.referrer or url_for("index"))


@app.post("/events/<int:event_id>/cancel")
@login_required
def cancel(event_id):
    db = get_db()
    db.execute("DELETE FROM signups WHERE user_id = ? AND event_id = ?", (g.user["id"], event_id))
    db.commit()
    flash("Your sign-up was cancelled.", "ok")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    db, today = get_db(), date.today().isoformat()
    joined = db.execute(
        """SELECT e.* FROM signups s JOIN events e ON e.id = s.event_id
           WHERE s.user_id = ? ORDER BY e.date""", (g.user["id"],)).fetchall()
    logged = db.execute(
        "SELECT * FROM logged_hours WHERE user_id = ? ORDER BY date DESC", (g.user["id"],)).fetchall()
    upcoming = [e for e in joined if e["date"] >= today]
    done_hours = sum(e["hours"] for e in joined if e["date"] < today)
    total = done_hours + sum(h["hours"] for h in logged)
    return render_template("dashboard.html", upcoming=upcoming, logged=logged,
                           total=total, parse=date.fromisoformat)


@app.post("/dashboard/log")
@login_required
def log_hours():
    org = request.form.get("organization", "").strip()
    try:
        day = date.fromisoformat(request.form.get("date", ""))
        hours = float(request.form.get("hours", ""))
    except ValueError:
        flash("Enter a valid date and number of hours.", "error")
        return redirect(url_for("dashboard"))
    if not org or not (0 < hours <= 24) or day > date.today():
        flash("Add an organization, hours between 0 and 24, and a date that is not in the future.", "error")
    else:
        db = get_db()
        db.execute("INSERT INTO logged_hours (user_id, organization, date, hours) VALUES (?,?,?,?)",
                   (g.user["id"], org, day.isoformat(), hours))
        db.commit()
        flash("Hours logged.", "ok")
    return redirect(url_for("dashboard"))


@app.get("/api/hours")
@login_required
def api_hours():
    """Hours per month for the last 6 months (used by the dashboard chart)."""
    db, today = get_db(), date.today()
    months, y, m = [], today.year, today.month
    for _ in range(6):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    totals = dict.fromkeys(months, 0.0)
    rows = db.execute(
        """SELECT substr(e.date, 1, 7) AS month, e.hours FROM signups s
           JOIN events e ON e.id = s.event_id WHERE s.user_id = ? AND e.date < ?
           UNION ALL
           SELECT substr(date, 1, 7), hours FROM logged_hours WHERE user_id = ?""",
        (g.user["id"], today.isoformat(), g.user["id"]),
    ).fetchall()
    for r in rows:
        if r["month"] in totals:
            totals[r["month"]] += r["hours"]
    return jsonify(labels=months, hours=[totals[k] for k in months])


# ---------- admin ----------
@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    db = get_db()
    if request.method == "POST":
        f = request.form
        try:
            day = date.fromisoformat(f.get("date", ""))
            hours, spots = float(f.get("hours", "")), int(f.get("spots", ""))
        except ValueError:
            flash("Check the date, hours, and number of spots.", "error")
            return redirect(url_for("admin"))
        title, desc, loc = f.get("title", "").strip(), f.get("description", "").strip(), f.get("location", "").strip()
        if not (title and desc and loc) or f.get("category") not in CATEGORIES or not (0 < hours <= 24) or not (1 <= spots <= 500):
            flash("Fill in every field. Hours must be 0-24 and spots 1-500.", "error")
        else:
            db.execute(
                "INSERT INTO events (title, description, category, location, date, hours, spots) VALUES (?,?,?,?,?,?,?)",
                (title, desc, f["category"], loc, day.isoformat(), hours, spots))
            db.commit()
            flash("Event published.", "ok")
        return redirect(url_for("admin"))
    events = db.execute(
        """SELECT e.*, (SELECT COUNT(*) FROM signups s WHERE s.event_id = e.id) AS taken
           FROM events e ORDER BY e.date DESC""").fetchall()
    return render_template("admin.html", events=events, categories=CATEGORIES,
                           today=date.today().isoformat())


@app.post("/admin/events/<int:event_id>/delete")
@admin_required
def delete_event(event_id):
    db = get_db()
    db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    db.commit()
    flash("Event deleted.", "ok")
    return redirect(url_for("admin"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
