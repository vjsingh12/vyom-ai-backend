"""
Vayuman — Vedic Astrology Calculation Engine
Using Swiss Ephemeris (pyswisseph) with Lahiri Ayanamsa
Accurate Lagna, Rashi, Nakshatra, Vimshottari Dasha calculations
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import swisseph as swe
from datetime import datetime, timezone
import math
import os
import json
import re
import sqlite3
import urllib.request
import numerology as numerology_engine
import urllib.parse
import urllib.error
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

app = Flask(__name__)
CORS(app)  # Allow requests from your website

# ── AUTH / ACCOUNTS ──────────────────────────────────────────────────────────
# Lightweight, dependency-free auth: SQLite for users & saved birth profiles,
# stateless signed tokens (no server-side session table needed).
#
# Uses Postgres (e.g. a free Supabase project) when DATABASE_URL is set —
# this is what should be configured on Render for persistent storage across
# deploys. Falls back to a local SQLite file when DATABASE_URL is absent
# (useful for local development/testing).

DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vayuman.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me-in-production")
serializer = URLSafeTimedSerializer(SECRET_KEY)
TOKEN_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


class DB:
    """Tiny wrapper so the rest of the code doesn't care whether it's
    talking to Postgres (Supabase) or SQLite (local fallback)."""

    def __init__(self):
        if USE_POSTGRES:
            self.conn = psycopg.connect(DATABASE_URL, sslmode='require', row_factory=dict_row)
            self.cur = self.conn.cursor()
        else:
            self.conn = sqlite3.connect(DB_PATH)
            self.conn.row_factory = sqlite3.Row
            self.cur = self.conn.cursor()

    def execute(self, sql, params=()):
        if USE_POSTGRES:
            sql = sql.replace('?', '%s')
        self.cur.execute(sql, params)
        return self

    def fetchone(self):
        row = self.cur.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(r) for r in self.cur.fetchall()]

    def commit(self):
        self.conn.commit()

    def close(self):
        self.cur.close()
        self.conn.close()

    def insert_returning_id(self, sql, params, table_for_sqlite, pk_for_sqlite="id"):
        """INSERT that returns the new row's id, on either backend."""
        if USE_POSTGRES:
            sql = sql.rstrip().rstrip(';') + " RETURNING id"
            self.execute(sql, params)
            new_id = self.cur.fetchone()['id']
        else:
            self.execute(sql, params)
            new_id = self.cur.lastrowid
        return new_id


def get_db():
    return DB()


def init_db():
    db = get_db()
    if USE_POSTGRES:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL,
                name TEXT NOT NULL,
                relation TEXT NOT NULL,
                dob TEXT NOT NULL,
                tob TEXT NOT NULL,
                pob TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                id SERIAL PRIMARY KEY,
                created_at TEXT NOT NULL,
                kind TEXT,
                email TEXT,
                name TEXT,
                dob TEXT,
                tob TEXT,
                pob TEXT,
                focus TEXT,
                question TEXT,
                output TEXT,
                lang TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id SERIAL PRIMARY KEY,
                created_at TEXT NOT NULL,
                email TEXT,
                name TEXT,
                dob TEXT,
                focus TEXT,
                rating INTEGER,
                comment TEXT,
                is_minor INTEGER,
                lang TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id SERIAL PRIMARY KEY,
                created_at TEXT NOT NULL,
                email TEXT UNIQUE,
                source TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS contact_messages (
                id SERIAL PRIMARY KEY,
                created_at TEXT NOT NULL,
                kind TEXT,
                name TEXT,
                email TEXT,
                message TEXT,
                rating INTEGER
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS pending_contexts (
                id SERIAL PRIMARY KEY,
                email TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                status TEXT,
                question_type TEXT,
                original_question TEXT,
                target_relation TEXT,
                needed_fields TEXT,
                resume_action TEXT,
                context_json TEXT
            )
        """)
    else:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                name TEXT NOT NULL,
                relation TEXT NOT NULL,
                dob TEXT NOT NULL,
                tob TEXT NOT NULL,
                pob TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                kind TEXT,
                email TEXT,
                name TEXT,
                dob TEXT,
                tob TEXT,
                pob TEXT,
                focus TEXT,
                question TEXT,
                output TEXT,
                lang TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                email TEXT,
                name TEXT,
                dob TEXT,
                focus TEXT,
                rating INTEGER,
                comment TEXT,
                is_minor INTEGER,
                lang TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                email TEXT UNIQUE,
                source TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS contact_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                kind TEXT,
                name TEXT,
                email TEXT,
                message TEXT,
                rating INTEGER
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS pending_contexts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                status TEXT,
                question_type TEXT,
                original_question TEXT,
                target_relation TEXT,
                needed_fields TEXT,
                resume_action TEXT,
                context_json TEXT
            )
        """)
    db.commit()
    db.close()


init_db()


def log_request(kind, data=None, email=None, question=None, output=None):
    """Best-effort logging of a reading/ask request for quality & training.
    Never raises — logging failure must not break the user's request."""
    try:
        data = data or {}
        db = get_db()
        db.execute(
            "INSERT INTO request_logs (created_at, kind, email, name, dob, tob, pob, focus, question, output, lang) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.utcnow().isoformat(),
                kind,
                email,
                data.get('name'),
                data.get('dob'),
                data.get('tob'),
                data.get('pob'),
                data.get('focus'),
                question,
                output,
                data.get('lang'),
            )
        )
        db.commit()
        db.close()
    except Exception as e:
        print(f"[log_request] failed: {e}")


PENDING_CONTEXT_EXPIRY_MINUTES = 45


def save_pending_context(email, pending_context):
    """
    Best-effort persistence of a pending context for a SIGNED-IN user, so it
    survives across devices/sessions. Anonymous users rely entirely on the
    frontend (sessionStorage) — this is a bonus, never a requirement, and
    must never break the main request if it fails.
    """
    if not email or not pending_context:
        return
    try:
        from datetime import timedelta
        now = datetime.utcnow()
        expires_at = (now + timedelta(minutes=PENDING_CONTEXT_EXPIRY_MINUTES)).isoformat()
        db = get_db()
        db.execute(
            "INSERT INTO pending_contexts (email, created_at, expires_at, status, question_type, "
            "original_question, target_relation, needed_fields, resume_action, context_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                email, now.isoformat(), expires_at,
                pending_context.get("status"),
                pending_context.get("question_type"),
                pending_context.get("original_question"),
                pending_context.get("target_relation"),
                json.dumps(pending_context.get("needed_fields") or []),
                pending_context.get("resume_action"),
                json.dumps(pending_context),
            )
        )
        db.commit()
        db.close()
    except Exception as e:
        print(f"[save_pending_context] failed: {e}")


def load_pending_context(email):
    """Returns the most recent NON-EXPIRED pending context for this email,
    or None. Best-effort — anonymous users always get None here (the
    frontend is their source of truth instead)."""
    if not email:
        return None
    try:
        db = get_db()
        row = db.execute(
            "SELECT context_json, expires_at FROM pending_contexts WHERE email = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (email,)
        ).fetchone()
        db.close()
        if not row:
            return None
        if row.get("expires_at") and row["expires_at"] < datetime.utcnow().isoformat():
            return None  # expired
        return json.loads(row["context_json"])
    except Exception as e:
        print(f"[load_pending_context] failed: {e}")
        return None


@app.route('/cleanup', methods=['GET', 'POST'])
def cleanup_logs():
    """Delete request_logs older than 7 days. Pinged daily by cron-job.org.
    Honours the 7-day retention promise in the Privacy Notice."""
    try:
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
        db = get_db()
        db.execute("DELETE FROM request_logs WHERE created_at < ?", (cutoff,))
        db.commit()
        db.close()
        return jsonify({"status": "ok", "deleted_before": cutoff})
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500



@app.route('/feedback', methods=['POST'])
def submit_feedback():
    """Store a user's star rating + optional comment for a reading.
    Captures who gave it (email if signed in, else name/dob from the chart)."""
    try:
        data = request.get_json(force=True) or {}
        rating = data.get('rating')
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid rating"}), 400
        if rating < 1 or rating > 5:
            return jsonify({"error": "Rating must be 1-5"}), 400

        # Resolve email from Bearer token if signed in
        email = None
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            email = verify_token(auth[7:])

        db = get_db()
        db.execute(
            "INSERT INTO feedback (created_at, email, name, dob, focus, rating, comment, is_minor, lang) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.utcnow().isoformat(),
                email,
                data.get('name'),
                data.get('dob'),
                data.get('focus'),
                rating,
                (data.get('comment') or '')[:2000],
                1 if data.get('is_minor') else 0,
                data.get('lang'),
            )
        )
        db.commit()
        db.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"[feedback] failed: {e}")
        return jsonify({"status": "error", "detail": str(e)}), 500


@app.route('/waitlist', methods=['POST'])
def join_waitlist():
    """Save a waitlist email. Idempotent — re-submitting the same email is fine."""
    try:
        data = request.get_json(force=True) or {}
        email = (data.get('email') or '').strip().lower()
        # Basic email sanity check
        if not email or '@' not in email or '.' not in email.split('@')[-1]:
            return jsonify({"error": "Invalid email"}), 400

        db = get_db()
        if USE_POSTGRES:
            db.execute(
                "INSERT INTO waitlist (created_at, email, source) VALUES (?, ?, ?) "
                "ON CONFLICT (email) DO NOTHING",
                (datetime.utcnow().isoformat(), email, data.get('source') or 'demo')
            )
        else:
            db.execute(
                "INSERT OR IGNORE INTO waitlist (created_at, email, source) VALUES (?, ?, ?)",
                (datetime.utcnow().isoformat(), email, data.get('source') or 'demo')
            )
        db.commit()
        db.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"[waitlist] failed: {e}")
        return jsonify({"status": "error", "detail": str(e)}), 500


@app.route('/contact', methods=['POST'])
def contact_message():
    """Save a contact-us message or general feedback. kind = 'contact' or 'feedback'."""
    try:
        data = request.get_json(force=True) or {}
        kind = (data.get('kind') or 'contact').strip().lower()
        if kind not in ('contact', 'feedback'):
            kind = 'contact'
        name = (data.get('name') or '').strip()[:200]
        email = (data.get('email') or '').strip()[:200]
        message = (data.get('message') or '').strip()[:5000]
        rating = data.get('rating')
        try:
            rating = int(rating) if rating not in (None, '') else None
        except (TypeError, ValueError):
            rating = None

        # Require at least a message (and an email for contact replies)
        if not message:
            return jsonify({"error": "Message is required"}), 400
        if kind == 'contact' and (not email or '@' not in email):
            return jsonify({"error": "A valid email is required"}), 400

        db = get_db()
        db.execute(
            "INSERT INTO contact_messages (created_at, kind, name, email, message, rating) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), kind, name, email, message, rating)
        )
        db.commit()
        db.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"[contact] failed: {e}")
        return jsonify({"status": "error", "detail": str(e)}), 500


def generate_token(email):
    return serializer.dumps(email)


