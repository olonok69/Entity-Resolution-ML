"""Generate synthetic UK customer records spread over 3 source systems, with known truth.

Each real person ("entity") appears in 1..3 systems (CRM, WEB, BILLING) and sometimes twice
in the same system. Every copy gets realistic noise: typos, nicknames, swapped names,
missing values, different phone / postcode formats, moved address, DOB day-month swap.
About 10% of people also live with another person (a household): same address, often the
same surname and sometimes a shared family email. That is what makes the hierarchy and
"generic identifier" problems real.

Output: data/customers.csv  (true_entity_id / true_household_id are ONLY for evaluation,
                             never used to match)
        data/new_batch.csv  (new records arriving later, for the incremental MDM demo)
"""

import random
from pathlib import Path

import pandas as pd
from faker import Faker
from faker.providers.date_time import Provider as DateTimeProvider

SEED = 42
N_ENTITIES = 4000
N_NEW_BATCH = 400
HOUSEHOLD_RATE = 0.10  # share of people who get a housemate

random.seed(SEED)
fake = Faker("en_GB")
Faker.seed(SEED)


def _rand_seconds(self, start_datetime: int, end_datetime: int) -> float:
    if start_datetime > end_datetime:
        raise ValueError("empty range for _rand_seconds")
    return self.generator.random.uniform(start_datetime, end_datetime)


# Faker draws random dates with randint on Windows and uniform elsewhere, so the same seed
# gave different people on Windows. Use one rule everywhere so the data matches the docs.
DateTimeProvider._rand_seconds = _rand_seconds

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
SOURCES = ["CRM", "WEB", "BILLING"]
OUT = Path(__file__).parent


def typo(s: str) -> str:
    """Apply one small character-level corruption to a value."""
    if not s or len(s) < 4:
        return s
    i = random.randrange(1, len(s) - 1)
    op = random.choice(["swap", "drop", "dup", "sub"])
    if op == "swap":
        return s[:i] + s[i + 1] + s[i] + s[i + 2 :]
    if op == "drop":
        return s[:i] + s[i + 1 :]
    if op == "dup":
        return s[:i] + s[i] + s[i:]
    return s[:i] + random.choice("aeioulnrst") + s[i + 1 :]


def phone_format(p: str) -> str:
    """Render the same phone number in one of several source-style formats."""
    digits = "".join(c for c in p if c.isdigit())
    style = random.choice(["raw", "spaced", "intl", "dash"])
    if style == "raw":
        return digits
    if style == "spaced":
        return f"{digits[:5]} {digits[5:]}"
    if style == "intl":
        return "+44 " + digits.lstrip("0")
    return f"{digits[:4]}-{digits[4:7]}-{digits[7:]}"


def make_entity(eid: int) -> dict:
    """Create one clean person record that serves as the synthetic ground truth."""
    first = fake.first_name()
    # bias towards names that have nicknames, so nicknames actually show up
    if random.random() < 0.25:
        first = random.choice(list(NICKNAMES)).title()
    last = fake.last_name()
    dob = fake.date_of_birth(minimum_age=18, maximum_age=85)
    mobile = "07" + "".join(random.choice("0123456789") for _ in range(9))
    domain = random.choice(
        ["gmail.com", "outlook.com", "yahoo.co.uk", "hotmail.co.uk", "btinternet.com"]
    )
    email = f"{first.lower()}.{last.lower()}{random.choice(['', str(random.randint(1, 99))])}@{domain}"
    return {
        "true_entity_id": eid,
        "first_name": first,
        "last_name": last,
        "dob": dob,
        "email": email,
        "phone": mobile,
        "address": fake.street_address().replace("\n", ", "),
        "city": fake.city(),
        "postcode": fake.postcode(),
    }


