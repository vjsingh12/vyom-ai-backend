"""
Vayuman — Pythagorean Numerology Engine
========================================

A self-contained, dependency-free module that computes the core Pythagorean
numerology numbers from a person's full birth name and date of birth.

Standard conventions used (the most widely accepted):
  - Letter chart: A=1 B=2 C=3 D=4 E=5 F=6 G=7 H=8 I=9, then J=1 ... repeating 1-9.
  - Master numbers 11, 22, 33 are preserved (not reduced to a single digit)
    when they arise as a final total.
  - Life Path: reduce month, day, and year SEPARATELY to a single/master number,
    then add those three and reduce again (the most common method; handles
    master numbers correctly).
  - Vowels = A, E, I, O, U.  Y is treated as a vowel ONLY when it acts as one
    (no adjacent vowel in the same name-part); otherwise it's a consonant.
  - Soul Urge uses vowels; Personality uses consonants; Expression uses all letters.

Public API:
    full_numerology_profile(full_name: str, dob: str) -> dict
        dob accepted as 'YYYY-MM-DD' (or 'DD/MM/YYYY' / 'MM-DD-YYYY' best-effort).

The interpretation TEXT here is brief and neutral; richer, warm interpretation
should be generated downstream (e.g. via the AI prompt) in Vayuman's voice.
"""

from datetime import date
import re

MASTER_NUMBERS = {11, 22, 33}

# Pythagorean letter -> value (A=1 .. I=9, J=1 .. R=9, S=1 .. Z=8)
LETTER_VALUES = {}
for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    LETTER_VALUES[ch] = (i % 9) + 1

VOWELS = set("AEIOU")


# ──────────────────────────────────────────────────────────────────────────
# Core reduction helpers
# ──────────────────────────────────────────────────────────────────────────

def reduce_number(n, keep_master=True):
    """Reduce an integer by summing its digits until it's a single digit,
    preserving master numbers (11, 22, 33) when keep_master is True."""
    n = abs(int(n))
    while n > 9:
        if keep_master and n in MASTER_NUMBERS:
            return n
        n = sum(int(d) for d in str(n))
    return n


def _is_y_vowel(name_part, index):
    """Decide whether the Y at position `index` in name_part acts as a vowel.
    Heuristic: Y is a vowel if it is NOT adjacent to another vowel within the
    same word part (i.e. it is carrying the vowel sound). This is the common
    practical rule used by numerology calculators."""
    prev_ch = name_part[index - 1] if index > 0 else ''
    next_ch = name_part[index + 1] if index + 1 < len(name_part) else ''
    # If a real vowel is directly beside it, Y is a glide (consonant-like)
    if prev_ch in VOWELS or next_ch in VOWELS:
        return False
    return True


def _classify_letters(full_name):
    """Return (all_letters, vowel_letters, consonant_letters) with Y handled
    per word so its vowel/consonant role is decided in context."""
    all_letters, vowels, consonants = [], [], []
    # Process word-by-word so Y context is per word
    for word in re.split(r"[\s'-]+", full_name.upper()):
        for idx, ch in enumerate(word):
            if ch not in LETTER_VALUES:
                continue
            all_letters.append(ch)
            if ch in VOWELS:
                vowels.append(ch)
            elif ch == 'Y':
                if _is_y_vowel(word, idx):
                    vowels.append(ch)
                else:
                    consonants.append(ch)
            else:
                consonants.append(ch)
    return all_letters, vowels, consonants


def _sum_letters(letters):
    return sum(LETTER_VALUES[c] for c in letters)


# ──────────────────────────────────────────────────────────────────────────
# Date parsing
# ──────────────────────────────────────────────────────────────────────────