def verify_token(token):
    try:
        return serializer.loads(token, max_age=TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def get_authenticated_email():
    """Returns the email for the Bearer token in the Authorization header, or None."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return verify_token(auth[len("Bearer "):])


@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json(force=True)
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or '@' not in email:
        return jsonify({"error": "Please enter a valid email address."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400

    conn = get_db()
    existing = conn.execute("SELECT email FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "An account with this email already exists. Try signing in instead."}), 409

    password_hash = generate_password_hash(password)
    conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email, password_hash, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

    token = generate_token(email)
    return jsonify({"token": token, "email": email})


@app.route('/signin', methods=['POST'])
def signin():
    data = request.get_json(force=True)
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({"error": "Please enter both email and password."}), 400

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Incorrect email or password."}), 401

    token = generate_token(email)
    return jsonify({"token": token, "email": email})


@app.route('/profiles', methods=['GET'])
def list_profiles():
    email = get_authenticated_email()
    if not email:
        return jsonify({"error": "Not authenticated."}), 401

    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, relation, dob, tob, pob FROM profiles WHERE email = ? ORDER BY created_at ASC",
        (email,)
    ).fetchall()
    conn.close()

    return jsonify({"profiles": rows})


@app.route('/profiles', methods=['POST'])
def add_profile():
    email = get_authenticated_email()
    if not email:
        return jsonify({"error": "Not authenticated."}), 401

    data = request.get_json(force=True)
    name = (data.get('name') or '').strip()
    relation = (data.get('relation') or '').strip()
    dob = (data.get('dob') or '').strip()
    tob = (data.get('tob') or '').strip()
    pob = (data.get('pob') or '').strip()

    if not all([name, relation, dob, tob, pob]):
        return jsonify({"error": "Please fill in all fields."}), 400

    conn = get_db()
    new_id = conn.insert_returning_id(
        "INSERT INTO profiles (email, name, relation, dob, tob, pob, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (email, name, relation, dob, tob, pob, datetime.utcnow().isoformat()),
        table_for_sqlite="profiles"
    )
    conn.commit()
    conn.close()

    return jsonify({"id": new_id, "name": name, "relation": relation, "dob": dob, "tob": tob, "pob": pob})


@app.route('/profiles/<int:profile_id>', methods=['DELETE'])
def delete_profile(profile_id):
    email = get_authenticated_email()
    if not email:
        return jsonify({"error": "Not authenticated."}), 401

    conn = get_db()
    row = conn.execute("SELECT email FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if not row or row["email"] != email:
        conn.close()
        return jsonify({"error": "Profile not found."}), 404

    conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    conn.commit()
    conn.close()

    return jsonify({"success": True})



# ── CONSTANTS ──────────────────────────────────────────────────────────────

RASHIS = [
    "Mesha (Aries)", "Vrishabha (Taurus)", "Mithuna (Gemini)",
    "Karka (Cancer)", "Simha (Leo)", "Kanya (Virgo)",
    "Tula (Libra)", "Vrishchika (Scorpio)", "Dhanu (Sagittarius)",
    "Makara (Capricorn)", "Kumbha (Aquarius)", "Meena (Pisces)"
]

RASHIS_SHORT = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena"
]

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishtha",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

# Nakshatra lords in Vimshottari Dasha order
NAKSHATRA_LORDS = [
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"
]

# Dasha periods in years
DASHA_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17
}

DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]

PLANET_NAMES = {
    swe.SUN: "Sun", swe.MOON: "Moon", swe.MARS: "Mars",
    swe.MERCURY: "Mercury", swe.JUPITER: "Jupiter",
    swe.VENUS: "Venus", swe.SATURN: "Saturn",
    swe.TRUE_NODE: "Rahu"
}

# Curated Lal Kitab remedy library — paraphrased from multiple traditional sources,
# filtered to keep only safe, simple, low-cost, non-violent actions.
# Each planet has several candidate remedies; the AI selects and personalises ONE.
LANGUAGE_NAMES = {
    'en': 'English',
    'hi': 'Hindi',
    'pa': 'Punjabi',
    'ta': 'Tamil',
    'te': 'Telugu',
    'zh': 'Chinese (Simplified)'
}

LAL_KITAB_REMEDIES = {
    "Sun": [
        "Offer water to the rising Sun each morning, facing east, while taking a moment of gratitude",
        "Donate jaggery and wheat to those in need on Sundays",
        "Feed roti (flatbread) to cows on Sunday mornings",
        "Spend a few minutes in early sunlight each morning before starting your day",
        "Place a few drops of water mixed with a pinch of jaggery at the root of a tree on Sundays",
        "Offer respect and a small gesture of service to your father or a fatherly figure",
        "Avoid accepting things for free where you can, and try to earn your gains honestly this period",
        "Keep a copper coin or small copper item with you, and donate one to a temple on a Sunday",
        "Recite or quietly reflect on the Aditya Hridaya or simply offer thanks to the Sun for vitality",
        "Add a small amount of saffron or turmeric to your routine, and share food with elders"
    ],
    "Moon": [
        "Keep a small steel or copper vessel of water by your bed at night, and water a plant with it the next morning",
        "Donate rice, milk, or white sweets on Mondays",
        "Avoid difficult conversations with your mother or maternal figures on Mondays — instead offer them care",
        "Spend a few quiet minutes near water (a river, lake, or even a bath) on Monday evenings",
        "Drink water from a silver vessel, or keep a silver item with you",
        "Offer milk or water to a peepal or banyan tree on Monday mornings",
        "Keep your emotional commitments small and honest this period — do not over-promise",
        "Donate a white cloth or rice to someone genuinely in need on a Monday",
        "Spend gentle, unhurried time with your mother or a nurturing person in your life",
        "Keep a small bowl of clean water in your bedroom and refresh it daily to settle the mind"
    ],
    "Mars": [
        "Donate red lentils (masoor dal) or jaggery on Tuesdays",
        "Offer something sweet to someone in need on Tuesdays, especially before any difficult conversation",
        "Avoid starting arguments or major confrontations on Tuesdays",
        "Channel restless energy into physical activity or exercise early in the day",
        "Offer sweet water or sherbet to others, especially in warm weather",
        "Donate or distribute sweets at a temple on a Tuesday",
        "Keep a small piece of sweet jaggery with you and have a little before tense moments",
        "Plant or care for a flowering plant with red blooms",
        "Practice pausing and taking three slow breaths before reacting when provoked",
        "Help someone who is physically struggling — carry a load, assist an elder — as quiet service"
    ],
    "Mercury": [
        "Donate green moong dal or fresh green vegetables on Wednesdays",
        "Keep your work or study desk clutter-free, especially on Wednesdays",
        "Feed green leafy fodder to a cow, or simply donate to a local goshala, on Wednesdays",
        "Write down your thoughts before an important conversation on Wednesdays",
        "Donate green bangles or green cloth to young girls or those in need",
        "Keep a green plant on your desk and tend to it",
        "Avoid signing important documents impulsively on Wednesdays — read twice",
        "Offer water to a tulsi (holy basil) plant and keep it healthy",
        "Speak carefully and truthfully this period — let your words be measured",
        "Help a student or child with learning, or donate books or stationery"
    ],
    "Jupiter": [
        "Donate turmeric, chickpeas (chana dal), or yellow sweets on Thursdays",
        "Seek a few words of guidance from a teacher, mentor, or elder on Thursdays",
        "Water a tree (especially a peepal tree, if accessible) on Thursday mornings",
        "Set aside a small amount for charity each Thursday, even if modest",
        "Add a pinch of turmeric to your bath or apply a small tilak on Thursdays",
        "Offer respect and service to a teacher, guru, or knowledgeable elder",
        "Donate yellow items — gram dal, bananas, or yellow cloth — to a temple or those in need",
        "Keep a small portion of your earnings dedicated to learning or to helping others learn",
        "Feed bananas or jaggery to cows on a Thursday",
        "Begin or continue a small habit of reading something wise and uplifting each day"
    ],
    "Venus": [
        "Donate white items — rice, sugar, or white clothing — on Fridays",
        "Offer white flowers or light a lamp at a place of worship on Fridays",
        "Do something small and generous for the women in your family on Fridays",
        "Spend time on something creative or beautifying your space on Fridays",
        "Keep your surroundings clean, fragrant, and pleasant, especially your bedroom",
        "Donate perfume, fragrant items, or sweets to others on a Friday",
        "Offer kheer (rice pudding) or white sweets and share them with loved ones",
        "Express appreciation openly to your partner or those you love this period",
        "Care for a fragrant or flowering plant such as jasmine or rose",
        "Avoid harsh words in close relationships — choose softness and grace this period"
    ],
    "Saturn": [
        "Donate black sesame seeds, black lentils (urad dal), or iron items on Saturdays",
        "Feed crows or stray dogs on Saturday mornings",
        "Light a small mustard oil lamp on Saturday evenings",
        "Be extra patient with delays this period — resist the urge to force outcomes",
        "Offer service to laborers, the elderly, or those doing hard, thankless work",
        "Donate a pair of shoes, a blanket, or warm clothing to someone in need",
        "Keep your commitments faithfully this period — Saturn rewards steady discipline",
        "Light a sesame-oil lamp under a peepal tree on a Saturday evening",
        "Help an elderly or disabled person with something practical, expecting nothing back",
        "Maintain a simple, honest daily routine and avoid cutting corners"
    ],
    "Rahu": [
        "Donate mustard oil, black gram, or a coconut on Saturdays",
        "Give something to someone facing genuine hardship, without expecting anything in return",
        "Avoid shortcuts, new contracts, or impulsive decisions this period — wait a day before committing",
        "Keep your living space tidy, especially under your bed and in storage areas",
        "Float a coconut or barley in flowing water as a gesture of release (where safe and permitted)",
        "Donate a blanket or warm item to someone sleeping rough",
        "Avoid gambling, speculation, and 'too good to be true' offers this period",
        "Keep a clear head — limit intoxicants and late nights during this phase",
        "Feed stray animals quietly without seeking recognition",
        "Ground yourself daily — a short walk, bare feet on grass, or simple breathing"
    ],
    "Ketu": [
        "Donate sesame seeds or a blanket to someone in need",
        "Feed stray dogs, especially brown or black ones",
        "Spend 10 minutes in quiet reflection or meditation, with no phone nearby",
        "Let go of one small grudge or unresolved thought this period",
        "Keep a small dog-friendly gesture in your routine — water or food for strays",
        "Donate a multi-colored or grey blanket to those in need",
        "Spend a little time in solitude or prayer, away from noise and screens",
        "Care for a pet or animal, or support an animal shelter",
        "Release attachment to one outcome you have been clinging to",
        "Keep a simple spiritual practice — a few minutes of stillness each day"
    ]
}

# ── HELPERS ────────────────────────────────────────────────────────────────

# Common Indian cities/towns — lat/lng lookup (avoids slow/unreliable external geocoding calls)
CITY_COORDS = {
    "bhawanigarh": (30.2733, 75.9669),
    "sangrur": (30.2458, 75.8421),
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "bombay": (19.0760, 72.8777),
    "bangalore": (12.9716, 77.5946),
    "bengaluru": (12.9716, 77.5946),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
    "hyderabad": (17.3850, 78.4867),
    "pune": (18.5204, 73.8567),
    "ahmedabad": (23.0225, 72.5714),
    "jaipur": (26.9124, 75.7873),
    "lucknow": (26.8467, 80.9462),
    "chandigarh": (30.7333, 76.7794),
    "ludhiana": (30.9010, 75.8573),
    "amritsar": (31.6340, 74.8723),
    "patiala": (30.3398, 76.3869),
    "punjab": (30.9010, 75.8573),
    "new york": (40.7128, -74.0060),
    "london": (51.5074, -0.1278),
    "toronto": (43.6532, -79.3832),
    "dubai": (25.2048, 55.2708),
    "singapore": (1.3521, 103.8198),
}

DEFAULT_COORDS = (28.6139, 77.2090)  # New Delhi — central India fallback

def get_coordinates(place_name):
    """
    Get coordinates for a place.
    1. Check local cache first (instant, for common cities)
    2. Fall back to Open-Meteo's free geocoding API (no key required, server-side so no CORS issue)
    3. Final fallback: New Delhi (won't crash)
    """
    place_lower = place_name.lower()

    # Fast local cache for common cities
    for city, coords in CITY_COORDS.items():
        if city in place_lower:
            return coords

    # Live geocoding for anything else
    try:
        query = urllib.parse.quote(place_name.split(',')[0].strip())
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={query}&count=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (VayuMan/1.0)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        if result.get("results"):
            r = result["results"][0]
            return r["latitude"], r["longitude"]
    except Exception:
        pass

    return DEFAULT_COORDS

def datetime_to_jd(dt):
    """Convert datetime to Julian Day Number"""
    return swe.julday(
        dt.year, dt.month, dt.day,
        dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    )

def get_ayanamsa(jd):
    """Get Lahiri Ayanamsa value"""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    return swe.get_ayanamsa(jd)

def get_sidereal_position(jd, planet):
    """Get sidereal (Vedic) position of a planet"""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    flags = swe.FLG_SIDEREAL | swe.FLG_SPEED
    result, _ = swe.calc_ut(jd, planet, flags)
    return result[0]  # longitude in degrees

def longitude_to_rashi(longitude):
    """Convert ecliptic longitude to Rashi index (0-11)"""
    return int((longitude % 360) / 30) % 12

def longitude_to_degree_in_rashi(longitude):
    """Get degrees within a Rashi"""
    return (longitude % 30 + 30) % 30

def get_nakshatra(moon_longitude):
    """Get Nakshatra from Moon's sidereal longitude"""
    moon_longitude = moon_longitude % 360
    nak_index = int(moon_longitude / (360 / 27)) % 27
    nak_pada = int((moon_longitude % (360 / 27)) / (360 / 108)) + 1
    return {
        "index": nak_index,
        "name": NAKSHATRAS[nak_index],
        "pada": nak_pada,
        "lord": NAKSHATRA_LORDS[nak_index % 9]
    }

def get_lagna(jd, lat, lon):
    """Calculate Lagna (Ascendant) using Swiss Ephemeris"""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    cusps, ascmc = swe.houses(jd, lat, lon, b'W')  # Whole sign houses
    ayanamsa = get_ayanamsa(jd)
    tropical_asc = ascmc[0]
    sidereal_asc = (tropical_asc - ayanamsa) % 360
    return sidereal_asc

def calculate_vimshottari_dasha(moon_longitude, birth_jd):
    """
    Calculate current Vimshottari Dasha and Antardasha
    Based on Moon's Nakshatra at birth
    """
    nakshatra = get_nakshatra(moon_longitude)
    nak_lord = nakshatra["lord"]
    nak_lord_index = DASHA_ORDER.index(nak_lord)

    # Degrees elapsed in current nakshatra at birth
    nak_size = 360 / 27  # 13.333...degrees
    degrees_in_nak = moon_longitude % nak_size
    fraction_elapsed = degrees_in_nak / nak_size

    # Years elapsed in first dasha at birth
    first_dasha_years = DASHA_YEARS[nak_lord]
    years_elapsed_at_birth = fraction_elapsed * first_dasha_years

    # Build dasha timeline from birth
    birth_dt = swe.revjul(birth_jd)
    birth_date = datetime(int(birth_dt[0]), int(birth_dt[1]), int(birth_dt[2]))

    dashas = []
    current_date = birth_date
    # Subtract already-elapsed portion of first dasha
    from dateutil.relativedelta import relativedelta

    # Start of first dasha (before birth)
    days_elapsed = years_elapsed_at_birth * 365.25
    dasha_start = birth_date - relativedelta(days=int(days_elapsed))

    for i in range(9):
        lord_index = (nak_lord_index + i) % 9
        lord = DASHA_ORDER[lord_index]
        years = DASHA_YEARS[lord]
        dasha_end = dasha_start + relativedelta(years=years)
        dashas.append({
            "lord": lord,
            "start": dasha_start.strftime("%Y-%m-%d"),
            "end": dasha_end.strftime("%Y-%m-%d"),
            "years": years
        })
        dasha_start = dasha_end

    # Find current dasha
    today = datetime.utcnow()
    current_dasha = None
    current_antardasha = None

    for dasha in dashas:
        d_start = datetime.strptime(dasha["start"], "%Y-%m-%d")
        d_end = datetime.strptime(dasha["end"], "%Y-%m-%d")
        if d_start <= today <= d_end:
            current_dasha = dasha

            # Calculate Antardasha within current Mahadasha
            total_days = (d_end - d_start).days
            ad_start = d_start
            for j in range(9):
                ad_lord_index = (DASHA_ORDER.index(dasha["lord"]) + j) % 9
                ad_lord = DASHA_ORDER[ad_lord_index]
                ad_years = DASHA_YEARS[ad_lord]
                ad_days = int((ad_years / 120) * DASHA_YEARS[dasha["lord"]] * 365.25)
                ad_end = ad_start + relativedelta(days=ad_days)

                if ad_start <= today <= ad_end:
                    current_antardasha = {
                        "lord": ad_lord,
                        "start": ad_start.strftime("%Y-%m-%d"),
                        "end": ad_end.strftime("%Y-%m-%d")
                    }
                    break
                ad_start = ad_end
            break

    return {
        "mahadasha": current_dasha,
        "antardasha": current_antardasha,
        "timeline": dashas[:5]  # Next 5 dashas
    }

def get_all_planets(jd, lagna_rashi_idx=0):
    """Get sidereal positions of all 9 Vedic planets, including house number relative to Lagna"""
    planets = {}
    for planet_id, planet_name in PLANET_NAMES.items():
        try:
            lon = get_sidereal_position(jd, planet_id)
            rashi_idx = longitude_to_rashi(lon)
            deg_in_rashi = longitude_to_degree_in_rashi(lon)
            house = ((rashi_idx - lagna_rashi_idx) % 12) + 1
            planets[planet_name] = {
                "longitude": round(lon, 4),
                "rashi": RASHIS_SHORT[rashi_idx],
                "rashi_index": rashi_idx,
                "degree": round(deg_in_rashi, 2),
                "house": house
            }
        except Exception:
            pass

    # Ketu = Rahu + 180
    if "Rahu" in planets:
        ketu_lon = (planets["Rahu"]["longitude"] + 180) % 360
        ketu_rashi = longitude_to_rashi(ketu_lon)
        ketu_house = ((ketu_rashi - lagna_rashi_idx) % 12) + 1
        planets["Ketu"] = {
            "longitude": round(ketu_lon, 4),
            "rashi": RASHIS_SHORT[ketu_rashi],
            "rashi_index": ketu_rashi,
            "degree": round(longitude_to_degree_in_rashi(ketu_lon), 2),
            "house": ketu_house
        }

    return planets

def detect_doshas(planets, lagna_rashi_idx, moon_rashi_idx, jd):
    """
    Detect common doshas from the birth chart.
    Returns a list of {name, present, description} dicts.
    Keeps to widely-used, computable definitions:
      - Mangal Dosha (Mars in houses 1,2,4,7,8,12 from Lagna)
      - Kaal Sarp Dosha (all 7 classical planets between Rahu and Ketu)
      - Sade Sati (current transiting Saturn within 1 sign of natal Moon)
    """
    doshas = []

    # ── Mangal Dosha (Mars Dosha) ──
    mars_house = planets.get("Mars", {}).get("house")
    manglik_houses = [1, 2, 4, 7, 8, 12]
    is_manglik = mars_house in manglik_houses
    doshas.append({
        "name": "Mangal Dosha (Mars Dosha)",
        "present": is_manglik,
        "description": (
            f"Mars sits in a position (house {mars_house}) that classically forms Mangal Dosha — "
            "often associated with added intensity or friction in close relationships and partnerships."
            if is_manglik else
            "Mars is not placed in a position that forms Mangal Dosha in this chart."
        )
    })

    # ── Kaal Sarp Dosha ──
    rahu_lon = planets.get("Rahu", {}).get("longitude")
    ketu_lon = planets.get("Ketu", {}).get("longitude")
    is_kaal_sarp = False
    if rahu_lon is not None and ketu_lon is not None:
        other_planets = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
        other_lons = [planets[p]["longitude"] for p in other_planets if p in planets]

        def in_arc(lon, start, end):
            # Is `lon` within the arc going clockwise from start to end?
            if start <= end:
                return start <= lon <= end
            return lon >= start or lon <= end

        all_on_one_side = all(in_arc(p, rahu_lon, ketu_lon) for p in other_lons) or \
                           all(in_arc(p, ketu_lon, rahu_lon) for p in other_lons)
        is_kaal_sarp = all_on_one_side

    doshas.append({
        "name": "Kaal Sarp Dosha",
        "present": is_kaal_sarp,
        "description": (
            "All major planets fall on one side of the Rahu-Ketu axis, forming Kaal Sarp Dosha — "
            "traditionally linked to delays and obstacles that often resolve later in life, "
            "sometimes bringing unexpected strength once worked through."
            if is_kaal_sarp else
            "Planets are distributed on both sides of the Rahu-Ketu axis — Kaal Sarp Dosha is not present."
        )
    })

    # ── Sade Sati (current transit of Saturn relative to natal Moon) ──
    try:
        now = datetime.utcnow()
        jd_now = datetime_to_jd(now)
        saturn_now_lon = get_sidereal_position(jd_now, swe.SATURN)
        saturn_now_rashi = longitude_to_rashi(saturn_now_lon)

        # Sade Sati = transiting Saturn in the 12th, 1st, or 2nd sign from natal Moon sign
        diff = (saturn_now_rashi - moon_rashi_idx) % 12
        is_sade_sati = diff in [11, 0, 1]  # 12th, 1st (same), 2nd

        phase = None
        if diff == 11:
            phase = "first phase (rising)"
        elif diff == 0:
            phase = "peak phase"
        elif diff == 1:
            phase = "final phase (waning)"

        doshas.append({
            "name": "Sade Sati",
            "present": is_sade_sati,
            "description": (
                f"Saturn is currently transiting in its Sade Sati position relative to your Moon sign — "
                f"the {phase}. This 7.5-year cycle often brings significant life restructuring, lessons in "
                "patience, and long-term growth, even if it feels heavy at times."
                if is_sade_sati else
                "Saturn is not currently in a Sade Sati transit relative to your Moon sign."
            )
        })
    except Exception:
        pass

    return doshas



@app.route('/chart', methods=['POST'])
def calculate_chart():
    """
    POST /chart
    Body: { "dob": "1985-03-12", "tob": "18:59", "pob": "Bhawanigarh, Punjab, India" }
    Returns: Full Vedic chart data
    """
    try:
        data = request.get_json()
        dob = data.get('dob')          # "YYYY-MM-DD"
        tob = data.get('tob')          # "HH:MM"
        pob = data.get('pob')          # "City, Country"

        if not all([dob, tob, pob]):
            return jsonify({"error": "Missing required fields: dob, tob, pob"}), 400

        # Parse date and time
        dt_str = f"{dob} {tob}"
        dt_local = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")

        # Get coordinates
        lat, lon = get_coordinates(pob)
        if lat is None:
            # Fallback to Bhawanigarh coordinates
            lat, lon = 30.2733, 75.9669

        # Convert to UTC using a longitude-based standard-time offset estimate.
        # This is a zero-dependency approach (no external timezone library):
        # most countries' standard time zones are within ~1 hour of solar
        # longitude/15, and several major regions use well-known fixed
        # offsets that don't align to whole hours (e.g. India = UTC+5:30).
        # NOTE: this ignores daylight-saving time and historical zone
        # changes. It's a reasonable approximation for astrology purposes,
        # where Lagna can shift with birth time precision anyway.
        from datetime import timezone, timedelta

        def estimate_utc_offset(lat, lon):
            # Known fixed-offset regions (approximate bounding boxes)
            # India / Sri Lanka: UTC+5:30
            if 6 <= lat <= 37 and 68 <= lon <= 97:
                return timedelta(hours=5, minutes=30)
            # Afghanistan: UTC+4:30
            if 29 <= lat <= 39 and 60 <= lon <= 75:
                return timedelta(hours=4, minutes=30)
            # Iran: UTC+3:30
            if 25 <= lat <= 40 and 44 <= lon <= 64:
                return timedelta(hours=3, minutes=30)
            # Myanmar: UTC+6:30
            if 9 <= lat <= 29 and 92 <= lon <= 102:
                return timedelta(hours=6, minutes=30)
            # Default: round longitude to the nearest 15° (1-hour zone)
            hours = round(lon / 15)
            return timedelta(hours=hours)

        offset = estimate_utc_offset(lat, lon)
        tz_name = f"UTC{'+' if offset.total_seconds() >= 0 else '-'}{abs(offset)}"

        dt_aware = dt_local.replace(tzinfo=timezone(offset))
        dt_utc = dt_aware.astimezone(timezone.utc)

        # Julian Day
        jd = datetime_to_jd(dt_utc)

        # Calculate Lagna
        lagna_lon = get_lagna(jd, lat, lon)
        lagna_rashi_idx = longitude_to_rashi(lagna_lon)
        lagna_degree = longitude_to_degree_in_rashi(lagna_lon)

        # Moon position
        moon_lon = get_sidereal_position(jd, swe.MOON)
        moon_rashi_idx = longitude_to_rashi(moon_lon)

        # Nakshatra
        nakshatra = get_nakshatra(moon_lon)

        # All planets
        planets = get_all_planets(jd, lagna_rashi_idx)

        # Dasha
        dasha = calculate_vimshottari_dasha(moon_lon, jd)

        # Doshas
        doshas = detect_doshas(planets, lagna_rashi_idx, moon_rashi_idx, jd)

        # Build response
        response = {
            "lagna": {
                "rashi": RASHIS[lagna_rashi_idx],
                "rashi_short": RASHIS_SHORT[lagna_rashi_idx],
                "rashi_index": lagna_rashi_idx,
                "degree": round(lagna_degree, 2),
                "longitude": round(lagna_lon, 4)
            },
            "moon": {
                "rashi": RASHIS[moon_rashi_idx],
                "rashi_short": RASHIS_SHORT[moon_rashi_idx],
                "longitude": round(moon_lon, 4),
                "nakshatra": nakshatra
            },
            "dasha": dasha,
            "doshas": doshas,
            "planets": planets,
            "meta": {
                "latitude": round(lat, 4),
                "longitude_geo": round(lon, 4),
                "julian_day": round(jd, 6),
                "ayanamsa": "Lahiri",
                "house_system": "Whole Sign",
                "timezone": tz_name
            }
        }

        return jsonify(response)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


class RateLimitError(Exception):
    """Raised when the AI provider returns a 429 (rate/quota limit)."""
    pass


# ── ASK VAYUMAN — DATA SUFFICIENCY GATE (Stage A, deterministic) ───────────
# Runs in plain Python before any AI call. The point: whether required data
# is missing must never be left for the LLM to notice mid-generation — that's
# how you get a confident "neutral" verdict invented over missing data. This
# gate decides sufficiency up front, and the prompt is then told explicitly
# what it may and may not claim.

SECOND_PERSON_PATTERN = re.compile(
    r'(?i)\b(wife|husband|spouse|partner|girlfriend|boyfriend|fianc[ée]e?|'
    r'friend|colleague|coworker|son|daughter|child|brother|sister|'
    r'mother|father|brand|business|company|product|baby|'
    r'person|someone|him|her|them|this (?:guy|girl|man|woman))\b'
)
COMPATIBILITY_KEYWORDS = re.compile(
    r'(?i)\b(resonate|compatib|match(?:es)?|suit(?:s|able)?|right for me|good for me|'
    r'connection|chemistry|work out|meant to be)\b'
)
TIMING_KEYWORDS = re.compile(
    r'(?i)\b(when will|what year|how soon|timing|will i ever|by when|this year|next year)\b'
)
HEALTH_KEYWORDS = re.compile(
    r'(?i)\b(illness|disease|health|sick|diagnos|pregnan|surgery|\bdie\b|death)\b'
)

# Answers containing any of these, when the gate found insufficient data,
# indicate the AI invented a verdict anyway — caught in Stage C below.
VERDICT_WORDS = re.compile(
    r'(?i)\b(resonates?|compatible|neutral energy|the energy feels|verdict:|strong (?:match|connection))\b'
)
NOT_CALCULATED_PHRASES = re.compile(
    r'(?i)(not calculated|not provided|we\'?d need|let\'?s assume|no direct calculation)'
)


def check_sufficiency(question, has_named_target=False):
    """
    Stage A — deterministic, no LLM call.
    has_named_target: True if a second person's data was actually extractable
    (e.g. a name was detected and calculated). Neither current app flow
    collects a partner's DOB/chart, so this is always about whether a NAME
    was given, not full birth data.
    """
    references_second_person = bool(SECOND_PERSON_PATTERN.search(question))
    asks_compatibility = bool(COMPATIBILITY_KEYWORDS.search(question))
    needs_target_data = references_second_person and asks_compatibility
    return {
        "needs_target_data": needs_target_data,
        "target_data_available": has_named_target,
        "insufficient": needs_target_data and not has_named_target,
        "asks_timing": bool(TIMING_KEYWORDS.search(question)),
        "touches_health": bool(HEALTH_KEYWORDS.search(question)),
    }


def violates_sufficiency_contract(answer_text, gate):
    """
    Stage C — deterministic post-check. If the gate found insufficient data
    but the answer contains a verdict word, OR contains one of the banned
    'not calculated' phrases we explicitly forbid, flag it so the caller can
    fall back to a safe template instead of showing a bad answer.
    """
    if gate["insufficient"] and VERDICT_WORDS.search(answer_text or ""):
        return True
    if NOT_CALCULATED_PHRASES.search(answer_text or ""):
        return True
    return False


# Which model provider to use: 'gemini' (default) or 'groq'.
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'gemini').lower()
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')


def call_gemini(prompt, api_key, temperature=0.9, max_tokens=2600):
    """Call Google's Gemini API and return the raw text response."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={api_key}")
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimitError("Vayuman is experiencing very high demand right now. "
                                 "Please try again in a few minutes.")
        raise

    # Extract text from Gemini's response structure
    try:
        parts = result["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError):
        # If blocked or empty, surface a clean error
        raise RuntimeError("The AI returned an empty response. Please try again.")


def call_groq(prompt, api_key, temperature=0.9, max_tokens=2600):
    """Call Groq's chat completion API and return the raw text response."""
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens
    }).encode('utf-8')

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (VayuMan/1.0)"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        # Surface rate limits as a clean, user-friendly signal
        if e.code == 429:
            raise RateLimitError("Vayuman is experiencing very high demand right now. "
                                 "Please try again in a few minutes.")
        raise

    return result["choices"][0]["message"]["content"]


