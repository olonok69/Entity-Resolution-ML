"""Shared, deliberately lightweight field normalisation used by every matcher.

These are demo heuristics rather than production validation rules: they make common
formatting differences comparable while leaving uncertain values for the matcher to score.

Why standardise first: "+44 7123 456789" and "07123456789" are the same phone, and
"SMITH" and "smith" are the same surname. If those differences survive into matching, the
matcher wastes evidence on formatting instead of on real disagreement. Every matching
step (01-05, 07, 08) calls standardise() on the raw CSV, so all see identical inputs.

Input:  a raw DataFrame with the columns written by data/generate_data.py.
Output: a copy with cleaned fields plus derived keys (unique_id, first_name_canon,
        email_user, postcode_area, surname_metaphone, first_metaphone) used for
        blocking and comparison.
Slides: 4 (Pipeline, the standardise stage), 7 (Blocking keys), 8 (scoring a pair).
"""

# re: regular expressions for stripping characters and whitespace.
import re
# unicodedata: turns accented letters into plain ASCII ("Zoë" -> "Zoe").
import unicodedata

# jellyfish: string similarity and phonetic encoding library (metaphone used below).
import jellyfish
import pandas as pd

# Nickname -> formal name. The reverse of the map in data/generate_data.py, plus a few
# extra common forms (rob, will, beth, jimmy, katie) a real source might contain.
NICKNAMES = {
    "bob": "robert",
    "rob": "robert",
    "bill": "william",
    "will": "william",
    "liz": "elizabeth",
    "beth": "elizabeth",
    "maggie": "margaret",
    "jim": "james",
    "jimmy": "james",
    "mike": "michael",
    "kate": "katherine",
    "katie": "katherine",
    "tom": "thomas",
    "chris": "christopher",
    "dan": "daniel",
    "jen": "jennifer",
    "rich": "richard",
    "joe": "joseph",
    "sam": "samuel",
    "alex": "alexander",
    "matt": "matthew",
    "becky": "rebecca",
    "vicky": "victoria",
    "jon": "jonathan",
    "steve": "stephen",
}
# Honorifics to remove. \b is a word boundary, so only whole words match ("amro" keeps its
# "mr"); \.? also eats a trailing dot ("Dr."); re.I makes it case-insensitive.
TITLES = re.compile(r"\b(mr|mrs|ms|miss|dr|prof|sir)\b\.?", re.I)


def clean_name(s) -> str | None:
    """Normalize a person's name for comparison, preserving useful name punctuation."""
    # Missing (NaN/None) or blank names become None, so matchers treat them as "no evidence".
    if pd.isna(s) or not str(s).strip():
        return None
    # NFKD splits "é" into "e" + accent mark; encode to ASCII with "ignore" drops the mark.
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    # Lowercase, then strip titles such as "mr" or "dr.".
    s = TITLES.sub("", s.lower())
    # Keep only letters, spaces, apostrophes and hyphens (O'Brien, Smith-Jones).
    s = re.sub(r"[^a-z\s'-]", "", s).strip()
    # An empty result (the name was only a title or digits) becomes None.
    return s or None


def clean_email(s) -> str | None:
    """Lowercase an email and normalize plus-tags and Gmail dot variants."""
    # Anything without an "@" is not a usable email.
    if pd.isna(s) or "@" not in str(s):
        return None
    # Split once at the first "@" into the user part and the domain.
    local, domain = str(s).strip().lower().split("@", 1)
    # Drop plus-tags: "jane+shop@x.com" delivers to "jane@x.com".
    local = local.split("+", 1)[0]
    # Gmail ignores dots in the local part; do not apply that rule to other providers.
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
    return f"{local}@{domain}"


def clean_phone(s) -> str | None:
    """Keep phone digits, normalize a leading UK country code, and reject short values."""
    if pd.isna(s):
        return None
    # \D matches any non-digit: removes spaces, dashes, "+" and brackets.
    d = re.sub(r"\D", "", str(s))
    # "447123..." (from +44) becomes the national form "07123...".
    if d.startswith("44"):
        d = "0" + d[2:]
    # Fewer than 10 digits cannot be a full UK number; treat it as missing.
    return d if len(d) >= 10 else None


def clean_postcode(s) -> str | None:
    """Uppercase a UK postcode and insert its final-space separator."""
    if pd.isna(s):
        return None
    # Remove all whitespace and uppercase: "wr3w 3wh" and "WR3W3WH" both become "WR3W3WH".
    p = re.sub(r"\s", "", str(s).upper())
    # A UK postcode's inward code is always the last 3 characters, so re-insert the space
    # there ("WR3W 3WH"). Values too short to be a postcode become None.
    return f"{p[:-3]} {p[-3:]}" if len(p) >= 5 else None


def standardise(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with normalized fields and derived keys used by all matchers."""
    # Work on a copy so the caller's raw data stays untouched (useful for golden records).
    out = df.copy()
    # Splink requires a column called unique_id; reuse the source record id.
    out["unique_id"] = out["source_record_id"]
    # Series.map(f) applies f to every value in the column and returns the new column.
    out["first_name"] = out["first_name"].map(clean_name)
    out["last_name"] = out["last_name"].map(clean_name)
    # Keep the cleaned spelling and a separate canonical form for known nicknames.
    # dict.get(n, n) returns the formal name if n is a nickname, otherwise n itself.
    out["first_name_canon"] = out["first_name"].map(
        lambda n: NICKNAMES.get(n, n) if n else None
    )
    out["email"] = out["email"].map(clean_email)
    # The part before "@": lets a matcher see "jane.doe" on two different providers.
    out["email_user"] = out["email"].map(lambda e: e.split("@")[0] if e else None)
    out["phone"] = out["phone"].map(clean_phone)
    out["postcode"] = out["postcode"].map(clean_postcode)
    # Outward code ("WR3W" of "WR3W 3WH"): a coarse location. Same area but different full
    # postcode is weaker evidence than an exact postcode (used as a feature in 03_ml).
    out["postcode_area"] = out["postcode"].map(lambda p: p.split(" ")[0] if p else None)
    # Address: lowercase and collapse runs of whitespace to single spaces.
    out["address"] = out["address"].map(
        lambda a: re.sub(r"\s+", " ", str(a).lower()).strip() if pd.notna(a) else None
    )
    # Parse dates; errors="coerce" turns unparseable values into NaT (missing), then
    # format back to "YYYY-MM-DD" text so equal dates are equal strings.
    out["dob"] = pd.to_datetime(out["dob"], errors="coerce").dt.strftime("%Y-%m-%d")
    # Metaphone is a phonetic code: names that sound alike get the same code
    # (e.g. "smith" and "smyth" both encode to "SM0"). Used as a typo-tolerant blocking key.
    out["surname_metaphone"] = out["last_name"].map(
        lambda n: jellyfish.metaphone(n) if n else None
    )
    # Encode the canonical first name, so "bob" and "robert" share a code too.
    out["first_metaphone"] = out["first_name_canon"].map(
        lambda n: jellyfish.metaphone(n) if n else None
    )
    return out
