"""Shared, deliberately lightweight field normalisation used by every matcher.

These are demo heuristics rather than production validation rules: they make common
formatting differences comparable while leaving uncertain values for the matcher to score.
"""

import re
import unicodedata

import jellyfish
import pandas as pd

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
TITLES = re.compile(r"\b(mr|mrs|ms|miss|dr|prof|sir)\b\.?", re.I)


def clean_name(s) -> str | None:
    """Normalize a person's name for comparison, preserving useful name punctuation."""
    if pd.isna(s) or not str(s).strip():
        return None
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = TITLES.sub("", s.lower())
    s = re.sub(r"[^a-z\s'-]", "", s).strip()
    return s or None


def clean_email(s) -> str | None:
    """Lowercase an email and normalize plus-tags and Gmail dot variants."""
    if pd.isna(s) or "@" not in str(s):
        return None
    local, domain = str(s).strip().lower().split("@", 1)
    local = local.split("+", 1)[0]
    # Gmail ignores dots in the local part; do not apply that rule to other providers.
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
    return f"{local}@{domain}"


def clean_phone(s) -> str | None:
    """Keep phone digits, normalize a leading UK country code, and reject short values."""
    if pd.isna(s):
        return None
    d = re.sub(r"\D", "", str(s))
    if d.startswith("44"):
        d = "0" + d[2:]
    return d if len(d) >= 10 else None


def clean_postcode(s) -> str | None:
    """Uppercase a UK postcode and insert its final-space separator."""
    if pd.isna(s):
        return None
    p = re.sub(r"\s", "", str(s).upper())
    return f"{p[:-3]} {p[-3:]}" if len(p) >= 5 else None


def standardise(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with normalized fields and derived keys used by all matchers."""
    out = df.copy()
    out["unique_id"] = out["source_record_id"]
    out["first_name"] = out["first_name"].map(clean_name)
    out["last_name"] = out["last_name"].map(clean_name)
    # Keep the cleaned spelling and a separate canonical form for known nicknames.
    out["first_name_canon"] = out["first_name"].map(
        lambda n: NICKNAMES.get(n, n) if n else None
    )
    out["email"] = out["email"].map(clean_email)
    out["email_user"] = out["email"].map(lambda e: e.split("@")[0] if e else None)
    out["phone"] = out["phone"].map(clean_phone)
    out["postcode"] = out["postcode"].map(clean_postcode)
    out["postcode_area"] = out["postcode"].map(lambda p: p.split(" ")[0] if p else None)
    out["address"] = out["address"].map(
        lambda a: re.sub(r"\s+", " ", str(a).lower()).strip() if pd.notna(a) else None
    )
    out["dob"] = pd.to_datetime(out["dob"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["surname_metaphone"] = out["last_name"].map(
        lambda n: jellyfish.metaphone(n) if n else None
    )
    out["first_metaphone"] = out["first_name_canon"].map(
        lambda n: jellyfish.metaphone(n) if n else None
    )
    return out
