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

def self_name_resonance(full_name, dob):
    """
    Compares ONE person's own name number against their OWN Life Path number.

    IMPORTANT — this is SELF-resonance only. It does NOT compare two people.
    Do not use this for spouse/partner compatibility, business/brand name
    resonance, child name suitability, or any two-person numerology
    comparison — use compare_numerology_profiles() or
    compare_name_to_user_profile() for those instead.
    """
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


def name_resonance(full_name, dob):
    """Backward-compatible alias for self_name_resonance(). See that
    function's docstring — this is self-resonance only, not a two-person
    comparison. Kept so existing callers (e.g. full_numerology_profile)
    don't break; new code should call self_name_resonance() directly."""
    return self_name_resonance(full_name, dob)

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

# ── BIRTH GRID (Psychomatrix / Arrows of Pythagoras) ───────────────────────
# What each cell (1-9) represents. Grid layout is fixed:
#   3 6 9   <- Mind plane
#   2 5 8   <- Soul plane
#   1 4 7   <- Body plane
CELL_TRAITS = {
    1: "will and character",
    2: "energy",
    3: "interest in learning",
    4: "health",
    5: "logic",
    6: "work ethic",
    7: "luck",
    8: "duty and patience",
    9: "memory",
}

GRID_PLANES = {
    "mind": (3, 6, 9),
    "soul": (2, 5, 8),
    "body": (1, 4, 7),
}

# Named lines. Only rows and diagonals are included — these are the lines
# with the most consistent naming/meaning across independent numerology
# sources. Columns vary too much source-to-source to name with confidence.
GRID_LINES = [
    {
        "cells": (3, 6, 9), "kind": "row", "plane": "mind",
        "present": "Arrow of Intellect",
        "present_desc": "Sharp, focused reasoning and a natural pull toward ideas.",
        "missing": "Arrow of Poor Memory",
        "missing_desc": "Memory and recall aren't reinforced by birth and benefit from deliberate practice.",
    },
    {
        "cells": (2, 5, 8), "kind": "row", "plane": "soul",
        "present": "Arrow of Emotional Balance",
        "present_desc": "A settled emotional core paired with natural intuition.",
        "missing": "Arrow of Hypersensitivity",
        "missing_desc": "Emotional protection is thinner here, making outside energy easier to absorb.",
    },
    {
        "cells": (1, 4, 7), "kind": "row", "plane": "body",
        "present": "Arrow of Practicality",
        "present_desc": "Grounded and action-oriented, comfortable turning plans into results.",
        "missing": "Arrow of Hesitation",
        "missing_desc": "Follow-through on action needs conscious building rather than coming naturally.",
    },
    {
        "cells": (1, 5, 9), "kind": "diagonal",
        "present": "Arrow of Determination",
        "present_desc": "Strong inner drive; once a decision is made, it's rarely abandoned.",
        "missing": "Arrow of Procrastination",
        "missing_desc": "Motivation tends to need external structure or accountability to take hold.",
    },
    {
        "cells": (3, 5, 7), "kind": "diagonal",
        "present": "Arrow of Spirituality",
        "present_desc": "Intuitive and reflective, at ease with life's uncertainties.",
        "missing": "Arrow of the Enquirer",
        "missing_desc": "A skeptical, evidence-first mind that questions before it trusts.",
    },
]


def birth_grid(dob):
    """
    Computes the birth grid (a.k.a. Psychomatrix / Arrows of Pythagoras) from
    the full date of birth. Uses the same _parse_dob() as the rest of this
    module, so it accepts whatever date formats life_path_number() etc. do.

    Returns:
    {
      "counts": {1: 2, 2: 1, ...},
      "planes": {"mind": {"cells": {...}, "total": N}, "soul": {...}, "body": {...}},
      "arrows": {"present": [...], "missing": [...]},
      "cell_traits": CELL_TRAITS,
    }
    """
    year, month, day = _parse_dob(dob)
    raw = f"{day:02d}{month:02d}{year:04d}"
    digits = [int(ch) for ch in raw if ch != "0"]
    counts = {n: digits.count(n) for n in range(1, 10)}

    planes_out = {}
    for plane, cells in GRID_PLANES.items():
        planes_out[plane] = {
            "cells": {c: counts[c] for c in cells},
            "total": sum(counts[c] for c in cells),
        }

    arrows_present, arrows_missing = [], []
    for line in GRID_LINES:
        vals = [counts[c] for c in line["cells"]]
        if all(v > 0 for v in vals):
            arrows_present.append({
                "name": line["present"], "cells": line["cells"],
                "description": line["present_desc"],
            })
        elif all(v == 0 for v in vals):
            arrows_missing.append({
                "name": line["missing"], "cells": line["cells"],
                "description": line["missing_desc"],
            })

    return {
        "counts": counts,
        "planes": planes_out,
        "arrows": {"present": arrows_present, "missing": arrows_missing},
        "cell_traits": CELL_TRAITS,
    }


