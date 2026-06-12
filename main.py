"""
Vyom AI — Vedic Astrology Calculation Engine
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
import urllib.request
import urllib.parse
import urllib.error

app = Flask(__name__)
CORS(app)  # Allow requests from your website

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
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (VyomAI/1.0)"})
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
    return int(longitude / 30)

def longitude_to_degree_in_rashi(longitude):
    """Get degrees within a Rashi"""
    return longitude % 30

def get_nakshatra(moon_longitude):
    """Get Nakshatra from Moon's sidereal longitude"""
    nak_index = int(moon_longitude / (360 / 27))
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
    today = datetime.now()
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

# ── MAIN API ENDPOINT ──────────────────────────────────────────────────────

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

        # Convert to UTC (assume IST = UTC+5:30 for India)
        # For production, use pytz with proper timezone detection
        from dateutil import tz
        india_tz = tz.gettz('Asia/Kolkata')
        dt_aware = dt_local.replace(tzinfo=india_tz)
        dt_utc = dt_aware.astimezone(tz.UTC)

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
            "planets": planets,
            "meta": {
                "latitude": round(lat, 4),
                "longitude_geo": round(lon, 4),
                "julian_day": round(jd, 6),
                "ayanamsa": "Lahiri",
                "house_system": "Whole Sign"
            }
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def call_groq(prompt, api_key, temperature=0.9, max_tokens=1400):
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
            "User-Agent": "Mozilla/5.0 (VyomAI/1.0)"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=45) as resp:
        result = json.loads(resp.read().decode('utf-8'))

    return result["choices"][0]["message"]["content"]


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
        api_key = os.environ.get('GROQ_API_KEY')

        if not api_key:
            return jsonify({"error": "Server not configured: missing GROQ_API_KEY"}), 500

        focus_labels = {
            'general': 'overall life',
            'career': 'career and purpose',
            'relationships': 'love and relationships',
            'health': 'health and wellbeing',
            'finances': 'finances and abundance'
        }
        focus_label = focus_labels.get(data.get('focus', 'general'), 'overall life')
        focus_key = data.get('focus', 'general')

        planets_summary = data.get('planets_summary', '')
        antardasha = data.get('antardasha', '')

        prompt = f"""You are Vyom AI — a deeply wise, emotionally intelligent Vedic astrology guide. Your voice is calm, warm, and human. You never use jargon. You speak like a trusted friend who happens to understand the cosmos deeply.

Generate a personalised, REAL-TIME Vedic astrology reading for {data.get('name', 'Seeker')} for {data.get('today')}.

Their Vedic chart details:
- Lagna (Ascendant): {data.get('lagna')}
- Moon Sign (Rashi): {data.get('rashi')}
- Nakshatra: {data.get('nakshatra')} (Pada {data.get('pada')})
- Current Mahadasha: {data.get('dashaLord')}
- Current Antardasha: {antardasha}
- Planetary placements (house positions relative to their Lagna): {planets_summary}
- PRIMARY FOCUS REQUESTED: {focus_label}

CRITICAL INSTRUCTIONS:
1. The "today" field MUST be primarily about {focus_label} — this is what {data.get('name', 'Seeker')} specifically asked about. Reference the relevant planet's house placement from the data above to ground this in their actual chart (in plain language, no jargon).
2. Do NOT default to generic "overall life" advice — every reading must feel distinctly different depending on the focus area and the actual planetary placements given.
3. Avoid soft, vague, feel-good filler ("things will work out", "stay positive"). Be SPECIFIC and grounded — name a likely situation, a real tension, or a concrete opportunity based on the chart data. It's okay to mention a challenge or friction, not just positives.
4. Vary sentence rhythm and word choice — do not reuse the same openings or phrases across different focus areas.
5. For "planetary_influences": pick the 3 most significant planets right now (always include the Mahadasha lord and Antardasha lord, plus one more relevant to the {focus_label} focus). For each, describe in ONE plain-language sentence what that planet is "doing" in real-life terms — e.g. "Saturn is currently shaping how much responsibility you're carrying at work, and may be making a project feel slower than you'd like." No jargon, no house numbers — describe the real-life area and the felt effect.

Write the reading in this EXACT JSON format (respond with JSON only, no markdown, no backticks):
{{
  "planetary_influences": [
    {{"planet": "PlanetName", "headline": "3-5 word real-life headline (e.g. 'Career momentum building')", "effect": "One plain-language sentence on what this planet is doing in their life right now."}},
    {{"planet": "PlanetName", "headline": "...", "effect": "..."}},
    {{"planet": "PlanetName", "headline": "...", "effect": "..."}}
  ],
  "today": "4-5 sentences, primarily about {focus_label}, grounded in their actual planetary placements. Specific, real, and direct — not generic.",
  "love": "2-3 sentences about relationships this week. Specific and actionable.",
  "career": "2-3 sentences about work and purpose this week.",
  "health": "2-3 sentences about energy and physical wellbeing.",
  "finance": "2-3 sentences about money and material matters.",
  "action": "One clear, specific, poetic action they should take today, directly tied to the {focus_label} focus. Make it beautiful and doable. No more than 2 sentences."
}}

Tone rules:
- Never say "the stars say" or "the planets indicate" — just speak directly
- No jargon like "8th house" or "natal chart" — speak in plain human language (e.g. say "the area of your life connected to partnerships" instead of "7th house")
- Sound like a wise elder who genuinely cares — direct, real, sometimes challenging, never a fortune cookie
- Weave in the {data.get('dashaLord')} Mahadasha and {antardasha} Antardasha energy naturally

Respond with ONLY the JSON object, nothing else."""

        raw_text = call_groq(prompt, api_key)
        clean = raw_text.replace("```json", "").replace("```", "").strip()
        reading = json.loads(clean)

        return jsonify(reading)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        return jsonify({"error": f"Groq API error ({e.code}): {error_body}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/ask', methods=['POST'])
def ask_vyom():
    """
    POST /ask
    Body: { "name": "...", "lagna": "...", "rashi": "...", "nakshatra": "...",
            "pada": 1, "dashaLord": "...", "antardasha": "...",
            "planets_summary": "...", "today": "...", "question": "..." }
    Returns: { "answer": "..." }
    Free-form Q&A grounded in the user's real chart — finance, love, career, health, anything.
    """
    try:
        data = request.get_json()
        api_key = os.environ.get('GROQ_API_KEY')

        if not api_key:
            return jsonify({"error": "Server not configured: missing GROQ_API_KEY"}), 500

        question = (data.get('question') or '').strip()
        if not question:
            return jsonify({"error": "No question provided"}), 400

        prompt = f"""You are Vyom AI — a deeply wise, emotionally intelligent Vedic astrology guide. Your voice is calm, warm, direct, and human. You never use jargon. You speak like a trusted friend who happens to understand the cosmos deeply.

{data.get('name', 'Seeker')} has come to you with a real question about their life. Use their actual Vedic chart to answer it honestly and specifically — this is a real-time consultation, not a generic horoscope.

Their Vedic chart details:
- Lagna (Ascendant): {data.get('lagna')}
- Moon Sign (Rashi): {data.get('rashi')}
- Nakshatra: {data.get('nakshatra')} (Pada {data.get('pada')})
- Current Mahadasha: {data.get('dashaLord')}
- Current Antardasha: {data.get('antardasha')}
- Planetary placements (house positions relative to their Lagna): {data.get('planets_summary')}
- Today's date: {data.get('today')}

Their question:
"{question}"

INSTRUCTIONS:
1. Answer their actual question directly — don't deflect into generic advice. If they ask about a specific situation (e.g. "should I take this job", "will my relationship work out", "is this a good time to invest"), engage with that specific situation using their chart data.
2. Ground your answer in their actual planetary placements — reference the relevant life area (career, relationships, finances, etc.) and which planet is influencing it, in plain language (no "8th house" type jargon).
3. Be honest and specific — including about likely challenges or timing concerns, not just reassurance. A wise guide tells the truth kindly, not just what someone wants to hear.
4. Length: 4-7 sentences. Warm but substantive — this should feel like real guidance, not a fortune cookie.
5. End with one grounded, practical next step they can take.

Respond with ONLY your answer as plain text — no JSON, no markdown formatting, no headers."""

        answer = call_groq(prompt, api_key, temperature=0.85, max_tokens=700)
        answer = answer.strip()

        return jsonify({"answer": answer})

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        return jsonify({"error": f"Groq API error ({e.code}): {error_body}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "Vyom AI engine is running", "engine": "Swiss Ephemeris + Lahiri Ayanamsa"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