def noisy_copy(ent: dict, source: str, rec_no: int) -> dict:
    """Create a source-system record with realistic field noise and omissions."""
    r = dict(ent)
    r["source_system"] = source
    r["source_record_id"] = f"{source}-{rec_no:06d}"
    r["updated_at"] = fake.date_time_between(
        start_date="-3y", end_date="now"
    ).isoformat(timespec="seconds")
    first, last = r["first_name"], r["last_name"]

    if random.random() < 0.15 and first.lower() in NICKNAMES:
        first = NICKNAMES[first.lower()].title()
    if random.random() < 0.15:
        first = typo(first)
    if random.random() < 0.15:
        last = typo(last)
    if random.random() < 0.03:
        first, last = last, first
    if random.random() < 0.10:
        first, last = first.upper(), last.upper()
    r["first_name"], r["last_name"] = first, last

    dob = r["dob"]
    if random.random() < 0.04 and dob.day <= 12:
        dob = dob.replace(day=dob.month, month=dob.day)  # US/UK format confusion
    r["dob"] = dob.isoformat() if random.random() > 0.08 else None

    if random.random() < 0.25:
        r["email"] = None
    elif random.random() < 0.08:
        r["email"] = typo(r["email"])
    elif random.random() < 0.10:
        r["email"] = r["email"].upper()

    r["phone"] = None if random.random() < 0.20 else phone_format(r["phone"])

    if random.random() < 0.15:  # moved house
        r["address"] = fake.street_address().replace("\n", ", ")
        r["city"] = fake.city()
        r["postcode"] = fake.postcode()
    elif random.random() < 0.20:
        r["address"] = typo(r["address"]).replace("Road", "Rd").replace("Street", "St")
    pc = r["postcode"]
    r["postcode"] = (
        pc.replace(" ", "")
        if random.random() < 0.3
        else pc.lower() if random.random() < 0.1 else pc
    )
    if source == "WEB" and random.random() < 0.5:  # web form has no address
        r["address"] = None
    if source == "BILLING" and random.random() < 0.4:  # billing does not capture dob
        r["dob"] = None
    return r


def add_households(entities: list[dict], rng: random.Random) -> None:
    """Pair some people into households: shared address, often shared surname or email.

    Uses its own random generator so the person-level noise stream stays reproducible.
    """
    for e in entities:
        e["true_household_id"] = f"H{e['true_entity_id']:05d}"
    pool = list(range(len(entities)))
    rng.shuffle(pool)
    n_pairs = int(len(entities) * HOUSEHOLD_RATE / 2)
    for k in range(n_pairs):
        head, member = entities[pool[2 * k]], entities[pool[2 * k + 1]]
        for f in ("address", "city", "postcode"):
            member[f] = head[f]
        member["true_household_id"] = head["true_household_id"]
        if rng.random() < 0.6:  # partner or adult child with the same surname
            member["last_name"] = head["last_name"]
            local, domain = member["email"].split("@")
            member["email"] = f"{member['first_name'].lower()}.{head['last_name'].lower()}@{domain}"
        if rng.random() < 0.25:  # one family mailbox used by both people
            fam = f"the{head['last_name'].lower()}s@{head['email'].split('@')[1]}"
            head["email"] = member["email"] = fam


def main():
    # Generate extra ground-truth people so half of the later batch can be genuinely new.
    entities = [make_entity(i) for i in range(N_ENTITIES + N_NEW_BATCH)]
    add_households(entities, random.Random(SEED + 1))
    rows, rec_no = [], 0
    for ent in entities[:N_ENTITIES]:
        n_sources = random.choices([1, 2, 3], weights=[0.35, 0.40, 0.25])[0]
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
            random.choice(entities[:N_ENTITIES])
            if i % 2 == 0
            else entities[N_ENTITIES + i]
        )
        new_rows.append(noisy_copy(ent, random.choice(SOURCES), rec_no))

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
        .sample(frac=1, random_state=SEED)
        .reset_index(drop=True)
    )
    df.to_csv(OUT / "customers.csv", index=False)
    pd.DataFrame(new_rows)[cols].to_csv(OUT / "new_batch.csv", index=False)
    print(f"customers.csv: {len(df)} records for {df.true_entity_id.nunique()} people")
    print(f"new_batch.csv: {len(new_rows)} records")
    hh = df.groupby("true_household_id").true_entity_id.nunique()
    print(f"households with 2 people: {(hh > 1).sum()}")


if __name__ == "__main__":
    main()
