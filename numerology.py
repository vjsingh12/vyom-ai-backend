"""
Vayuman — Pythagorean Numerology Engine
========================================

A self-contained, dependency-free module that computes the core Pythagorean
numerology numbers from a person's full birth name and date of birth.
"""

from datetime import date
import re

MASTER_NUMBERS = {11, 22, 33}

# Pythagorean letter -> value
LETTER_VALUES = {}
for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    LETTER_VALUES[ch] = (i % 9) + 1

VOWELS = set("AEIOU")

def reduce_number(n, keep_master=True):
    n = abs(int(n))
    while n > 9:
        if keep_master and n in MASTER_NUMBERS:
            return n
        n = sum(int(d) for d in str(n))
    return n

def _is_y_vowel(name_part, index):
    prev_ch = name_part[index - 1] if index > 0 else ''
    next_ch = name_part[index + 1] if index + 1 < len(name_part) else ''
    if prev_ch in VOWELS or next_ch in VOWELS:
        return False
    return True

def _classify_letters(full_name):
    all_letters, vowels, consonants = [], [], []
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

def _parse_dob(dob):
    if isinstance(dob, date):
        return dob.year, dob.month, dob.day
    s = str(dob).strip()
    m = re.match(r'^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$', s)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r'^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$', s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12: return y, b, a
        if b > 12: return y, a, b
        return y, b, a
    raise ValueError(f"Unrecognised date format: {dob!r} (use YYYY-MM-DD)")

def life_path_number(dob):
    year, month, day = _parse_dob(dob)
    return reduce_number(reduce_number(month) + reduce_number(day) + reduce_number(year))

def expression_number(full_name):
    all_letters, _, _ = _classify_letters(full_name)
    return reduce_number(_sum_letters(all_letters))

def soul_urge_number(full_name):
    _, vowels, _ = _classify_letters(full_name)
    return reduce_number(_sum_letters(vowels))

def personality_number(full_name):
    _, _, consonants = _classify_letters(full_name)
    return reduce_number(_sum_letters(consonants))

def birthday_number(dob):
    _, _, day = _parse_dob(dob)
    return reduce_number(day)

def maturity_number(full_name, dob):
    return reduce_number(life_path_number(dob) + expression_number(full_name))

def personal_year_number(dob, target_year=None):
    _, month, day = _parse_dob(dob)
    if target_year is None:
        target_year = date.today().year
    return reduce_number(reduce_number(month) + reduce_number(day) + reduce_number(target_year))

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

LUCKY_ATTRIBUTES = {
    1: {"planet": "Sun", "day": "Sunday", "colours": ["Gold", "Orange", "Yellow"], "gemstone": "Ruby"},
    2: {"planet": "Moon", "day": "Monday", "colours": ["White", "Cream", "Silver"], "gemstone": "Pearl"},
    3: {"planet": "Jupiter", "day": "Thursday", "colours": ["Yellow", "Gold", "Violet"], "gemstone": "Yellow Sapphire"},
    4: {"planet": "Rahu", "day": "Sunday", "colours": ["Grey", "Electric Blue", "Khaki"], "gemstone": "Hessonite"},
    5: {"planet": "Mercury", "day": "Wednesday", "colours": ["Green", "Light Green", "Turquoise"], "gemstone": "Emerald"},
    6: {"planet": "Venus", "day": "Friday", "colours": ["Pink", "Light Blue", "White"], "gemstone": "Diamond"},
    7: {"planet": "Ketu", "day": "Monday", "colours": ["Light Grey", "Sea Green", "Smoke"], "gemstone": "Cat's Eye"},
    8: {"planet": "Saturn", "day": "Saturday", "colours": ["Dark Blue", "Black", "Purple"], "gemstone": "Blue Sapphire"},
    9: {"planet": "Mars", "day": "Tuesday", "colours": ["Red", "Maroon", "Rose"], "gemstone": "Red Coral"},
}

def lucky_profile(dob):
    _, _, day = _parse_dob(dob)
    root = reduce_number(day, keep_master=False)
    attrs = LUCKY_ATTRIBUTES.get(root, LUCKY_ATTRIBUTES[1])
    return {
        "lucky_number": root,
        "ruling_planet": attrs["planet"],
        "lucky_day": attrs["day"],
        "lucky_colours": attrs["colours"],
        "lucky_gemstone": attrs["gemstone"],
    }

_NUMBER_FRIENDS = {
    1: {1, 2, 3, 5, 9}, 2: {1, 2, 3, 5}, 3: {1, 2, 3, 5, 7, 9},
    4: {1, 5, 6, 7}, 5: {1, 5, 6, 3, 9}, 6: {4, 5, 6, 8, 9},
    7: {1, 4, 5, 7}, 8: {5, 6, 8}, 9: {1, 3, 5, 6, 9},
}
_NUMBER_NEUTRAL = {
    1: {4, 7, 8}, 2: {4, 7, 9}, 3: {4, 6, 8}, 4: {2, 3, 8, 9},
    5: {2, 4, 7, 8}, 6: {1, 2, 3, 7}, 7: {2, 3, 6, 9},
    8: {1, 3, 4, 7, 9}, 9: {2, 4, 7, 8},
}

def name_resonance(full_name, dob):
    lp_full = life_path_number(dob)
    expr_full = expression_number(full_name)
    lp = reduce_number(lp_full, keep_master=False)
    nm = reduce_number(expr_full, keep_master=False)

    if nm in _NUMBER_FRIENDS.get(lp, set()) or nm == lp:
        verdict = "strong"
        headline = "Your name resonates strongly with your core number"
        note = "Your name's number and your life-path number support one another."
    elif nm in _NUMBER_NEUTRAL.get(lp, set()):
        verdict = "neutral"
        headline = "Your name sits in gentle balance with your core number"
        note = "A steady, neutral footing that neither helps nor hinders."
    else:
        verdict = "tension"
        headline = "Your name carries a quiet tension with your core number"
        note = "They pull in somewhat different directions — a subtle friction."

    return {
        "name_number": expr_full,
        "life_path_number": lp_full,
        "verdict": verdict,
        "headline": headline,
        "note": note,
    }

# ── NEW STEP-BY-STEP BREAKDOWN HELPER ─────────────────────────────────────
def name_number_breakdown(full_name):
    """Return detailed Pythagorean breakdown for each word and the full name."""
    words = []
    grand_total = 0

    for raw_word in re.split(r"[\s'-]+", full_name.upper().strip()):
        letters = [ch for ch in raw_word if ch in LETTER_VALUES]
        if not letters:
            continue

        values = [{"letter": ch, "value": LETTER_VALUES[ch]} for ch in letters]
        total = sum(item["value"] for item in values)
        reduced = reduce_number(total, keep_master=True)
        grand_total += total

        words.append({
            "word": raw_word,
            "letters": values,
            "total": total,
            "reduced": reduced,
        })

    return {
        "words": words,
        "full_total": grand_total,
        "full_reduced": reduce_number(grand_total, keep_master=True),
    }

def full_numerology_profile(full_name, dob, target_year=None):
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
        "life_path": pack(lp, CORE_MEANINGS),
        "expression": pack(expr, CORE_MEANINGS),
        "soul_urge": pack(soul, CORE_MEANINGS),
        "personality": pack(pers, CORE_MEANINGS),
        "birthday": pack(bday, CORE_MEANINGS),
        "maturity": pack(mat, CORE_MEANINGS),
        "personal_year": pack(py, PERSONAL_YEAR_THEMES),
        "lucky": lucky_profile(dob),
        "name_resonance": name_resonance(full_name, dob),
    }