def birth_grid_summary_for_prompt(dob):
    """Plain-text summary of the birth grid, for inserting into an AI prompt."""
    data = birth_grid(dob)
    lines = []

    for n in range(1, 10):
        count = data["counts"][n]
        trait = CELL_TRAITS[n]
        if count == 0:
            lines.append(f"- {trait} (number {n}): absent from the birth grid")
        else:
            times = "time" if count == 1 else "times"
            lines.append(f"- {trait} (number {n}): appears {count} {times}")

    if data["arrows"]["present"]:
        names = "; ".join(a["name"] for a in data["arrows"]["present"])
        lines.append(f"Completed arrows: {names}")
    if data["arrows"]["missing"]:
        names = "; ".join(a["name"] for a in data["arrows"]["missing"])
        lines.append(f"Missing arrows: {names}")

    return "\n".join(lines)


# ── DATA SUFFICIENCY & TWO-PERSON COMPARISON ───────────────────────────────
# These functions let main.py decide WHAT can be calculated and compared
# before any AI call happens. numerology.py calculates; it never decides
# whether a question is "answerable" — that's main.py's job, using these
# building blocks.

RELATION_ONLY_WORDS = {
    "wife", "husband", "partner", "spouse", "girlfriend", "boyfriend",
    "fiance", "fiancee", "son", "daughter", "child", "baby", "mother",
    "father", "brother", "sister", "friend", "colleague", "coworker",
    "him", "her", "them", "someone", "person", "guy", "girl", "man", "woman",
}

# Common filler words stripped before checking if anything usable remains
_FILLER_WORDS = {"my", "the", "a", "an", "our", "his", "her", "their", "this", "that"}


def has_usable_name(value):
    """
    Return True only if `value` contains enough alphabetic content to
    calculate name numerology, and isn't just a relation word ("my wife"),
    a vague pronoun ("her"), or empty/whitespace.
    """
    if not value or not isinstance(value, str):
        return False
    words = [w.strip(".,!?'\"").lower() for w in value.strip().split()]
    words = [w for w in words if w and w not in _FILLER_WORDS]
    if not words:
        return False
    # Reject if EVERY remaining word is a relation-only word
    if all(w in RELATION_ONLY_WORDS for w in words):
        return False
    # Must contain enough actual letters to run Pythagorean calculation on
    letter_count = sum(1 for ch in value.upper() if ch in LETTER_VALUES)
    return letter_count >= 2


def has_usable_dob(value):
    """Return True only if `value` can actually be parsed as a date."""
    if not value:
        return False
    try:
        _parse_dob(value)
        return True
    except Exception:
        return False


def partial_profile_from_available_data(name=None, dob=None, target_year=None):
    """
    Build ONLY the numbers that can actually be calculated from whatever
    data is available. Never fails just because name or dob is missing —
    that's the point: partial data still returns partial, real numbers.
    """
    name_ok = has_usable_name(name) if name else False
    dob_ok = has_usable_dob(dob) if dob else False

    numbers = {}
    missing_fields = []
    available_fields = []

    if name_ok:
        available_fields.append("name")
        numbers["expression"] = {"number": expression_number(name), "meaning": CORE_MEANINGS.get(expression_number(name), "")}
        numbers["soul_urge"] = {"number": soul_urge_number(name), "meaning": CORE_MEANINGS.get(soul_urge_number(name), "")}
        numbers["personality"] = {"number": personality_number(name), "meaning": CORE_MEANINGS.get(personality_number(name), "")}
    else:
        missing_fields.append("name")

    if dob_ok:
        available_fields.append("dob")
        py_year = target_year if target_year is not None else date.today().year
        numbers["life_path"] = {"number": life_path_number(dob), "meaning": CORE_MEANINGS.get(reduce_number(life_path_number(dob)), "")}
        numbers["birthday"] = {"number": birthday_number(dob), "meaning": CORE_MEANINGS.get(birthday_number(dob), "")}
        numbers["personal_year"] = {"number": personal_year_number(dob, py_year), "meaning": PERSONAL_YEAR_THEMES.get(personal_year_number(dob, py_year), "")}
    else:
        missing_fields.append("dob")

    if name_ok and dob_ok:
        numbers["maturity"] = {"number": maturity_number(name, dob), "meaning": CORE_MEANINGS.get(maturity_number(name, dob), "")}

    return {
        "input": {"name_available": name_ok, "dob_available": dob_ok},
        "numbers": numbers,
        "missing_fields": missing_fields,
        "available_fields": available_fields,
    }


