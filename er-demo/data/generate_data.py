"""Generate synthetic UK customer records spread over 3 source systems, with known truth.

Each real person ("entity") appears in 1..3 systems (CRM, WEB, BILLING) and sometimes twice
in the same system. Every copy gets realistic noise: typos, nicknames, swapped names,
missing values, different phone / postcode formats, moved address, DOB day-month swap.
About 10% of people also live with another person (a household): same address, often the
same surname and sometimes a shared family email. That is what makes the hierarchy and
"generic identifier" problems real.

Why synthetic data: entity resolution can only be measured when you know the right answer.
Because this script creates the people first and the messy copies second, every record
carries the id of the person it really belongs to. The matchers never look at that id; the
evaluation code uses it to count false merges and missed links.

Inputs:  none (everything comes from Faker and a fixed random seed).
Output: data/customers.csv  (true_entity_id / true_household_id are ONLY for evaluation,
                             never used to match)
        data/new_batch.csv  (new records arriving later, for the incremental MDM demo)

Run:     python data/generate_data.py   (also the first line of run_all.sh)
Slides:  5 (Synthetic data), 2 (One person, three systems), 20 (households in the spine).
"""

# random drives every noise decision; seeded below so each run is identical.
import random
# datetime is subclassed further down to freeze "today" for Faker.
from datetime import datetime
# Path builds file locations relative to this script, not the current directory.
from pathlib import Path

# pandas holds the generated rows and writes them to CSV.
import pandas as pd
# Faker produces realistic fake names, addresses and postcodes.
from faker import Faker
# The date_time provider module is patched below so dates do not depend on today or the OS.
import faker.providers.date_time as faker_date_time
from faker.providers.date_time import Provider as DateTimeProvider

# Experiment settings. Changing any of these changes every downstream number.
SEED = 42  # one seed for all random streams, so results are reproducible
N_ENTITIES = 4000  # number of real people in the initial population
N_NEW_BATCH = 400  # records in the later "incremental" feed used by 05_mdm.py
HOUSEHOLD_RATE = 0.10  # share of people who get a housemate

# Seed Python's random module (used for noise) and Faker (used for names/addresses).
random.seed(SEED)
# en_GB locale gives UK-style names, streets, cities and postcodes.
fake = Faker("en_GB")
Faker.seed(SEED)


def _rand_seconds(self, start_datetime: int, end_datetime: int) -> float:
    """Replacement for Faker's internal helper that picks a random timestamp in a range."""
    # Same guard Faker uses: an empty range is a programming error.
    if start_datetime > end_datetime:
        raise ValueError("empty range for _rand_seconds")
    # Always use uniform(), drawn from Faker's own seeded generator.
    return self.generator.random.uniform(start_datetime, end_datetime)


# Faker draws random dates with randint on Windows and uniform elsewhere, so the same seed
# gave different people on Windows. Use one rule everywhere.
DateTimeProvider._rand_seconds = _rand_seconds


class _FixedNow(datetime):
    """Faker dates are relative to today; pin "today" so every run makes the same data."""

    @classmethod
    def now(cls, tz=None):
        # A fixed date: ages and "last 3 years" timestamps no longer move with the calendar.
        return cls(2026, 10, 19, 12, 0, 0, tzinfo=tz)


# Make Faker's date provider use the frozen clock above.
faker_date_time.datetime = _FixedNow

# Formal first name -> nickname. Used to inject nickname noise ("Robert" becomes "Bob").
# common/standardise.py holds the reverse map so matchers can undo it.
NICKNAMES = {
    "robert": "bob",
    "william": "bill",
    "elizabeth": "liz",
    "margaret": "maggie",
    "james": "jim",
    "michael": "mike",
    "katherine": "kate",
    "thomas": "tom",
    "christopher": "chris",
    "daniel": "dan",
    "jennifer": "jen",
    "richard": "rich",
    "joseph": "joe",
    "samuel": "sam",
    "alexander": "alex",
    "matthew": "matt",
    "rebecca": "becky",
    "victoria": "vicky",
    "jonathan": "jon",
    "stephen": "steve",
}
# The three source systems a person can appear in (slide 2: one person, three systems).
SOURCES = ["CRM", "WEB", "BILLING"]
# Output folder: the data/ directory this script lives in.
OUT = Path(__file__).parent


def typo(s: str) -> str:
    """Apply one small character-level corruption to a value."""
    # Very short or empty values are left alone; a typo there would destroy them.
    if not s or len(s) < 4:
        return s
    # Pick an inner position (never the first or last character).
    i = random.randrange(1, len(s) - 1)
    # Choose one of four classic keyboard errors.
    op = random.choice(["swap", "drop", "dup", "sub"])
    if op == "swap":
        # Transposition: swap characters i and i+1 ("smith" -> "smtih").
        return s[:i] + s[i + 1] + s[i] + s[i + 2 :]
    if op == "drop":
        # Deletion: remove character i ("smith" -> "smth").
        return s[:i] + s[i + 1 :]
    if op == "dup":
        # Insertion: repeat character i ("smith" -> "smiith").
        return s[:i] + s[i] + s[i:]
    # Substitution: replace character i with a common letter ("smith" -> "snith").
    return s[:i] + random.choice("aeioulnrst") + s[i + 1 :]


