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
import re
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

# Curated Lal Kitab remedy library — paraphrased from multiple traditional sources,
# filtered to keep only safe, simple, low-cost, non-violent actions.
# Each planet has several candidate remedies; the AI selects and personalises ONE.
LAL_KITAB_REMEDIES = {
    "Sun": [
        "Offer water to the rising Sun each morning, facing east",
        "Donate jaggery and wheat to those in need on Sundays",
        "Feed roti (flatbread) to cows on Sunday mornings",
        "Spend a few minutes in sunlight each morning before starting your day"
    ],
    "Moon": [
        "Keep a small steel or copper vessel of water by your bed at night, and water a plant with it the next morning",
        "Donate rice, milk, or white sweets on Mondays",
        "Avoid difficult conversations with your mother or maternal figures on Mondays",
        "Spend a few quiet minutes near water (a river, lake, or even a bath) on Monday evenings"
    ],
    "Mars": [
        "Donate red lentils (masoor dal) or jaggery on Tuesdays",
        "Offer something sweet to someone in need on Tuesdays, especially before any difficult conversation",
        "Avoid starting arguments or major confrontations on Tuesdays",
        "Channel restless energy into physical activity early in the day"
    ],
    "Mercury": [
        "Donate green moong dal or fresh green vegetables on Wednesdays",
        "Keep your work or study desk clutter-free, especially on Wednesdays",
        "Feed green leafy fodder to a cow, or simply donate to a local goshala, on Wednesdays",
        "Write down your thoughts before an important conversation on Wednesdays"
    ],
    "Jupiter": [
        "Donate turmeric, chickpeas (chana dal), or yellow sweets on Thursdays",
        "Seek a few words of guidance from a teacher, mentor, or elder on Thursdays",
        "Water a tree (especially a peepal tree, if accessible) on Thursday mornings",
        "Set aside a small amount for charity each Thursday, even if modest"
    ],
    "Venus": [
        "Donate white items — rice, sugar, or white clothing — on Fridays",
        "Offer white flowers or light a candle at a place of worship on Fridays",
        "Do something small and generous for the women in your family on Fridays",
        "Spend time on something creative or beautifying your space on Fridays"
    ],
    "Saturn": [
        "Donate black sesame seeds, black lentils (urad dal), or iron items on Saturdays",
        "Feed crows or stray dogs on Saturday mornings",
        "Light a small mustard oil lamp on Saturday evenings",
        "Be extra patient with delays today — resist the urge to force outcomes"
    ],
    "Rahu": [
        "Donate mustard oil, black gram, or a coconut on Saturdays",
        "Give something to someone facing genuine hardship, without expecting anything in return",
        "Avoid shortcuts, new contracts, or impulsive decisions today — wait a day before committing",
        "Keep your living space tidy, especially under your bed and in storage areas"
    ],
    "Ketu": [
        "Donate sesame seeds or a blanket to someone in need",
        "Feed stray dogs, especially brown or black ones",
        "Spend 10 minutes in quiet reflection or meditation, with no phone nearby",
        "Let go of one small grudge or unresolved thought today"
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
        dasha_lord = data.get('dashaLord', '')

        # Build a candidate remedy list from the Mahadasha lord and Antardasha lord
        remedy_candidates = []
        for lord in [dasha_lord, antardasha]:
            if lord in LAL_KITAB_REMEDIES and lord not in [c[0] for c in remedy_candidates]:
                remedy_candidates.append((lord, LAL_KITAB_REMEDIES[lord]))

        remedy_options_text = ""
        for lord, options in remedy_candidates:
            remedy_options_text += f"\nFor {lord}, choose from:\n"
            for opt in options:
                remedy_options_text += f"- {opt}\n"

        if not remedy_options_text:
            # Fallback: offer Jupiter's remedies (generally benign/positive)
            remedy_options_text = "\nFor Jupiter, choose from:\n"
            for opt in LAL_KITAB_REMEDIES["Jupiter"]:
                remedy_options_text += f"- {opt}\n"

        prompt = f"""You are Vyom AI — a deeply wise, emotionally intelligent Vedic astrology guide. Your voice is calm, warm, and human. You never use jargon. You speak like a trusted friend who happens to understand the cosmos deeply.

Generate a personalised, REAL-TIME Vedic astrology reading for {data.get('name', 'Seeker')} for {data.get('today')}.

Their Vedic chart details:
- Lagna (Ascendant): {data.get('lagna')}
- Moon Sign (Rashi): {data.get('rashi')}
- Nakshatra: {data.get('nakshatra')} (Pada {data.get('pada')})
- Current Mahadasha: {data.get('dashaLord')}
- Current Antardasha: {antardasha}
- Planetary placements (house positions relative to their Lagna): {planets_summary}
- Active doshas in this chart: {data.get('active_doshas', 'None notable')}
- PRIMARY FOCUS REQUESTED: {focus_label}

CRITICAL INSTRUCTIONS:
1. The "today" field MUST be primarily about {focus_label} — this is what {data.get('name', 'Seeker')} specifically asked about. Reference the relevant planet's house placement from the data above to ground this in their actual chart (in plain language, no jargon).
2. Do NOT default to generic "overall life" advice — every reading must feel distinctly different depending on the focus area and the actual planetary placements given.
3. Avoid soft, vague, feel-good filler ("things will work out", "stay positive"). Be SPECIFIC and grounded — name a likely situation, a real tension, or a concrete opportunity based on the chart data. It's okay to mention a challenge or friction, not just positives.
4. Vary sentence rhythm and word choice — do not reuse the same openings or phrases across different focus areas.
5. For "planetary_influences": pick the 3 most significant planets right now (always include the Mahadasha lord and Antardasha lord, plus one more relevant to the {focus_label} focus). For each, describe in ONE plain-language sentence what that planet is "doing" in real-life terms — e.g. "Saturn is currently shaping how much responsibility you're carrying at work, and may be making a project feel slower than you'd like." No jargon, no house numbers — describe the real-life area and the felt effect.
6. For the Lal Kitab remedy: choose EXACTLY ONE option from the candidate list below (do not invent a new remedy — pick from this list verbatim or with very minor wording adjustment for natural flow). Pick whichever option best fits {data.get('name', 'Seeker')}'s {focus_label} focus.
7. If any doshas are listed as active above, briefly acknowledge EACH ONE in the DOSHA_NOTE field (not just one) — calm, factual, never alarming, one short sentence per dosha. If "None notable" or empty, write DOSHA_NOTE as a short reassuring note that no major doshas are currently active.

REMEDY CANDIDATES:{remedy_options_text}

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
[TODAY]4-5 sentences, primarily about {focus_label}, grounded in their actual planetary placements. Specific, real, and direct — not generic.[/TODAY]
[LOVE]2-3 sentences about relationships this week. Specific and actionable.[/LOVE]
[CAREER]2-3 sentences about work and purpose this week.[/CAREER]
[HEALTH]2-3 sentences about energy and physical wellbeing.[/HEALTH]
[FINANCE]2-3 sentences about money and material matters.[/FINANCE]
[ACTION]One clear, specific, poetic action they should take today, directly tied to the {focus_label} focus. Make it beautiful and doable. No more than 2 sentences.[/ACTION]
[REMEDY_NAME]The chosen remedy from the candidate list above, stated as a clear short instruction (you may lightly rephrase for flow, but keep the core action and timing intact)[/REMEDY_NAME]
[REMEDY_WHY]One sentence on why this remedy is suggested for them right now, connected to the planetary influence above — plain language, no jargon.[/REMEDY_WHY]
[REMEDY_HOW]One sentence describing exactly how and when to do it — simple, doable, low-cost, no special ingredients beyond common household items.[/REMEDY_HOW]
[DOSHA_NOTE]One short sentence for EACH active dosha listed above, calmly explaining its real-life effect (or a brief reassuring note if none are active). Plain language, factual tone — never fear-based.[/DOSHA_NOTE]

Tone rules:
- Never say "the stars say" or "the planets indicate" — just speak directly
- No jargon like "8th house" or "natal chart" — speak in plain human language (e.g. say "the area of your life connected to partnerships" instead of "7th house")
- Sound like a wise elder who genuinely cares — direct, real, sometimes challenging, never a fortune cookie
- Weave in the {data.get('dashaLord')} Mahadasha and {antardasha} Antardasha energy naturally
- The Lal Kitab remedy must be genuinely traditional, simple, safe, and inexpensive (water, grains, charity, colors, directions, timing) — never anything involving animal sacrifice, dangerous substances, or large expense

Output ONLY the tagged sections above, nothing else — no preamble, no closing remarks."""

        raw_text = call_groq(prompt, api_key)

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
1. First, check whether the question is a genuine, coherent question (even if vague, casual, or oddly phrased). If it's gibberish, random characters, a string of unrelated words, or otherwise doesn't form a real question — gently and warmly ask them to rephrase or share what's actually on their mind. Do NOT invent an astrological answer to nonsense. Keep this redirect short (1-3 sentences) and kind, e.g. "I want to make sure I understand you properly — could you share a bit more about what's on your mind?"
2. If it IS a genuine question, answer it directly — don't deflect into generic advice. If they ask about a specific situation (e.g. "should I take this job", "will my relationship work out", "is this a good time to invest"), engage with that specific situation using their chart data.
3. Ground your answer in their actual planetary placements — reference the relevant life area (career, relationships, finances, etc.) and which planet is influencing it, in plain language (no "8th house" type jargon).
4. Be honest and specific — including about likely challenges or timing concerns, not just reassurance. A wise guide tells the truth kindly, not just what someone wants to hear.
5. Length: 4-7 sentences for genuine questions. Warm but substantive — this should feel like real guidance, not a fortune cookie.
6. End with one grounded, practical next step they can take (only for genuine questions).

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