def build_target_profile(target):
    """
    Build a numerology profile for a SECOND person/entity only — a spouse,
    friend, brand, business, etc. NEVER treat this as the main user's data.

    target: dict with optional 'name' and/or 'dob' keys (e.g. from a
    frontend follow-up form: {"relation": "wife", "name": "", "dob": "..."})
    Returns None if target is empty/missing entirely.
    """
    if not target:
        return None
    name = target.get("name") or None
    dob = target.get("dob") or None
    if not name and not dob:
        return None
    return partial_profile_from_available_data(name=name, dob=dob)


def compare_number_pair(a, b):
    """
    Compare two already-reduced numbers using the friends/neutral/tension
    tables. Returns a structured verdict, never a bare string.
    """
    ra = reduce_number(a, keep_master=False)
    rb = reduce_number(b, keep_master=False)

    if ra == rb or rb in _NUMBER_FRIENDS.get(ra, set()):
        verdict = "supportive"
        meaning = f"{a} and {b} share a natural, easy alignment."
    elif rb in _NUMBER_NEUTRAL.get(ra, set()):
        verdict = "mixed"
        meaning = f"{a} and {b} sit in steady, neutral balance — neither reinforcing nor working against each other."
    else:
        verdict = "challenging"
        meaning = f"{a} and {b} pull in somewhat different directions, a real but workable friction."

    return {
        "a": a, "b": b,
        "verdict": verdict,
        "meaning": meaning,
        "confidence": "medium",
    }


def compare_numerology_profiles(user_profile, target_profile):
    """
    Compare two PEOPLE's numerology profiles — only when target_profile
    actually contains usable numbers. Never invents a missing side.

    user_profile: output of full_numerology_profile()
    target_profile: output of partial_profile_from_available_data(), or None
    """
    if not target_profile or not target_profile.get("numbers"):
        return {
            "can_compare": False,
            "comparison_type": "two_person_numerology",
            "overall_verdict": None,
            "confidence": "none",
            "pairs": [],
            "missing_fields": ["target_name_or_dob"],
            "reason": "A second person's numerology data is required before compatibility can be judged.",
        }

    PAIR_MAP = [
        ("life_direction", "life_path", "life_path"),
        ("expression", "expression", "expression"),
        ("soul_urge", "soul_urge", "soul_urge"),
        ("personality", "personality", "personality"),
    ]

    pairs = []
    for area, user_key, target_key in PAIR_MAP:
        u = user_profile.get(user_key, {}).get("number")
        t = target_profile["numbers"].get(target_key, {}).get("number")
        if u is None or t is None:
            continue
        cmp = compare_number_pair(u, t)
        pairs.append({
            "area": area,
            "user_number": u,
            "target_number": t,
            "verdict": cmp["verdict"],
            "meaning": cmp["meaning"],
        })

    if not pairs:
        return {
            "can_compare": False,
            "comparison_type": "two_person_numerology",
            "overall_verdict": None,
            "confidence": "none",
            "pairs": [],
            "missing_fields": target_profile.get("missing_fields", ["target_name_or_dob"]),
            "reason": "Not enough overlapping numbers between both profiles to compare yet.",
        }

    verdict_counts = {"supportive": 0, "mixed": 0, "challenging": 0}
    for p in pairs:
        verdict_counts[p["verdict"]] += 1
    overall_verdict = max(verdict_counts, key=verdict_counts.get)

    return {
        "can_compare": True,
        "comparison_type": "two_person_numerology",
        "overall_verdict": overall_verdict,
        "confidence": "medium" if len(pairs) >= 2 else "low",
        "pairs": pairs,
        "missing_fields": target_profile.get("missing_fields", []),
    }


def compare_name_to_user_profile(target_name, user_profile, purpose="general"):
    """
    Compare a proposed name — business, brand, child, page, product — against
    the user's OWN numerology profile. NOT the same as spouse/partner
    compatibility (use compare_numerology_profiles for that).
    """
    if not has_usable_name(target_name):
        return {
            "can_compare": False,
            "comparison_type": "target_name_to_user",
            "target_name": target_name,
            "reason": "No usable name was given to calculate.",
        }

    target_number = expression_number(target_name)
    user_lp = user_profile.get("life_path", {}).get("number")
    user_expr = user_profile.get("expression", {}).get("number")

    cmp = compare_number_pair(user_lp, target_number) if user_lp is not None else None

    return {
        "can_compare": True,
        "comparison_type": "target_name_to_user",
        "target_name": target_name,
        "target_name_number": target_number,
        "user_life_path": user_lp,
        "user_expression": user_expr,
        "verdict": cmp["verdict"] if cmp else "unknown",
        "confidence": cmp["confidence"] if cmp else "low",
        "meaning": cmp["meaning"] if cmp else "",
        "purpose": purpose,
    }