def phone_format(p: str) -> str:
    """Render the same phone number in one of several source-style formats."""
    # Strip everything but digits so we start from the canonical number.
    digits = "".join(c for c in p if c.isdigit())
    # Each source system stores phones differently; pick one style at random.
    style = random.choice(["raw", "spaced", "intl", "dash"])
    if style == "raw":
        # 07123456789
        return digits
    if style == "spaced":
        # 07123 456789
        return f"{digits[:5]} {digits[5:]}"
    if style == "intl":
        # +44 7123456789 (international form drops the leading 0)
        return "+44 " + digits.lstrip("0")
    # 0712-345-6789
    return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"


def make_entity(eid: int) -> dict:
    """Create one clean person record that serves as the synthetic ground truth."""
    first = fake.first_name()
    # bias towards names that have nicknames, so nicknames actually show up
    if random.random() < 0.25:
        first = random.choice(list(NICKNAMES)).title()
    last = fake.last_name()
    # Adults only, aged 18 to 85 relative to the frozen "today".
    dob = fake.date_of_birth(minimum_age=18, maximum_age=85)
    # UK mobile: "07" followed by 9 random digits.
    mobile = "07" + "".join(random.choice("0123456789") for _ in range(9))
    # A handful of common UK email providers.
    domain = random.choice(
        ["gmail.com", "outlook.com", "yahoo.co.uk", "hotmail.co.uk", "btinternet.com"]
    )
    # first.last@domain, sometimes with a number (e.g. gareth.smith66@hotmail.co.uk).
    email = f"{first.lower()}.{last.lower()}{random.choice(['', str(random.randint(1, 99))])}@{domain}"
    # The clean "true" person. Every source record is a noisy copy of one of these.
    return {
        "true_entity_id": eid,  # answer key: which real person this is
        "first_name": first,
        "last_name": last,
        "dob": dob,
        "email": email,
        "phone": mobile,
        # Faker addresses can span lines; flatten to one line.
        "address": fake.street_address().replace("\n", ", "),
        "city": fake.city(),
        "postcode": fake.postcode(),
    }


def noisy_copy(ent: dict, source: str, rec_no: int) -> dict:
    """Create a source-system record with realistic field noise and omissions."""
    # Copy the clean person so the truth itself is never modified.
    r = dict(ent)
    r["source_system"] = source
    # Record id such as CRM-000123: unique across all systems because rec_no is global.
    r["source_record_id"] = f"{source}-{rec_no:06d}"
    # Last-update timestamp within the past 3 years; MDM survivorship uses it ("most recent").
    r["updated_at"] = fake.date_time_between(
        start_date="-3y", end_date="now"
    ).isoformat(timespec="seconds")
    first, last = r["first_name"], r["last_name"]

    # Name noise. Each line is an independent coin flip with its own probability.
    # 15%: use the nickname if this name has one ("Robert" -> "Bob").
    if random.random() < 0.15 and first.lower() in NICKNAMES:
        first = NICKNAMES[first.lower()].title()
    # 15%: typo in first name; 15%: typo in surname.
    if random.random() < 0.15:
        first = typo(first)
    if random.random() < 0.15:
        last = typo(last)
    # 3%: first and last name entered in the wrong boxes.
    if random.random() < 0.03:
        first, last = last, first
    # 10%: system stores names in upper case.
    if random.random() < 0.10:
        first, last = first.upper(), last.upper()
    r["first_name"], r["last_name"] = first, last

    dob = r["dob"]
    # 4%: day and month swapped (only possible when the day is a valid month, 1..12).
    if random.random() < 0.04 and dob.day <= 12:
        dob = dob.replace(day=dob.month, month=dob.day)  # US/UK format confusion
    # Store as ISO text, or missing 8% of the time.
    r["dob"] = dob.isoformat() if random.random() > 0.08 else None

    # Email noise: chained elif, so at most one of these happens.
    if random.random() < 0.25:
        # 25%: no email captured.
        r["email"] = None
    elif random.random() < 0.08:
        # Otherwise 8%: a typo in the address.
        r["email"] = typo(r["email"])
    elif random.random() < 0.10:
        # Otherwise 10%: upper-cased (standardise.clean_email lowercases it back).
        r["email"] = r["email"].upper()

    # Phone: 20% missing, otherwise rendered in a random source format.
    r["phone"] = None if random.random() < 0.20 else phone_format(r["phone"])

    if random.random() < 0.15:  # moved house
        # A completely new address: the old one is no evidence of a match any more.
        r["address"] = fake.street_address().replace("\n", ", ")
        r["city"] = fake.city()
        r["postcode"] = fake.postcode()
    elif random.random() < 0.20:
        # Same address, but with a typo and common abbreviations (Road -> Rd, Street -> St).
        r["address"] = typo(r["address"]).replace("Road", "Rd").replace("Street", "St")
    pc = r["postcode"]
    # Postcode formatting: 30% without the space, else 10% lower case, else unchanged.
    r["postcode"] = (
        pc.replace(" ", "")
        if random.random() < 0.3
        else pc.lower() if random.random() < 0.1 else pc
    )
    # Source-specific gaps: each system captures a different set of fields.
    if source == "WEB" and random.random() < 0.5:  # web form has no address
        r["address"] = None
    if source == "BILLING" and random.random() < 0.4:  # billing does not capture dob
        r["dob"] = None
    return r