def _parse_dob(dob):
    """Parse a DOB string into (year, month, day). Accepts:
       YYYY-MM-DD (preferred), DD/MM/YYYY, MM/DD/YYYY (best-effort)."""
    if isinstance(dob, date):
        return dob.year, dob.month, dob.day
    s = str(dob).strip()
    # ISO: YYYY-MM-DD
    m = re.match(r'^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$', s)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    # DD/MM/YYYY or MM/DD/YYYY  -> assume DD/MM/YYYY (most of the world);
    # if first field > 12 it must be the day, which confirms DD/MM.
    m = re.match(r'^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$', s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12:      # a must be day
            return y, b, a
        if b > 12:      # b must be day -> MM/DD
            return y, a, b
        return y, b, a  # ambiguous -> assume DD/MM/YYYY
    raise ValueError(f"Unrecognised date format: {dob!r} (use YYYY-MM-DD)")


# ──────────────────────────────────────────────────────────────────────────
# Core number calculations
# ──────────────────────────────────────────────────────────────────────────

def life_path_number(dob):
    """Life Path: reduce month, day, year separately (preserving masters),
    then add and reduce again."""
    year, month, day = _parse_dob(dob)
    m = reduce_number(month)
    d = reduce_number(day)
    y = reduce_number(year)
    return reduce_number(m + d + y)


def expression_number(full_name):
    """Expression / Destiny: all letters of the full birth name."""
    all_letters, _, _ = _classify_letters(full_name)
    return reduce_number(_sum_letters(all_letters))


def soul_urge_number(full_name):
    """Soul Urge / Heart's Desire: vowels only."""
    _, vowels, _ = _classify_letters(full_name)
    return reduce_number(_sum_letters(vowels))


def personality_number(full_name):
    """Personality: consonants only."""
    _, _, consonants = _classify_letters(full_name)
    return reduce_number(_sum_letters(consonants))


def birthday_number(dob):
    """Birthday number: the day of the month, reduced (masters preserved)."""
    _, _, day = _parse_dob(dob)
    return reduce_number(day)


def maturity_number(full_name, dob):
    """Maturity: Life Path + Expression, reduced."""
    return reduce_number(life_path_number(dob) + expression_number(full_name))


def personal_year_number(dob, target_year=None):
    """Personal Year: reduce(birth month + birth day + the target/current year).
    This is the main TIMING number — it changes each calendar year."""
    _, month, day = _parse_dob(dob)
    if target_year is None:
        target_year = date.today().year
    return reduce_number(reduce_number(month) + reduce_number(day) + reduce_number(target_year))


# ──────────────────────────────────────────────────────────────────────────
# Brief neutral meanings (placeholders — rich text generated downstream by AI)
# ──────────────────────────────────────────────────────────────────────────

CORE_MEANINGS = {
    1: "Independence, leadership, initiative, self-reliance.",
    2: "Cooperation, sensitivity, partnership, diplomacy.",
    3: "Creativity, expression, optimism, communication.",
    4: "Stability, discipline, hard work, building foundations.",
    5: "Freedom, change, curiosity, adaptability.",
    6: "Responsibility, nurturing, harmony, service to others.",
    7: "Introspection, analysis, spirituality, seeking truth.",
    8: "Ambition, material mastery, authority, achievement.",
    9: "Compassion, idealism, completion, humanitarianism.",
    11: "Master number: intuition, inspiration, spiritual insight.",
    22: "Master number: the master builder, turning vision into reality.",
    33: "Master number: the master teacher, compassion and uplifting others.",
}

PERSONAL_YEAR_THEMES = {
    1: "A year of new beginnings, fresh starts, and planting seeds.",
    2: "A year of patience, relationships, and quiet development.",
    3: "A year of creativity, social connection, and self-expression.",
    4: "A year of hard work, structure, and laying foundations.",
    5: "A year of change, freedom, travel, and the unexpected.",
    6: "A year of home, responsibility, love, and family matters.",
    7: "A year of reflection, study, rest, and inner growth.",
    8: "A year of ambition, career, finances, and tangible results.",
    9: "A year of endings, release, and completing a chapter.",
    11: "A heightened year of intuition and spiritual awakening.",
    22: "A powerful year for building something lasting.",
    33: "A year of compassion, teaching, and service.",
}

# Traditional number -> ruling planet, lucky day, lucky colours, gemstone.
# Master numbers reduce to their root for these lucky attributes (11->2, 22->4,
# 33->6) since the planetary/colour system is based on the single digits 1-9.
LUCKY_ATTRIBUTES = {
    1: {"planet": "Sun",     "day": "Sunday",    "colours": ["Gold", "Orange", "Yellow"],        "gemstone": "Ruby"},
    2: {"planet": "Moon",    "day": "Monday",    "colours": ["White", "Cream", "Silver"],         "gemstone": "Pearl"},
    3: {"planet": "Jupiter", "day": "Thursday",  "colours": ["Yellow", "Gold", "Violet"],         "gemstone": "Yellow Sapphire"},
    4: {"planet": "Rahu",    "day": "Sunday",    "colours": ["Grey", "Electric Blue", "Khaki"],   "gemstone": "Hessonite"},
    5: {"planet": "Mercury", "day": "Wednesday", "colours": ["Green", "Light Green", "Turquoise"],"gemstone": "Emerald"},
    6: {"planet": "Venus",   "day": "Friday",    "colours": ["Pink", "Light Blue", "White"],      "gemstone": "Diamond"},
    7: {"planet": "Ketu",    "day": "Monday",    "colours": ["Light Grey", "Sea Green", "Smoke"], "gemstone": "Cat's Eye"},
    8: {"planet": "Saturn",  "day": "Saturday",  "colours": ["Dark Blue", "Black", "Purple"],     "gemstone": "Blue Sapphire"},
    9: {"planet": "Mars",    "day": "Tuesday",   "colours": ["Red", "Maroon", "Rose"],            "gemstone": "Red Coral"},
}


def lucky_profile(dob):
    """Lucky number, ruling planet, day, colours, and gemstone — derived from
    the Birthday root number (the single-digit reduction of the day of birth,
    the traditional 'Moolank' used for lucky attributes)."""
    _, _, day = _parse_dob(dob)
    root = reduce_number(day, keep_master=False)  # 1-9 for lucky attributes
    attrs = LUCKY_ATTRIBUTES[root]
    return {
        "lucky_number": root,
        "ruling_planet": attrs["planet"],
        "lucky_day": attrs["day"],
        "lucky_colours": attrs["colours"],
        "lucky_gemstone": attrs["gemstone"],
    }


# ──────────────────────────────────────────────────────────────────────────
# Full profile
# ──────────────────────────────────────────────────────────────────────────

def full_numerology_profile(full_name, dob, target_year=None):
    """Compute the full Pythagorean numerology profile.

    Returns a dict with all core numbers, their brief meanings, and the
    inputs used. Designed to be fed into an AI prompt for rich interpretation.
    """
    lp = life_path_number(dob)
    expr = expression_number(full_name)
    soul = soul_urge_number(full_name)
    pers = personality_number(full_name)
    bday = birthday_number(dob)
    mat = maturity_number(full_name, dob)
    py_year = target_year if target_year is not None else date.today().year
    py = personal_year_number(dob, py_year)

    def pack(num, table):
        return {"number": num, "meaning": table.get(num, "")}

    return {
        "input": {
            "name": full_name,
            "dob": str(dob),
            "personal_year_for": py_year,
        },
        "life_path":   pack(lp, CORE_MEANINGS),
        "expression":  pack(expr, CORE_MEANINGS),
        "soul_urge":   pack(soul, CORE_MEANINGS),
        "personality": pack(pers, CORE_MEANINGS),
        "birthday":    pack(bday, CORE_MEANINGS),
        "maturity":    pack(mat, CORE_MEANINGS),
        "personal_year": pack(py, PERSONAL_YEAR_THEMES),
        "lucky": lucky_profile(dob),
    }


if __name__ == "__main__":
    # Quick manual demo
    import json
    profile = full_numerology_profile("John Doe", "1985-03-14")
    print(json.dumps(profile, indent=2))