def call_ai(prompt, temperature=0.9, max_tokens=2600):
    """Unified AI call. Uses the configured provider (Gemini by default), and
    automatically falls back to the other provider on failure/rate-limit if
    that provider's key is available."""
    gemini_key = os.environ.get('GEMINI_API_KEY')
    groq_key = os.environ.get('GROQ_API_KEY')

    primary = AI_PROVIDER
    # Build ordered provider list (primary first, the other as fallback)
    order = ['gemini', 'groq'] if primary == 'gemini' else ['groq', 'gemini']

    last_err = None
    for prov in order:
        try:
            if prov == 'gemini' and gemini_key:
                return call_gemini(prompt, gemini_key, temperature, max_tokens)
            if prov == 'groq' and groq_key:
                return call_groq(prompt, groq_key, temperature, max_tokens)
        except RateLimitError as e:
            last_err = e
            continue  # try the fallback provider
        except Exception as e:
            last_err = e
            continue
    # If we got here, everything failed
    if isinstance(last_err, RateLimitError):
        raise last_err
    if last_err:
        raise last_err
    raise RuntimeError("No AI provider is configured. Set GEMINI_API_KEY or GROQ_API_KEY.")


@app.route('/reading', methods=['POST'])
def generate_reading():
    """
    POST /reading
    Body: { "name": "...", "lagna": "...", "rashi": "...", "nakshatra": "...",
            "pada": 1, "dashaLord": "...", "today": "...", "focus": "..." }
    Returns: AI-generated reading JSON (today, love, career, health, finance, action)
    Calls Groq API server-side — avoids browser CORS issues and keeps API key secret.
    """
    try:
        data = request.get_json()
        if not (os.environ.get('GEMINI_API_KEY') or os.environ.get('GROQ_API_KEY')):
            return jsonify({"error": "Server not configured: missing AI provider key"}), 500

        focus_labels = {
            'general': 'overall life',
            'career': 'career',
            'relationships': 'love and relationships',
            'health': 'health and wellbeing',
            'finances': 'finances and abundance',
            'studies': 'studies and personal growth'
        }
        is_minor = bool(data.get('is_minor', False))
        # A minor's chart is always a study-focused reading
        focus_key = 'studies' if is_minor else data.get('focus', 'general')
        focus_label = focus_labels.get(focus_key, 'overall life')

        planets_summary = data.get('planets_summary', '')
        antardasha = data.get('antardasha', '')
        dasha_lord = data.get('dashaLord', '')
        active_doshas_raw = data.get('active_doshas', '') or ''
        active_doshas_lower = active_doshas_raw.lower()

        # First name only, with first letter capitalized, for direct address
        full_name = (data.get('name') or 'Seeker').strip()
        first_name = full_name.split()[0] if full_name.split() else 'Seeker'
        first_name = first_name[:1].upper() + first_name[1:] if first_name else 'Seeker'

        # Traditional significator planet for each focus area
        FOCUS_SIGNIFICATORS = {
            'career': 'Saturn',
            'relationships': 'Venus',
            'health': 'Mars',
            'finances': 'Jupiter'
        }

        # Which doshas make a remedy genuinely relevant for each focus area.
        # (Rule: a focused reading shows a remedy ONLY if one of these doshas
        # is actually active in the chart — otherwise no remedy is shown.)
        FOCUS_RELEVANT_DOSHAS = {
            'relationships': ['mangal'],                      # Mars/marriage affliction
            'career': ['sade sati', 'kaal sarp'],            # Saturn pressure / blocked momentum
            'health': ['mangal', 'kaal sarp'],               # vitality/accident-prone afflictions
            'finances': ['kaal sarp'],                       # blocked flow / obstacles
        }

        # ── Decide whether a remedy applies ──────────────────────────────────
        # General reading: always include a remedy (tied to the dasha lord).
        # Focused reading: include a remedy ONLY if a relevant dosha is active.
        remedy_lord = None
        chosen_remedy = None
        remedy_applies = True

        if is_minor:
            # Never show remedies for a minor's chart.
            remedy_applies = False
        elif focus_key in FOCUS_SIGNIFICATORS:
            relevant = FOCUS_RELEVANT_DOSHAS.get(focus_key, [])
            dosha_present = any(d in active_doshas_lower for d in relevant)
            if dosha_present:
                remedy_lord = FOCUS_SIGNIFICATORS[focus_key]
            else:
                remedy_applies = False   # focused reading, no relevant dosha → no remedy
        else:
            # general reading
            if dasha_lord in LAL_KITAB_REMEDIES:
                remedy_lord = dasha_lord
            elif antardasha in LAL_KITAB_REMEDIES:
                remedy_lord = antardasha
            else:
                remedy_lord = "Jupiter"

        if remedy_applies:
            remedy_options = LAL_KITAB_REMEDIES.get(remedy_lord, LAL_KITAB_REMEDIES["Jupiter"])
            # Deterministic per-person pick (stable but varied across people)
            seed_str = f"{data.get('name','')}{data.get('dob','')}{remedy_lord}"
            option_index = sum(ord(c) for c in seed_str) % len(remedy_options)
            chosen_remedy = remedy_options[option_index]

            remedy_instruction_text = (
                f"The remedy has ALREADY been chosen for this person — it relates to {remedy_lord}. "
                f"REMEDY_NAME must restate this remedy (you may lightly rephrase for natural flow, "
                f"but keep the core action, object, and timing intact — do not change it to a "
                f"different remedy or different planet):\n\"{chosen_remedy}\"\n"
                f"REMEDY_WHY must explain in one sentence why this remedy is relevant"
                f"{' to ' + focus_label + ' specifically' if focus_key != 'general' else ''}, "
                f"connected to this person's chart."
            )
        else:
            # No remedy for this focused reading — instruct the AI to omit it.
            remedy_instruction_text = (
                "Do NOT include any remedy for this reading. Leave REMEDY_NAME, REMEDY_WHY, and "
                "REMEDY_HOW completely empty. There is no chart affliction that calls for a remedy "
                f"in the area of {focus_label} right now, and it would be dishonest to invent one."
            )

        lang_code = data.get('lang', 'en')
        lang_name = LANGUAGE_NAMES.get(lang_code, 'English')

        # Past→present→future arc — only for general and relationships readings
        # (never for a minor's study reading).
        if not is_minor and focus_key in ('general', 'relationships'):
            time_arc_instruction = (
                "TIME ARC (important for this reading): Weave a vivid past -> present -> future thread "
                "into the TODAY field. Open with a brief, recognisable nod to the longer chapter they "
                f"have been moving through (their current Mahadasha of {dasha_lord} and Antardasha of "
                f"{antardasha}, which unfold over months and years). Then center firmly on the present. "
                "Then give a CONFIDENT, SPECIFIC forward outlook covering roughly the next three years: "
                "name the next major dasha/antardasha shift and, where relevant, give a concrete timing "
                "WINDOW with approximate years or seasons (e.g. 'the window opening in late 2026 looks "
                "especially favourable for...', 'the period around 2027 is a strong one for...'). "
                "Speak with warm confidence ('this is a strong window', 'the period ahead is especially "
                "favourable for...') rather than hedging every line with 'maybe'. IMPORTANT: still never "
                "state a fabricated hard guarantee or a single fixed date as certain fact (do not say 'you "
                "WILL marry in 2027'); frame timing as a strong, favourable window or likely period. The "
                "reading should feel specific, personal, and confident — not a string of vague maybes — "
                "while remaining an honest favourable-window forecast rather than a guarantee. "
                "Keep it warm and grounded."
            )
        else:
            time_arc_instruction = ""

        # ── Minor-chart safety mode ──────────────────────────────────────────
        # The app user is an adult, but this chart belongs to a minor (under 18),
        # e.g. a parent/guardian consulting about their child. The reading must
        # be written ABOUT the child, addressed to the caring adult reading it.
        if is_minor:
            minor_instruction = (
                f"\n\nIMPORTANT — THIS CHART BELONGS TO A MINOR (a child under 18). "
                f"The reader is the child's parent or guardian, NOT the child. This reading is "
                f"\"{first_name}'s Inner Compass\" — a warm, holistic portrait of who this child is and who they "
                f"are naturally becoming. Follow ALL of these rules:\n"
                f"- Write entirely in the THIRD PERSON about the child (use their first name '{first_name}' and "
                f"'they/them' — e.g. '{first_name} is a curious, warm-hearted child'). NEVER address the child directly.\n"
                f"- Speak TO the parent/guardian, helping them truly understand and nurture their child.\n"
                f"- Cover a RICH, HOLISTIC picture of the child, drawn from their actual chart:\n"
                f"   • their core nature and temperament (how they experience the world)\n"
                f"   • their natural strengths, gifts, and talents\n"
                f"   • their interests and what naturally draws their curiosity\n"
                f"   • how they learn best and engage with studies\n"
                f"   • their practical/emotional/social tendencies\n"
                f"   • the kinds of paths and fields they may naturally lean toward as they grow — whether creative, "
                f"analytical, entrepreneurial/business-minded, structured roles, hands-on, helping/service-oriented, "
                f"intellectual, etc. — framed ALWAYS as gentle, non-deterministic inclinations to nurture "
                f"('may be drawn toward', 'shows a natural leaning to', 'could flourish in'), NEVER as fixed predictions.\n"
                f"   • their spiritual and inner qualities — sensitivity, values, depth, inner life\n"
                f"- Explicitly encourage the involvement, patience, and loving guidance of parents/guardians at least "
                f"once, including how they can best support the child's unfolding.\n"
                f"- ABSOLUTELY NO romantic, relationship, marriage, or any adult content of any kind. This is non-negotiable. "
                f"Do not discuss the child's future marriage or love life.\n"
                f"- Do NOT prescribe any remedy, ritual, fast, gemstone, or remedial action. Leave all remedy fields empty.\n"
                f"- Keep the tone gentle, hopeful, age-appropriate, warm, and reassuring. Avoid anything frightening, "
                f"fatalistic, or that could worry a parent unnecessarily.\n"
                f"- The [TODAY] field is the heart of this reading — make it the rich Inner Compass portrait described "
                f"above. Open it by naming the child ('{first_name} ...') in third person, not by addressing them. "
                f"Make it warm, specific to their chart, and genuinely insightful for a parent — not generic.\n"
            )
        else:
            minor_instruction = ""

        # Native planet-name guidance per language so output reads as PURE
        # target-language text (not English planet names dropped into Hindi, etc.)
        PLANET_NATIVE = {
            'hi': "Use the natural Hindi names for planets in Devanagari: Sun=सूर्य, Moon=चंद्र, Mars=मंगल, Mercury=बुध, Jupiter=गुरु/बृहस्पति, Venus=शुक्र, Saturn=शनि, Rahu=राहु, Ketu=केतु.",
            'pa': "Use the natural Punjabi (Gurmukhi) names for planets: Sun=ਸੂਰਜ, Moon=ਚੰਦ, Mars=ਮੰਗਲ, Mercury=ਬੁੱਧ, Jupiter=ਗੁਰੂ/ਬ੍ਰਿਹਸਪਤੀ, Venus=ਸ਼ੁੱਕਰ, Saturn=ਸ਼ਨੀ, Rahu=ਰਾਹੂ, Ketu=ਕੇਤੂ.",
            'ta': "Use the natural Tamil names for planets: Sun=சூரியன், Moon=சந்திரன், Mars=செவ்வாய், Mercury=புதன், Jupiter=குரு/வியாழன், Venus=சுக்கிரன், Saturn=சனி, Rahu=ராகு, Ketu=கேது.",
            'te': "Use the natural Telugu names for planets: Sun=సూర్యుడు, Moon=చంద్రుడు, Mars=కుజుడు/అంగారకుడు, Mercury=బుధుడు, Jupiter=గురువు/బృహస్పతి, Venus=శుక్రుడు, Saturn=శని, Rahu=రాహువు, Ketu=కేతువు.",
            'zh': "Use the natural Chinese names for planets: Sun=太阳, Moon=月亮, Mars=火星, Mercury=水星, Jupiter=木星, Venus=金星, Saturn=土星, Rahu=罗睺, Ketu=计都.",
        }

        if lang_code == 'en':
            language_instruction = (
                "Respond entirely in English. Use the standard ENGLISH planet names only "
                "(Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu) — do NOT use "
                "Sanskrit planet names like Surya, Chandra, Mangal, Shani, etc."
            )
        else:
            native_planets = PLANET_NATIVE.get(lang_code, "")
            language_instruction = (
                f"Respond ENTIRELY and PURELY in {lang_name}, written naturally and fluently in {lang_name}'s "
                f"native script (not transliterated/romanized). Every field below must be in {lang_name} — "
                f"the planetary influences, today's insight, all life areas, the action, the remedy "
                f"(translate the remedy instruction itself into {lang_name} too, keeping its core "
                f"action and timing intact), and the dosha note. "
                f"{native_planets} "
                f"Do NOT drop English planet names into the {lang_name} text — always use the native {lang_name} planet names given above. "
                f"Keep only 'Vayuman' as-is. Write ALL sentences in pure {lang_name} with no English words mixed in "
                f"(except 'Vayuman'). "
            )

        prompt = f"""You are Vayuman — a deeply wise, emotionally intelligent Vedic astrologer. Your voice is calm, warm, and human, and you never use jargon. But beneath that warmth you are a RIGOROUS, PRECISE astrologer: every interpretation you give is derived from the specific planetary placements in the person's actual birth chart — their signs, houses, nakshatra, and dasha periods. You read the real chart in front of you and translate exactly what THOSE placements mean into plain, human language. You never give generic horoscope-style statements that could apply to anyone; a reading from you is unmistakably tailored to this one specific chart.

{"" if focus_key == "general" else f'''⚠️ THIS IS A FOCUSED READING ABOUT: {focus_label.upper()} ⚠️
{data.get("name", "Seeker")} specifically asked for guidance on {focus_label} — NOT a general life overview. The [TODAY] field below MUST be a deep, dedicated analysis of {focus_label} specifically. Do not write a generic "your day overall" summary. Every sentence in [TODAY] should relate to {focus_label}.
'''}
Generate a personalised, REAL-TIME Vedic astrology reading for {data.get('name', 'Seeker')} for {data.get('today')}.

Their Vedic chart details:
- Lagna (Ascendant): {data.get('lagna')}
- Moon Sign (Rashi): {data.get('rashi')}
- Nakshatra: {data.get('nakshatra')} (Pada {data.get('pada')})
- Current Mahadasha: {data.get('dashaLord')}
- Current Antardasha: {antardasha}
- Planetary placements (house positions relative to their Lagna): {planets_summary}
- Active doshas in this chart: {data.get('active_doshas', 'None notable')}
- PRIMARY FOCUS REQUESTED: {focus_label.upper()}{"" if focus_key == "general" else " (THIS IS NOT A GENERAL READING — see warning above)"}

LANGUAGE: {language_instruction}
{minor_instruction}

{time_arc_instruction}

CRITICAL INSTRUCTIONS:
0. The "today" field MUST open by addressing {first_name} directly by first name in the first sentence. This is required, not optional.

ACCURACY IS THE TOP PRIORITY. This reading must be so specific to {first_name}'s actual chart that it could NOT have been written for anyone else. A generic reading is a failed reading. To achieve this:
- Before writing each field, silently reason about the ACTUAL placements given above: which sign each relevant planet is in, which house it occupies, and what that specific sign+house COMBINATION means for {focus_label}. (e.g. "Venus in Scorpio in the 7th house" means something very different from "Venus in Taurus in the 2nd" — intense, all-or-nothing relationships vs. steady, security-seeking ones.)
- Every claim you make must be traceable to a specific placement in the data — the sign, the house, the dasha lord, or an active dosha. If you cannot tie a sentence to a real placement, delete it.
- Name concrete, real-life specifics: the actual life areas, tensions, dynamics, and tendencies that THESE placements produce — not universal statements that apply to everyone.

1. The "today" field MUST be primarily about {focus_label}. Ground it explicitly in the relevant planets for {focus_label}: for love/relationships look at Venus, the 7th house ruler and any planets in the 5th/7th; for career look at Saturn, the Sun, the 10th house and its occupants; for finances look at Jupiter, the 2nd and 11th houses; for health look at the Lagna lord, Mars, the 1st/6th houses. Read what their SPECIFIC signs and houses say, and translate that into plain language.
2. Do NOT default to generic "overall life" advice. Two different people must get visibly different readings because their placements differ. Make the sign+house specifics audible in the wording.
3. Ban vague filler entirely ("things will work out", "stay positive", "trust the universe", "a sense of new beginnings", "embrace the journey"). Instead, name the actual dynamic: what specifically tends to go right, what specifically creates friction, and why — based on the placements. It is good and honest to name a real challenge tied to a difficult placement.
4. Vary sentence rhythm and word choice — do not reuse the same openings or phrases across focus areas or across planets.
5. For "planetary_influences": pick the 3 most significant planets right now (always include the Mahadasha lord {data.get('dashaLord')} and Antardasha lord {antardasha}, plus one more genuinely relevant to {focus_label}). For each, describe in ONE plain-language sentence what that planet — IN ITS SPECIFIC SIGN AND HOUSE — is doing in {first_name}'s real life right now. Translate the placement into a felt, real-world effect (e.g. "Saturn moving through your house of partnerships is asking you to take a relationship more seriously, or to let go of one that has run its course"). Keep the language plain and free of technical jargon, but the EFFECT you describe must come from the actual placement, not a generic planet trait.
6. {remedy_instruction_text}
7. If any doshas are listed as active above, briefly acknowledge EACH ONE in the DOSHA_NOTE field (not just one) — calm, factual, never alarming, one short sentence per dosha. If "None notable" or empty, write DOSHA_NOTE as a short reassuring note that no major doshas are currently active.
{"" if focus_key == "general" else f'''8. FINAL CHECK before writing [TODAY]: re-read it after drafting — if it could apply to someone who asked about a DIFFERENT focus area (or no focus at all), or to a person with DIFFERENT placements, rewrite it. It must be unmistakably about {focus_label} AND unmistakably about {first_name}'s specific chart.'''}
9. CONFIDENCE & TIMING: Write with warm confidence, not constant hedging. When timing is relevant, give concrete, satisfying timing WINDOWS grounded in the dasha/antardasha periods and transits — name approximate years or seasons (e.g. "the window opening in late 2026 is especially favourable", "the period around 2027 looks strong for this"). People value a little specificity. Do NOT bury the reading in "maybe / perhaps / it's possible" on every line. BUT never fabricate a hard guarantee or a single fixed date stated as certain fact (not "you WILL marry in 2027"); frame timing as a strong, favourable window or likely period. Specific and confident, yet still an honest favourable-window forecast — never a guarantee.

Write your reading using EXACTLY this format — plain text with delimiter tags, no JSON, no markdown, no backticks. Write naturally, including apostrophes and quotes as needed within the text:

[INFLUENCE1_PLANET]PlanetName[/INFLUENCE1_PLANET]
[INFLUENCE1_HEADLINE]3-5 word real-life headline, e.g. Career momentum building[/INFLUENCE1_HEADLINE]
[INFLUENCE1_EFFECT]One plain-language sentence on what this planet is doing in their life right now.[/INFLUENCE1_EFFECT]
[INFLUENCE2_PLANET]PlanetName[/INFLUENCE2_PLANET]
[INFLUENCE2_HEADLINE]...[/INFLUENCE2_HEADLINE]
[INFLUENCE2_EFFECT]...[/INFLUENCE2_EFFECT]
[INFLUENCE3_PLANET]PlanetName[/INFLUENCE3_PLANET]
[INFLUENCE3_HEADLINE]...[/INFLUENCE3_HEADLINE]
[INFLUENCE3_EFFECT]...[/INFLUENCE3_EFFECT]
[TODAY]MUST begin by addressing the person directly by their first name "{first_name}" in the very first sentence (e.g. "{first_name}, ..."). Then continue with {"4-5 sentences, primarily about overall life, written with warm confidence and grounded specificity — name the actual dynamics their placements produce and, where timing is relevant, give a concrete favourable window (approximate years/seasons, e.g. 'the period around 2027 looks especially strong for...'), never vague 'maybe' filler" if focus_key == "general" else f"6-8 sentences, primarily and DEEPLY about {focus_label}"}, grounded in their actual planetary placements. Specific, real, and direct — not generic.{"" if focus_key == "general" else " Since this is a focused reading, go beyond surface-level: analyze the current planetary influences on this specific area in practical detail — what's actively helping, what's creating friction, realistic timing considerations, and what a thoughtful person in this position should actually understand about their situation right now."}[/TODAY]
{"" if focus_key != "general" else '''[LOVE]2-3 sentences about relationships right now, grounded in the actual Venus / 7th-house placements. Be specific and confident — name the real dynamic, and where timing matters give a concrete favourable window (approximate year/season), not vague filler. Never a fabricated guarantee.[/LOVE]
[CAREER]2-3 sentences about work and purpose right now, grounded in the actual Saturn / Sun / 10th-house placements. Specific and confident, with a concrete timing window where relevant.[/CAREER]
[HEALTH]2-3 sentences about energy and physical wellbeing right now, grounded in the Lagna lord / Mars / 1st-6th house placements. Specific and practical, with timing where relevant.[/HEALTH]
[FINANCE]2-3 sentences about money and material matters right now, grounded in the Jupiter / 2nd-11th house placements. Specific and confident, naming a concrete favourable window where relevant.[/FINANCE]'''}
{"" if focus_key != "general" else f'''[ACTION]One clear, specific, poetic action they should take today, directly tied to the {focus_label} focus. Make it beautiful and doable. No more than 2 sentences.[/ACTION]'''}
[REMEDY_NAME]The chosen remedy from the candidate list above, stated as a clear short instruction (you may lightly rephrase for flow, but keep the core action and timing intact)[/REMEDY_NAME]
[REMEDY_WHY]One sentence on why this remedy is suggested for them right now, connected to the planetary influence above — plain language, no jargon.[/REMEDY_WHY]
[REMEDY_HOW]One sentence describing exactly how and when to do it — simple, doable, low-cost, no special ingredients beyond common household items.[/REMEDY_HOW]
{"" if focus_key != "general" else '''[DOSHA_NOTE]One short sentence for EACH active dosha listed above, calmly explaining its real-life effect (or a brief reassuring note if none are active). Plain language, factual tone — never fear-based.[/DOSHA_NOTE]'''}

Tone rules:
- Never say "the stars say" or "the planets indicate" — just speak directly
- No jargon like "8th house" or "natal chart" — speak in plain human language (e.g. say "the area of your life connected to partnerships" instead of "7th house")
- Sound like a wise elder who genuinely cares — direct, real, sometimes challenging, never a fortune cookie
- Weave in the {data.get('dashaLord')} Mahadasha and {antardasha} Antardasha energy naturally
- The Lal Kitab remedy must be genuinely traditional, simple, safe, and inexpensive (water, grains, charity, colors, directions, timing) — never anything involving animal sacrifice, dangerous substances, or large expense

Output ONLY the tagged sections above, nothing else — no preamble, no closing remarks."""

        raw_text = call_ai(prompt, temperature=0.7, max_tokens=3200)

        def extract(tag, text):
            m = re.search(rf'\[{tag}\](.*?)\[/{tag}\]', text, re.DOTALL)
            return m.group(1).strip() if m else ''

        reading = {
            "planetary_influences": [],
            "today": extract("TODAY", raw_text),
            "love": extract("LOVE", raw_text),
            "career": extract("CAREER", raw_text),
            "health": extract("HEALTH", raw_text),
            "finance": extract("FINANCE", raw_text),
            "action": extract("ACTION", raw_text),
            "remedy": {
                "name": extract("REMEDY_NAME", raw_text),
                "why": extract("REMEDY_WHY", raw_text),
                "how": extract("REMEDY_HOW", raw_text)
            },
            "dosha_note": extract("DOSHA_NOTE", raw_text)
        }

        for i in range(1, 4):
            planet = extract(f"INFLUENCE{i}_PLANET", raw_text)
            headline = extract(f"INFLUENCE{i}_HEADLINE", raw_text)
            effect = extract(f"INFLUENCE{i}_EFFECT", raw_text)
            if planet:
                reading["planetary_influences"].append({
                    "planet": planet, "headline": headline, "effect": effect
                })

        # Sanity check — if core fields are empty, parsing failed entirely
        if not reading["today"]:
            return jsonify({"error": f"Could not parse AI response. Raw output: {raw_text[:300]}"}), 500

        log_request("reading", data=data, email=get_authenticated_email(),
                    output=json.dumps(reading, ensure_ascii=False))
        return jsonify(reading)

    except RateLimitError as e:
        return jsonify({"error": str(e), "rate_limited": True}), 429
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        if e.code == 429:
            return jsonify({"error": "Vayuman is experiencing very high demand right now. Please try again in a few minutes.", "rate_limited": True}), 429
        return jsonify({"error": f"Groq API error ({e.code}): {error_body}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/ask', methods=['POST'])
def ask_vyom():
    try:
        data = request.get_json()
        if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GROQ_API_KEY"):
            return jsonify(error="Server not configured — missing AI provider key"), 500

        question = (data.get("question") or "").strip()
        if not question:
            return jsonify(error="No question provided"), 400

        firstname = (data.get("name") or "Seeker").split()[0]
        firstname = firstname[0].upper() + firstname[1:] if firstname else "Seeker"

        history = data.get('history') or []
        history_block = ""
        if isinstance(history, list) and history:
            turns = []
            for turn in history[-6:]:
                if not isinstance(turn, dict):
                    continue
                h_q = str(turn.get('question', ''))[:300].strip()
                h_a = str(turn.get('answer', ''))[:600].strip()
                if h_q and h_a:
                    turns.append(f"Q: {h_q}\nA: {h_a}")
            if turns:
                history_block = (
                    "EARLIER IN THIS CONVERSATION (for context only — do not re-answer these, "
                    "just use them to understand what the person is referring to if their new "
                    "question builds on one, and to avoid repeating the same dasha/timing window "
                    "as a crutch if it's already been covered):\n" + "\n\n".join(turns) + "\n"
                )

        BANNED_FILLER = ["great potential", "amazing things", "the universe has a plan",
                          "your journey", "trust the process", "everything happens for a reason",
                          "you are destined", "special and unique", "align with the universe",
                          "positive energy", "the stars have blessed you", "embrace the journey"]
        banned_filler_text = "; ".join(f'"{p}"' for p in BANNED_FILLER)

        # Stage A — deterministic sufficiency gate. This app never collects a
        # second person's birth chart, so any compatibility-style question
        # about someone else is, by definition, missing their data.
        gate = check_sufficiency(question, has_named_target=False)

        sufficiency_instruction = ""
        if gate["insufficient"]:
            sufficiency_instruction = (
                "\nDATA SUFFICIENCY — IMPORTANT: this question asks you to judge a connection "
                "or compatibility with another person, but you have NO chart data for that person "
                "at all (no birth chart was ever provided for them). You may NOT say the connection "
                "'resonates', is 'compatible', 'neutral', or give any verdict about the OTHER person "
                "or the pairing. Instead: clearly state that you'd need their birth details "
                "(date, time, place) to judge the connection itself, THEN still give real, useful "
                "insight from the asker's OWN chart alone (e.g. what their placements suggest they "
                "need or tend toward in relationships/partnerships). Never use the words 'not "
                "calculated', 'not provided', 'we'd need', or 'let's assume' — just plainly ask for "
                "the missing birth details in one natural sentence.\n"
            )

        health_instruction = ""
        if gate["touches_health"]:
            health_instruction = (
                "\nHEALTH QUESTION DETECTED: do not diagnose, predict, or name any illness. "
                "You may speak generally about energy/vitality tendencies from the chart, but "
                "explicitly note that for anything medical, a qualified professional should be "
                "consulted.\n"
            )

        timing_instruction = ""
        if gate["asks_timing"]:
            timing_instruction = (
                "\nTIMING QUESTION DETECTED: give a favourable WINDOW (a season or year range) "
                "tied to dasha/antardasha timing — never a single guaranteed date, and never state "
                "an outcome as certain.\n"
            )

        prompt = f"""You are Vayuman — an elite, emotionally intelligent Vedic astrology guide.
Your voice is calm, warm, direct, and human. You never use jargon.

{firstname} has come to you with a real question. Answer it using ONLY their actual Vedic chart below.

Their Vedic chart:
- Lagna (Ascendant): {data.get('lagna')}
- Moon Sign (Rashi): {data.get('rashi')}
- Nakshatra: {data.get('nakshatra')}
- Current Mahadasha lord: {data.get('dashaLord')}
- Current Antardasha lord: {data.get('antardasha')}
- Planetary placements: {data.get('planets_summary')}
{sufficiency_instruction}{health_instruction}{timing_instruction}
{history_block}
Their question: {question}

INSTRUCTIONS:
0. USE THE EARLIER CONVERSATION ABOVE (if present) to understand references like "him", "that", "the same thing", or a topic mentioned in a prior answer. Resolve the reference silently and answer the new question directly — do not ask the person to repeat information they already gave.
1. OPEN BY ECHOING THEIR QUESTION: state your answer using language that picks up the actual words of what they asked — if they asked "will this relationship work", open addressing "this relationship" in your own words, not a generic opener like "Based on your chart...". State the verdict, yes/no, or timing plainly in this first sentence (unless the sufficiency note above says you can't give a verdict — then state what's missing plainly instead). No preamble before it.
2. COMMIT TO A STANCE: give ONE clear answer, not a menu of possibilities. Do not hedge with multiple "maybe" or "it could go either way" qualifiers stacked in the same answer — pick the most chart-grounded read and state it with confidence, then note the one real caveat if there is one.
3. NEVER GO IN CIRCLES: do not restate the question back rhetorically ("You're asking whether..."), do not repeat the same point in different words to pad length, and do not end by summarizing what you already just said. Every sentence must add new information.
4. ACCURACY: Every claim MUST trace to a specific placement in their chart. If it's generic enough to apply to anyone, delete it.
5. TIMING: Give ONE clear window tied to their Mahadasha ({data.get('dashaLord')}) and Antardasha ({data.get('antardasha')}) — but if a timing window tied to this same dasha/antardasha was already given in an earlier answer above, don't repeat it verbatim; either add new specificity or skip timing this time.
6. HONESTY: If there is friction, name it clearly, then give the path forward.
7. LENGTH: 3-5 sentences for simple questions. Up to 8 for complex ones. NEVER PAD.
8. NO FLUFF: never use these phrases or close paraphrases of them: {banned_filler_text}. Ground everything in the chart instead.
9. NEVER SAY: "you will definitely marry this person", "this person is your soulmate", "your partner is cheating", "you will become rich", "you should leave your job", "you will get pregnant", "you are cursed", "your chart guarantees X", "you will die", "you will get sick".
"""
        answer = call_ai(prompt, temperature=0.65, max_tokens=900)
        answer = answer.strip()

        # Stage C — deterministic post-check. If the gate found insufficient
        # data but the model invented a verdict anyway, fall back to a safe,
        # honest template instead of showing the bad answer.
        if violates_sufficiency_contract(answer, gate):
            print(f"[ask_vyom] sufficiency contract violated, using fallback for question: {question[:80]}")
            answer = (
                f"{firstname}, I'd need their birth details — date, time, and place — to judge "
                f"that connection properly, since I only have your chart to work from right now. "
                f"From your side, your {data.get('rashi', 'Moon sign')} and current "
                f"{data.get('dashaLord', 'Mahadasha')} period shape a lot of how you show up in "
                f"relationships generally. Share their birth details and I can give you a real "
                f"reading on the pairing itself."
            )

        log_request("ask", data=data, email=get_authenticated_email(), question=question, output=answer)
        return jsonify(answer=answer)

    except RateLimitError as e:
        return jsonify(error=str(e), rate_limited=True), 429
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/numerology', methods=['POST'])
def get_numerology():
    """Numerology reading. Needs only full name + DOB (no time/place).
    Computes the Pythagorean profile, then has the AI write a warm
    interpretation in Vayuman's voice."""
    try:
        data = request.get_json() or {}
        full_name = (data.get('name') or '').strip()
        dob = (data.get('dob') or '').strip()
        if not full_name:
            return jsonify({"error": "Please enter your full name for a numerology reading."}), 400
        if not dob:
            return jsonify({"error": "Please enter your date of birth."}), 400

        # Compute the numerology profile
        try:
            profile = numerology_engine.full_numerology_profile(full_name, dob)
        except Exception as e:
            return jsonify({"error": f"Could not read those details: {e}"}), 400

        if not (os.environ.get('GEMINI_API_KEY') or os.environ.get('GROQ_API_KEY')):
            return jsonify({"error": "Server not configured: missing AI provider key"}), 500

        first_name = full_name.split()[0]
        first_name = first_name[:1].upper() + first_name[1:] if first_name else "Seeker"

        lp = profile['life_path']; expr = profile['expression']; soul = profile['soul_urge']
        pers = profile['personality']; bday = profile['birthday']; mat = profile['maturity']
        py = profile['personal_year']; lucky = profile['lucky']
        nres = profile.get('name_resonance', {})

        BANNED_FILLER = ["great potential", "amazing things", "the universe has a plan",
                          "your journey", "trust the process", "everything happens for a reason",
                          "you are destined", "special and unique", "align with the universe",
                          "positive energy", "manifest your dreams", "the stars have blessed you"]
        banned_filler_text = "; ".join(f'"{p}"' for p in BANNED_FILLER)

        def _contains_any(text, terms):
            t = (text or "").lower()
            return any(term in t for term in terms)

        # ── Birth Grid (Psychomatrix / Arrows) — computed deterministically ──
        grid = numerology_engine.birth_grid(dob)

        cell_lines = []
        for n in range(1, 10):
            count = grid['counts'][n]
            trait = grid['cell_traits'][n]
            cell_lines.append(
                f"- {trait} (number {n}): "
                + (f"appears {count} time{'s' if count != 1 else ''}" if count else "absent")
            )
        cells_text = "\n".join(cell_lines)

        arrows_present = grid['arrows']['present']
        arrows_missing = grid['arrows']['missing']
        arrows_text = ""
        if arrows_present:
            arrows_text += "Completed arrows:\n" + "\n".join(
                f"- {a['name']}: {a['description']}" for a in arrows_present) + "\n"
        if arrows_missing:
            arrows_text += "Missing arrows:\n" + "\n".join(
                f"- {a['name']}: {a['description']}" for a in arrows_missing)
        if not arrows_text:
            arrows_text = "No fully completed or fully missing lines in this grid."

        # ── ONE unified prompt — both number systems feed the same reading,
        # so the AI can draw real connections between them instead of two
        # disconnected write-ups. ────────────────────────────────────────────
        prompt = f"""You are Vayuman, a warm, wise numerology guide. Write ONE complete, unified personal numerology reading for {first_name}, speaking directly to them by their first name. Base it ONLY on the facts below (all computed precisely — do not recalculate or change any of it).

{first_name}'s core numbers (Pythagorean system):
- Life Path {lp['number']} ({lp['meaning']}) — their core purpose and life journey.
- Expression/Destiny {expr['number']} ({expr['meaning']}) — natural talents and what they project.
- Soul Urge {soul['number']} ({soul['meaning']}) — inner desires and motivation.
- Personality {pers['number']} ({pers['meaning']}) — how others perceive them.
- Birthday {bday['number']} ({bday['meaning']}) — a special gift they carry.
- Maturity {mat['number']} ({mat['meaning']}) — what they grow into later in life.
- Personal Year (this year) {py['number']} ({py['meaning']}) — the theme of their year ahead.

{first_name}'s birth grid (positions of digits from their date of birth) — a line of numbers that all appear in someone's birth date is called an "arrow", and it points to a natural strength; a line where none of the numbers appear points to something worth building deliberately:
{cells_text}

{arrows_text}

Write the reading in this shape (plain text, no markdown/headings/bullets, roughly 10-14 sentences across 4 short paragraphs — one opening, then one each for career, relationships, and health & money combined):

OPENING PARAGRAPH — Address {first_name} by name and give ONE genuinely interesting, specific insight about who they are as a whole person — ideally a real connection between their core numbers and their birth grid (e.g. a completed arrow reinforcing their Life Path). State the number or arrow that grounds this insight ONCE, clearly, then spend the rest of the paragraph actually describing what it means for how they move through the world — their temperament, their instincts, what makes them distinct. Do not restate the number again in this paragraph once it's been named.

CAREER PARAGRAPH — Real, specific guidance about work and ambition. Pick whichever number(s) or grid cells/arrows are genuinely most relevant to career (commonly Expression, Personality, an arrow touching will/logic/duty, or a quiet cell in health/work-ethic). Name each one ONCE by number, then devote the remaining sentences to rich, concrete description of how this actually plays out at work — the kind of environment they thrive in, how they're perceived by colleagues, what tends to trip them up, what this year's Personal Year {py['number']} means for career timing specifically.

RELATIONSHIPS PARAGRAPH — Real, specific guidance about love, family, and connection. Pick whichever number(s) or grid cells are genuinely relevant (commonly Soul Urge, Personality, an arrow touching energy/emotional balance). Name each ONCE, then describe the actual relational pattern this produces — how they love, what they need from a partner, where friction tends to show up — in human, specific language.

HEALTH & MONEY PARAGRAPH — Real guidance covering both physical wellbeing and financial matters, drawing from whichever numbers or grid cells are relevant to each (commonly Life Path or Maturity for health tendencies, Expression or a quiet/strong cell for money habits). Name each number ONCE, then give grounded, practical description of the actual pattern — not just "focus on your health" but what specifically this combination suggests about how they handle stress, energy, and money.

CRITICAL — CITE EACH NUMBER ONLY ONCE: once you've named a number or arrow (e.g. "Life Path 11", "the arrow of determination"), do not repeat that same number again anywhere else in the reading. Refer back to it descriptively instead ("that same driven streak", "this pattern") rather than restating the digit. A reading dense with repeated digits reads like a printout, not a consultation — the numbers earn their place once, then the WRITING carries the insight.

DO NOT give the birth grid its own separate paragraph or call it out as a distinct topic ("turning to your grid...", "your birth grid also shows..."). Fold grid facts invisibly into whichever paragraph they're actually relevant to, exactly the way you fold in the core numbers — the reader should never feel like two systems are being explained side by side.

NEVER use these phrases or close paraphrases of them: {banned_filler_text}.

STRICT SCOPE: do NOT discuss name resonance, the person's name number, or their name's spelling anywhere in this reading — that has its own dedicated section elsewhere on the page and covering it here would duplicate it. Do NOT mention astrology, planets, or charts — this is a pure numerology reading. Warm, humane, specific, and cohesive — it should read as ONE reading by one voice, not a list of facts."""

        interpretation = call_ai(prompt, temperature=0.8, max_tokens=1400)
        interpretation = (interpretation or "").strip()

        # Safety net: if the AI returns an empty response, fall back to a
        # deterministic reading built from both the numbers and the grid so
        # the user never sees a blank reading.
        if not interpretation:
            strongest = sorted(grid['counts'].items(), key=lambda kv: kv[1], reverse=True)
            top_cell = next(((n, c) for n, c in strongest if c > 0), None)
            arrow_line = (
                f" Your grid also completes the {arrows_present[0]['name']}, {arrows_present[0]['description'].lower()}"
                if arrows_present else ""
            )
            top_cell_line = (
                f" Your birth grid reinforces this with {grid['cell_traits'][top_cell[0]]}, "
                f"appearing {'twice' if top_cell[1] > 1 else 'once'}.{arrow_line}"
                if top_cell else ""
            )
            interpretation = (
                f"{first_name}, your numbers tell a clear story. Your Life Path "
                f"{lp['number']} speaks of {lp['meaning'].rstrip('.').lower()} — the heart of your journey. "
                f"Your Expression {expr['number']} ({expr['meaning'].rstrip('.').lower()}) shows in how you meet the world, "
                f"while your Soul Urge {soul['number']} reveals an inner pull toward {soul['meaning'].rstrip('.').lower()}."
                f"{top_cell_line} "
                f"This year carries the energy of a Personal Year {py['number']}: {py['meaning'].rstrip('.').lower()}. "
                f"Lean into that theme — it's the current you're meant to move with right now."
            )

        log_request("numerology", data=data, email=get_authenticated_email(), output=interpretation)

        return jsonify({
            "interpretation": interpretation,
            "profile": profile,
            "birth_grid": {
                "counts": grid['counts'],
                "planes": grid['planes'],
                "arrows": grid['arrows'],
            },
        })

    except RateLimitError as e:
        return jsonify({"error": str(e), "rate_limited": True}), 429
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return jsonify({"error": "Vayuman is experiencing very high demand right now. Please try again in a few minutes.", "rate_limited": True}), 429
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── ANSWER PERMISSION GATE — main.py decides, the AI only explains ─────────
# Core principle: numerology.py calculates numbers. main.py decides whether
# a question CAN be answered, and what kind of answer is allowed. Gemini/Groq
# is never asked to judge data sufficiency — it only ever explains an answer
# type the backend has already permissioned.

class AnswerType:
    FULL_READING = "full_reading"
    PARTIAL_READING = "partial_reading"
    MISSING_DATA = "missing_data_response"
    SAFETY_RESPONSE = "safety_response"
    UNSUPPORTED = "unsupported_response"
    CLARIFICATION_REQUIRED = "clarification_required"


QUESTION_TYPES = [
    "numerology_self", "numerology_name_resonance", "numerology_compatibility",
    "brand_name_resonance", "business_name_resonance", "child_name_resonance",
    "career_general", "career_timing", "money_general", "money_timing",
    "relationship_general", "partner_compatibility", "marriage_timing",
    "health_sensitive", "pregnancy_sensitive", "death_sensitive",
    "remedy_request", "general_life_guidance", "unsupported_or_unclear",
]

# Deterministic keyword classification — no LLM call. Order matters: more
# specific/sensitive categories are checked first so they can't be shadowed
# by a broader keyword match later in the list.
_QUESTION_TYPE_PATTERNS = [
    ("death_sensitive", re.compile(r'(?i)\b(when will i die|how (?:will|do) i die|my death|lifespan)\b')),
    ("pregnancy_sensitive", re.compile(r'(?i)\b(pregnan|conceive|having a baby|fertility)\b')),
    ("health_sensitive", re.compile(r'(?i)\b(illness|disease|health|sick|diagnos|surgery|symptom)\b')),
    ("marriage_timing", re.compile(r'(?i)\b(when will i (?:get married|marry)|marriage.*when|when.*marriage)\b')),
    ("partner_compatibility", re.compile(r'(?i)\b(wife|husband|spouse|partner|girlfriend|boyfriend|fianc[ée]e?)\b.*\b(resonate|compatib|match|suit|right for me|connection)\b')),
    ("child_name_resonance", re.compile(r'(?i)\b(?:(?:child|baby|son|daughter)\b.*\bname\b|name\b.*\b(?:child|baby|son|daughter))\b')),
    ("business_name_resonance", re.compile(r'(?i)\b(business name|company name)\b')),
    ("brand_name_resonance", re.compile(r'(?i)\bbrand\b')),
    ("numerology_compatibility", re.compile(r'(?i)\b(resonate|compatib|match(?:es)?)\b')),
    ("career_timing", re.compile(r'(?i)\bcareer\b.*\b(when|timing|this year|next year)\b')),
    ("career_general", re.compile(r'(?i)\b(career|job|profession|promotion)\b')),
    ("money_timing", re.compile(r'(?i)\b(money|rich|wealth|financ)\b.*\b(when|timing|this year|next year)\b')),
    ("money_general", re.compile(r'(?i)\b(money|rich|wealth|financ|invest|business)\b')),
    ("remedy_request", re.compile(r'(?i)\b(remedy|remedies|what should i do to fix|how (?:can|do) i improve)\b')),
    ("relationship_general", re.compile(r'(?i)\b(relationship|love life|dating)\b')),
    ("numerology_name_resonance", re.compile(r'(?i)\bname\b.*\b(resonate|suit|match)\b')),
]


def classify_numerology_question(question):
    for qtype, pattern in _QUESTION_TYPE_PATTERNS:
        if pattern.search(question):
            return qtype
    return "general_life_guidance"


_QUESTION_STOPWORDS = {
    "does", "is", "are", "was", "were", "will", "would", "should", "can",
    "could", "do", "did", "what", "when", "why", "how", "who", "which",
    "the", "this", "that", "these", "those", "my", "your", "his", "her",
    "their", "our", "and", "but", "or", "if", "so",
}


def _extract_target_name(question, fullname):
    """Reuses the existing candidate-name regex to find a real name typed
    into the question itself (e.g. 'my wife Simran')."""
    # NOTE: (?i) scoped to only the keyword alternation — applying it to the
    # whole pattern would make [A-Z] match lowercase too (Python regex
    # character classes are affected by inline case-insensitive flags),
    # which silently broke this: "business name good" would otherwise
    # capture "name good" as if it were a proper noun.
    candidates = re.findall(
        r'(?i:name|named|called|page|brand|business|handle|title|wife|husband|partner|'
        r'son|daughter|friend)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})',
        question
    )
    for c in candidates:
        c = c.strip()
        if c.lower() != fullname.lower() and numerology_engine.has_usable_name(c):
            return c
    # Also catch a bare capitalised name/phrase anywhere in the question
    # (e.g. "Is Divine Compass a good brand name for me?"). Sentence-initial
    # capitalization ("Does", "Is", "What") is grammar, not a name signal —
    # strip any leading stopword(s) from a candidate rather than discarding
    # the whole match, so "Does Simran Kaur" still yields "Simran Kaur".
    bare = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b', question)
    for c in bare:
        words = c.split()
        while words and words[0].lower() in _QUESTION_STOPWORDS:
            words.pop(0)
        cleaned = " ".join(words)
        if not cleaned:
            continue
        if cleaned.lower() != fullname.lower() and numerology_engine.has_usable_name(cleaned):
            return cleaned
    return None


def _target_relation_label(question, question_type):
    """Best-effort human label for the pending_context — 'wife', 'brand', etc."""
    m = SECOND_PERSON_PATTERN.search(question) if 'SECOND_PERSON_PATTERN' in globals() else None
    if m:
        word = m.group(1).lower()
        if word not in ("him", "her", "them", "someone", "person"):
            return word
    if question_type in ("brand_name_resonance",):
        return "brand"
    if question_type in ("business_name_resonance",):
        return "business"
    if question_type in ("child_name_resonance",):
        return "child"
    return "target"


def build_answer_permission_gate(question, data, profile):
    """
    THE gate. Runs entirely in Python before any AI call. Decides:
    - what kind of question this is
    - whether it CAN be answered, partially or fully
    - what's missing
    - what claims are forbidden in the eventual answer
    """
    fullname = data.get('name', '')
    question_type = classify_numerology_question(question)

    target_name = _extract_target_name(question, fullname)
    target_profile = None
    if target_name:
        target_profile = numerology_engine.partial_profile_from_available_data(name=target_name)

    forbidden_claims = [
        "positive/negative/neutral compatibility verdict without both people's data",
        '"resonates" without both sides calculated', '"strong match"', '"weak match"',
        '"the energy feels"',
    ]

    # ── Sensitive/safety categories — always a safety response, never AI-judged
    if question_type in ("health_sensitive", "pregnancy_sensitive", "death_sensitive"):
        return {
            "question_type": question_type,
            "answer_type": AnswerType.SAFETY_RESPONSE,
            "can_answer_fully": False,
            "missing_data": [],
            "forbidden_claims": ["diagnosis", "illness prediction", "pregnancy certainty", "death prediction"],
            "target_name": target_name,
            "target_profile": target_profile,
        }

    # ── Two-person comparison categories — need target data
    if question_type in ("partner_compatibility", "numerology_compatibility",
                          "child_name_resonance", "numerology_name_resonance"):
        if not target_profile or not target_profile["numbers"]:
            return {
                "question_type": question_type,
                "answer_type": AnswerType.MISSING_DATA,
                "can_answer_fully": False,
                "missing_data": ["target_name_or_dob"],
                "forbidden_claims": forbidden_claims,
                "target_name": target_name,
                "target_profile": target_profile,
                "pending_context": {
                    "status": "awaiting_target_data",
                    "original_question": question,
                    "target_relation": _target_relation_label(question, question_type),
                    "needed_fields": ["target_name_or_dob"],
                    "resume_action": "compare_target_with_user",
                    "question_type": question_type,
                },
            }
        comparison = numerology_engine.compare_numerology_profiles(profile, target_profile)
        answer_type = AnswerType.FULL_READING if not target_profile["missing_fields"] else AnswerType.PARTIAL_READING
        return {
            "question_type": question_type,
            "answer_type": answer_type,
            "can_answer_fully": not target_profile["missing_fields"],
            "missing_data": target_profile["missing_fields"],
            "forbidden_claims": forbidden_claims if target_profile["missing_fields"] else [],
            "target_name": target_name,
            "target_profile": target_profile,
            "comparison": comparison,
        }

    # ── Brand/business name resonance — needs a target name
    if question_type in ("brand_name_resonance", "business_name_resonance"):
        if not target_name:
            return {
                "question_type": question_type,
                "answer_type": AnswerType.MISSING_DATA,
                "can_answer_fully": False,
                "missing_data": ["target_name"],
                "forbidden_claims": forbidden_claims,
                "target_name": None,
                "target_profile": None,
                "pending_context": {
                    "status": "awaiting_target_data",
                    "original_question": question,
                    "target_relation": _target_relation_label(question, question_type),
                    "needed_fields": ["target_name"],
                    "resume_action": "compare_target_with_user",
                    "question_type": question_type,
                },
            }
        name_comparison = numerology_engine.compare_name_to_user_profile(
            target_name, profile, purpose=question_type.replace("_name_resonance", "")
        )
        return {
            "question_type": question_type,
            "answer_type": AnswerType.FULL_READING,
            "can_answer_fully": True,
            "missing_data": [],
            "forbidden_claims": [],
            "target_name": target_name,
            "target_profile": None,
            "name_comparison": name_comparison,
        }

    # ── Timing categories — allowed, but capped confidence, no exact dates
    if question_type in ("marriage_timing", "career_timing", "money_timing"):
        return {
            "question_type": question_type,
            "answer_type": AnswerType.FULL_READING,
            "can_answer_fully": True,
            "missing_data": [],
            "forbidden_claims": ["exact guaranteed date", "fixed certainty"],
            "target_name": None, "target_profile": None,
        }

    # ── Money/career/general — normally fully answerable from the user's own profile
    money_career_claims = []
    if question_type == "money_general":
        money_career_claims = ["guaranteed wealth", "specific investment instruction"]
    elif question_type == "career_general":
        money_career_claims = ["guaranteed job/promotion", "command to quit current job"]

    return {
        "question_type": question_type,
        "answer_type": AnswerType.FULL_READING,
        "can_answer_fully": True,
        "missing_data": [],
        "forbidden_claims": money_career_claims,
        "target_name": None, "target_profile": None,
    }


def _unified_response(answer, answer_type, question_type, used_ai, can_answer_fully,
                       missing_data=None, pending_context=None, resume_context_used=False):
    """Every Ask Vayuman (numerology) response goes through this shape,
    matching the API contract exactly — no endpoint returns a partial shape."""
    return {
        "answer": answer,
        "answer_type": answer_type,
        "question_type": question_type,
        "used_ai": used_ai,
        "can_answer_fully": can_answer_fully,
        "can_answer_partially": answer_type == AnswerType.PARTIAL_READING,
        "missing_data": missing_data or [],
        "pending_context": pending_context,
        "resume_context_used": resume_context_used,
    }


def build_missing_data_response(gate, profile, firstname):
    """
    Deterministic, Python-only response — NO AI call. Used whenever the gate
    decides required data is missing. Still gives real value from the user's
    OWN available numbers, phrased naturally, never inventing the missing side.
    """
    lp = profile["life_path"]
    expr = profile["expression"]

    if gate["question_type"] in ("brand_name_resonance", "business_name_resonance"):
        ask = "Share the exact name and I'll calculate it against your profile."
    else:
        ask = "Share their name (or date of birth) and I'll work out exactly how it lines up with your numbers."

    answer = (
        f"I can't judge that yet — I need more to go on. From your side, your Life Path "
        f"{lp['number']} ({lp['meaning'].rstrip('.').lower()}) and Expression {expr['number']} "
        f"({expr['meaning'].rstrip('.').lower()}) shape a lot of what you bring to this. {ask}"
    )
    return _unified_response(
        answer=answer,
        answer_type=gate["answer_type"],
        question_type=gate["question_type"],
        used_ai=False,
        can_answer_fully=False,
        missing_data=gate.get("missing_data", []),
        pending_context=gate.get("pending_context"),
    )


_SAFETY_TEMPLATES = {
    "health_sensitive": (
        "Numerology and astrology aren't able to diagnose or predict illness, so I won't guess "
        "at your health here. What your numbers CAN speak to is energy and stress tendencies in "
        "a general sense — but for anything about your actual health, please speak to a qualified "
        "medical professional."
    ),
    "pregnancy_sensitive": (
        "I can't responsibly predict or guarantee anything about pregnancy or fertility — that's "
        "outside what numerology can honestly speak to, and it's a conversation for you and a "
        "qualified medical professional, not a number."
    ),
    "death_sensitive": (
        "I don't give predictions about death or lifespan — that's not something numerology or "
        "astrology can honestly claim to know, and I won't pretend otherwise."
    ),
}


def build_safety_response(gate, firstname):
    """Deterministic, Python-only response for sensitive categories — NO AI call."""
    template = _SAFETY_TEMPLATES.get(gate["question_type"], _SAFETY_TEMPLATES["health_sensitive"])
    return _unified_response(
        answer=template,
        answer_type=AnswerType.SAFETY_RESPONSE,
        question_type=gate["question_type"],
        used_ai=False,
        can_answer_fully=False,
    )


def select_relevant_numerology_factors(gate, profile):
    """Pick only the numbers actually relevant to this question type, instead
    of dumping the entire profile into every prompt."""
    base = {
        "life_path": profile["life_path"]["number"],
        "expression": profile["expression"]["number"],
    }
    qt = gate["question_type"]
    if qt in ("relationship_general", "partner_compatibility", "marriage_timing"):
        base["soul_urge"] = profile["soul_urge"]["number"]
        base["personality"] = profile["personality"]["number"]
    if qt in ("career_general", "career_timing", "money_general", "money_timing"):
        base["personal_year"] = profile["personal_year"]["number"]
    if qt in ("marriage_timing", "career_timing", "money_timing"):
        base["personal_year"] = profile["personal_year"]["number"]
    return base


def build_numerology_prompt(question, profile, gate, selected_factors, firstname, history_block):
    """
    Structured prompt — "COMMIT TO A STANCE" only applies when can_answer_fully
    is true and the category isn't sensitive. Partial/missing cases never
    reach this function at all (the gate returns a deterministic response
    for those before any AI call).
    """
    factors_text = "\n".join(f"- {k}: {v}" for k, v in selected_factors.items())
    forbidden_text = "; ".join(gate["forbidden_claims"]) if gate["forbidden_claims"] else "none beyond the standard safety rules"

    extra_context = ""
    if gate.get("comparison") and gate["comparison"].get("can_compare"):
        comp = gate["comparison"]
        pairs_text = "\n".join(
            f"  - {p['area']}: user {p['user_number']} vs target {p['target_number']} → {p['verdict']}"
            for p in comp["pairs"]
        )
        extra_context = f"\nCALCULATED TWO-PERSON COMPARISON (use this, do not recalculate):\nOverall: {comp['overall_verdict']}\n{pairs_text}\n"
    if gate.get("name_comparison") and gate["name_comparison"].get("can_compare"):
        nc = gate["name_comparison"]
        extra_context = (
            f"\nCALCULATED NAME COMPARISON (use this, do not recalculate):\n"
            f"Target name: {nc['target_name']} → number {nc['target_name_number']}\n"
            f"Verdict vs your Life Path {nc['user_life_path']}: {nc['verdict']} — {nc['meaning']}\n"
        )

    commit_instruction = (
        "COMMIT TO A STANCE: give ONE clear answer, not a menu of possibilities. State it with confidence."
        if gate["can_answer_fully"] and gate["question_type"] not in ("health_sensitive", "pregnancy_sensitive", "death_sensitive")
        else "Do NOT commit to a firm verdict beyond what the calculated data above actually supports — stay honest about the limits of a PARTIAL reading."
    )

    return f"""You are Vayuman, a plain-English numerology guide.

Use ONLY the structured data below — never invent a number or claim data you don't have.

QUESTION:
{question}

QUESTION TYPE: {gate['question_type']}
ANSWER TYPE: {gate['answer_type']}
CAN ANSWER FULLY: {gate['can_answer_fully']}
MISSING DATA: {gate['missing_data'] or 'none'}

SELECTED FACTORS (only these — do not reference any other number):
{factors_text}
{extra_context}
{history_block}

FORBIDDEN CLAIMS — never say or imply any of: {forbidden_text}
NEVER SAY: "you will definitely marry this person", "your partner is cheating", "you will become rich", "you should leave your job", "you will get pregnant", "you are cursed", "your chart guarantees X", "you will die/get sick".

RULES:
- Do not invent numbers or mention data not present above.
- Do not give a verdict beyond what ANSWER TYPE allows.
- Do not use vague spiritual filler ("cosmic shift", "divine alignment", "trust the process", "your journey").
- Explain every numerology term simply, in the same sentence you use it.
- Open by echoing the actual words of the question, not a generic opener.
- Never restate the question rhetorically or repeat the same point twice to pad length.
- {commit_instruction}
- Keep it concise: 4-6 sentences.
- If Personal Year has already been mentioned earlier in this conversation, don't repeat it — use a different number.

Write the answer now — plain text, no preamble, no headers unless factors include a real name comparison worth showing step-by-step.
"""


def post_check_answer(answer, gate):
    """
    Deterministic post-check. If the AI still violated the gate's rules
    despite the prompt (e.g. gave a verdict on a partial reading, or used a
    banned phrase), replace with a safe fallback rather than show it.
    """
    text = (answer or "")
    lower = text.lower()

    if gate["answer_type"] == AnswerType.PARTIAL_READING:
        if re.search(r'(?i)\b(resonates?|compatible|strong match|weak match|the energy feels)\b', text):
            return False, "partial reading gave a full verdict it wasn't allowed to give"

    if re.search(r'(?i)(not calculated|not provided|we\'?d need|let\'?s assume)', text):
        return False, "used a banned 'missing data' phrase instead of the gate's own wording"

    banned_filler = ["great potential", "the universe has a plan", "trust the process",
                      "your journey", "cosmic shift", "divine alignment", "you are destined"]
    for phrase in banned_filler:
        if phrase in lower:
            return False, f"used banned filler phrase: {phrase}"

    return True, None


def resolve_pending_context(data):
    """
    If the request includes resume_context, this is a FOLLOW-UP to a
    previous question that was missing data — not a new question. Returns
    the resume info to act on, or None if this is a fresh question.
    """
    resume_context = data.get("resume_context")
    if not resume_context or not isinstance(resume_context, dict):
        return None
    resume_action = resume_context.get("resume_action")
    if not resume_action:
        return None
    original_question = data.get("question") or resume_context.get("original_question")
    if not original_question:
        return None
    return {
        "original_question": original_question,
        "resume_action": resume_action,
        "question_type": resume_context.get("question_type"),
    }


def answer_resumed_question(user_profile, target_profile, resumed, firstname, question):
    """
    Completes a previously-incomplete question now that target data has
    arrived, WITHOUT creating a standalone reading for the target. Reuses
    the same gate-shape/prompt/post-check pipeline as a fresh question, so
    the target's data is never confused with the main user's own reading.
    """
    question_type = resumed.get("question_type") or "numerology_compatibility"

    if not target_profile or not target_profile.get("numbers"):
        # Still nothing usable even after the "resume" attempt — fall back
        # to a fresh missing-data response rather than guessing.
        synthetic_gate = {
            "question_type": question_type,
            "answer_type": AnswerType.MISSING_DATA,
            "missing_data": ["target_name_or_dob"],
            "pending_context": {
                "status": "awaiting_target_data",
                "original_question": question,
                "target_relation": _target_relation_label(question, question_type),
                "needed_fields": ["target_name_or_dob"],
                "resume_action": "compare_target_with_user",
                "question_type": question_type,
            },
        }
        response = build_missing_data_response(synthetic_gate, user_profile, firstname)
        response["resume_context_used"] = True
        return response

    if question_type in ("brand_name_resonance", "business_name_resonance"):
        # Target is a name-only entity (brand/business), not a birth-data person
        target_name = target_profile.get("numbers", {}).get("expression", {}).get("number")
        name_comparison = None  # handled via comparison below using expression numbers directly
        comparison = numerology_engine.compare_numerology_profiles(user_profile, target_profile)
        gate = {
            "question_type": question_type,
            "answer_type": AnswerType.FULL_READING,
            "can_answer_fully": True,
            "missing_data": [],
            "forbidden_claims": [],
            "comparison": comparison,
        }
    else:
        comparison = numerology_engine.compare_numerology_profiles(user_profile, target_profile)
        answer_type = AnswerType.FULL_READING if not target_profile["missing_fields"] else AnswerType.PARTIAL_READING
        gate = {
            "question_type": question_type,
            "answer_type": answer_type,
            "can_answer_fully": not target_profile["missing_fields"],
            "missing_data": target_profile["missing_fields"],
            "forbidden_claims": [] if not target_profile["missing_fields"] else [
                "positive/negative/neutral compatibility verdict beyond what's actually calculated"
            ],
            "comparison": comparison,
        }

    selected_factors = select_relevant_numerology_factors(gate, user_profile)
    prompt = build_numerology_prompt(question, user_profile, gate, selected_factors, firstname, "")
    answer = call_ai(prompt, temperature=0.6 if gate["can_answer_fully"] else 0.4, max_tokens=1200)
    answer = answer.strip()

    ok, violation_reason = post_check_answer(answer, gate)
    if not ok:
        print(f"[answer_resumed_question] post-check failed ({violation_reason})")
        answer = (
            f"Comparing your numbers now that I have theirs: your Life Path "
            f"{user_profile['life_path']['number']} and their available numbers show a "
            f"{comparison.get('overall_verdict', 'mixed')} pattern overall — "
            f"{'a good foundation to build from' if comparison.get('overall_verdict') == 'supportive' else 'real differences worth understanding rather than a simple yes or no'}."
        )

    response = _unified_response(
        answer=answer,
        answer_type=gate["answer_type"],
        question_type=question_type,
        used_ai=True,
        can_answer_fully=gate["can_answer_fully"],
        missing_data=gate["missing_data"],
        pending_context=None,
        resume_context_used=True,
    )
    return response


@app.route('/numerology-ask', methods=['POST'])
def numerology_ask():
    try:
        data = request.get_json() or {}

        # ── Accept BOTH the new {user:{}, target:{}, resume_context:{}} shape
        # AND the old flat {name, dob} shape, so existing frontends don't break.
        user_obj = data.get('user') or {}
        fullname = (user_obj.get('name') or data.get('name') or "").strip()
        dob = (user_obj.get('dob') or data.get('dob') or "").strip()
        question = (data.get('question') or "").strip()
        history = data.get('history') or []

        if not question or not fullname or not dob:
            return jsonify(error="Missing question, name or dob"), 400

        profile = numerology_engine.full_numerology_profile(fullname, dob)
        firstname = fullname.split()[0].capitalize() if fullname else "Seeker"
        email = get_authenticated_email()

        # ── RESUME CHECK — this is the actual fix. If resume_context is
        # present, this is target data for a PREVIOUS question, not a new
        # question about the target. Never fall through to a fresh reading.
        resumed = resolve_pending_context(data)
        if resumed and resumed["resume_action"] == "compare_target_with_user":
            target = data.get('target') or {}
            target_profile = numerology_engine.build_target_profile(target)
            response = answer_resumed_question(profile, target_profile, resumed, firstname, resumed["original_question"])
            log_request("numerology_ask", data=data, email=email,
                        question=resumed["original_question"], output=response["answer"])
            return jsonify(response)

        # Build prior conversation context so follow-up questions can refer
        # back to earlier answers without the person repeating themselves.
        history_block = ""
        if isinstance(history, list) and history:
            turns = []
            for turn in history[-6:]:
                if not isinstance(turn, dict):
                    continue
                h_q = str(turn.get('question', ''))[:300].strip()
                h_a = str(turn.get('answer', ''))[:600].strip()
                if h_q and h_a:
                    turns.append(f"Q: {h_q}\nA: {h_a}")
            if turns:
                history_block = (
                    "EARLIER IN THIS CONVERSATION (for context only — do not re-answer these, "
                    "just use them to understand what the person is referring to if their new "
                    "question builds on one):\n" + "\n\n".join(turns) + "\n"
                )

        # ── THE GATE — decides everything before any AI call ────────────────
        gate = build_answer_permission_gate(question, {**data, 'name': fullname}, profile)

        if gate["answer_type"] == AnswerType.MISSING_DATA:
            response = build_missing_data_response(gate, profile, firstname)
            if email and response.get("pending_context"):
                save_pending_context(email, response["pending_context"])
            log_request("numerology_ask", data=data, email=email,
                        question=question, output=response["answer"])
            return jsonify(response)

        if gate["answer_type"] == AnswerType.SAFETY_RESPONSE:
            response = build_safety_response(gate, firstname)
            log_request("numerology_ask", data=data, email=email,
                        question=question, output=response["answer"])
            return jsonify(response)

        # ── Only FULL_READING / PARTIAL_READING reach the AI ─────────────────
        selected_factors = select_relevant_numerology_factors(gate, profile)
        prompt = build_numerology_prompt(question, profile, gate, selected_factors, firstname, history_block)
        answer = call_ai(prompt, temperature=0.6 if gate["can_answer_fully"] else 0.4, max_tokens=1200)
        answer = answer.strip()

        ok, violation_reason = post_check_answer(answer, gate)
        if not ok:
            print(f"[numerology_ask] post-check failed ({violation_reason}) for question: {question[:80]}")
            if gate["answer_type"] == AnswerType.PARTIAL_READING:
                fallback = build_missing_data_response(gate, profile, firstname)
                answer = fallback["answer"]
            else:
                answer = (
                    f"Your Life Path {profile['life_path']['number']} and Expression "
                    f"{profile['expression']['number']} are the clearest signal here — "
                    f"{profile['life_path']['meaning'].rstrip('.').lower()} Try asking again "
                    f"with a bit more detail and I'll go deeper."
                )

        response = _unified_response(
            answer=answer,
            answer_type=gate["answer_type"],
            question_type=gate["question_type"],
            used_ai=True,
            can_answer_fully=gate["can_answer_fully"],
            missing_data=gate.get("missing_data", []),
            pending_context=None,
            resume_context_used=False,
        )
        log_request("numerology_ask", data=data, email=email,
                    question=question, output=answer)
        return jsonify(response)

    except RateLimitError as e:
        return jsonify(error=str(e), rate_limited=True), 429
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "Vayuman engine is running", "engine": "Swiss Ephemeris + Lahiri Ayanamsa"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