def add_households(entities: list[dict], rng: random.Random) -> None:
    """Pair some people into households: shared address, often shared surname or email.

    Uses its own random generator so the person-level noise stream stays reproducible.
    """
    # By default everyone lives alone: household id derived from their own entity id.
    for e in entities:
        e["true_household_id"] = f"H{e['true_entity_id']:05d}"
    # Shuffle all people, then take consecutive pairs as (head, member).
    pool = list(range(len(entities)))
    rng.shuffle(pool)
    # 10% of people in households means 5% as many pairs as people.
    n_pairs = int(len(entities) * HOUSEHOLD_RATE / 2)
    for k in range(n_pairs):
        head, member = entities[pool[2 * k]], entities[pool[2 * k + 1]]
        # The member moves in: same address, city and postcode as the head.
        for f in ("address", "city", "postcode"):
            member[f] = head[f]
        member["true_household_id"] = head["true_household_id"]
        if rng.random() < 0.6:  # partner or adult child with the same surname
            member["last_name"] = head["last_name"]
            # Rebuild the member's email from the new surname, keeping their provider.
            local, domain = member["email"].split("@")
            member["email"] = f"{member['first_name'].lower()}.{head['last_name'].lower()}@{domain}"
        if rng.random() < 0.25:  # one family mailbox used by both people
            # A generic shared identifier (e.g. thesmiths@gmail.com). Two different people
            # with the same email is the trap that 04_graph_resolution.py flags.
            fam = f"the{head['last_name'].lower()}s@{head['email'].split('@')[1]}"
            head["email"] = member["email"] = fam


def main():
    # Generate extra ground-truth people so half of the later batch can be genuinely new.
    entities = [make_entity(i) for i in range(N_ENTITIES + N_NEW_BATCH)]
    # Separate RNG (seed 43) so adding households does not shift the noise stream above.
    add_households(entities, random.Random(SEED + 1))
    rows, rec_no = [], 0
    # Initial population: only the first N_ENTITIES people.
    for ent in entities[:N_ENTITIES]:
        # How many systems know this person: 1 (35%), 2 (40%) or 3 (25%).
        n_sources = random.choices([1, 2, 3], weights=[0.35, 0.40, 0.25])[0]
        # random.sample picks that many distinct systems.
        for src in random.sample(SOURCES, n_sources):
            copies = 2 if random.random() < 0.07 else 1  # duplicate inside same system
            for _ in range(copies):
                rec_no += 1
                rows.append(noisy_copy(ent, src, rec_no))

    # new batch: half are existing people arriving again, half are brand new people
    new_rows = []
    for i in range(N_NEW_BATCH):
        rec_no += 1
        # Alternate returning people and new people to make incremental matching measurable.
        ent = (
            # Even i: a random existing person (should attach to an existing customer).
            random.choice(entities[:N_ENTITIES])
            if i % 2 == 0
            # Odd i: one of the reserved extra people (should become a new customer).
            else entities[N_ENTITIES + i]
        )
        new_rows.append(noisy_copy(ent, random.choice(SOURCES), rec_no))

    # Column order of the output files; the last two are the evaluation answer keys.
    cols = [
        "source_record_id",
        "source_system",
        "first_name",
        "last_name",
        "dob",
        "email",
        "phone",
        "address",
        "city",
        "postcode",
        "updated_at",
        "true_entity_id",
        "true_household_id",
    ]
    df = (
        pd.DataFrame(rows)[cols]
        # sample(frac=1) shuffles all rows, so copies of one person are not next to each other.
        .sample(frac=1, random_state=SEED)
        # Renumber the index 0..n-1 after shuffling and discard the old order.
        .reset_index(drop=True)
    )
    df.to_csv(OUT / "customers.csv", index=False)
    pd.DataFrame(new_rows)[cols].to_csv(OUT / "new_batch.csv", index=False)
    # Summary lines: total records, distinct real people, and size of the new batch.
    print(f"customers.csv: {len(df)} records for {df.true_entity_id.nunique()} people")
    print(f"new_batch.csv: {len(new_rows)} records")
    # Count households that contain more than one distinct person in the initial data.
    # Fewer than the 220 created pairs, because pairs were drawn from all 4,400 people and
    # some housemates are among the 400 reserved for the new batch only.
    hh = df.groupby("true_household_id").true_entity_id.nunique()
    print(f"households with 2 people: {(hh > 1).sum()}")


if __name__ == "__main__":
    main()
