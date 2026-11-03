"""Invented names and product descriptions.

Company names are built from made-up word stems, and street and town names
are invented. Phone numbers use the 555-01xx range reserved for fiction, and
emails use the reserved ``.example`` domain. No real company or personal data.
"""

import random

STEMS = [
    "Lumenfold", "Corvane", "Quillmere", "Tarnwick", "Velloran", "Brisketta",
    "Ombrelux", "Fenwarden", "Halcyra", "Druvelle", "Quorvane", "Pellucia",
    "Zantheon", "Kestrove", "Ambervault", "Solvane", "Thistlecrane", "Irongale",
    "Nettlebrook", "Vantorel", "Crestmoor", "Wyncastle", "Orlavant", "Saffrel",
]  # fmt: skip
VENDOR_SUFFIXES = {
    "US": ["Supplies Inc.", "Works LLC", "Trading Co.", "Industrial Inc.", "Labs LLC"],
    "UK": ["Supplies Ltd", "Trading Ltd", "Works Ltd", "& Partners Ltd"],
    "EU": ["GmbH", "Handel GmbH", "B.V.", "S.A.R.L.", "AG"],
    "IN": ["Pvt. Ltd.", "Traders Pvt. Ltd.", "Enterprises"],
    "JP": ["K.K.", "Trading K.K."],
}
CLIENT_SUFFIXES = ["Studio", "Design Group", "Analytics", "Bakery", "Logistics", "Clinic",
                   "Architects", "Media", "Consulting", "Robotics"]  # fmt: skip

STREETS = ["Marrow Lane", "Quillon Street", "Ashveil Road", "Tamberly Avenue",
           "Corriden Way", "Fenstock Drive", "Halloway Court", "Brindle Row"]  # fmt: skip
TOWNS = ["Ostervale", "Kelmsby", "Durrenford", "Vasselburg", "Pinmarsh", "Calloway Bay",
         "Rendhurst", "Saltmere"]  # fmt: skip

PRODUCTS = [
    "LED desk lamp", "Ergonomic office chair", "Wireless keyboard", "USB-C docking station",
    "A4 copy paper (box of 5 reams)", "Whiteboard markers (pack of 12)", "Monitor arm",
    "Laser toner cartridge", "Network switch, 8-port", "Label printer tape",
    "Standing desk frame", "Acoustic wall panel", "Cable management kit", "Webcam 1080p",
]  # fmt: skip
SERVICES = [
    "Website maintenance", "On-site IT support", "Logo design revisions",
    "Bookkeeping services", "Data migration consulting", "Copywriting",
    "Photography session", "Server monitoring", "Training workshop", "Translation services",
]  # fmt: skip


def company(rng: random.Random, region: str, client: bool = False, avoid: str = "") -> str:
    stem = rng.choice([s for s in STEMS if not avoid.startswith(s)])
    suffix = rng.choice(CLIENT_SUFFIXES if client else VENDOR_SUFFIXES[region])
    return f"{stem} {suffix}"


def address(rng: random.Random, region: str) -> list[str]:
    number = rng.randint(2, 980)
    street = rng.choice(STREETS)
    town = rng.choice(TOWNS)
    if region == "US":
        return [f"{number} {street}", f"{town}, ST {rng.randint(10000, 99999)}"]
    if region == "UK":
        return [f"{number} {street}", f"{town} QX{rng.randint(1, 9)} {rng.randint(1, 9)}ZZ"]
    if region == "IN":
        return [f"{number}, {street}", f"{town} - {rng.randint(100000, 999999)}"]
    if region == "JP":
        return [f"{number}-{rng.randint(1, 9)} {street}", f"{town} {rng.randint(100, 999)}-0000"]
    return [f"{street} {number}", f"{rng.randint(10000, 99999)} {town}"]


def phone(rng: random.Random) -> str:
    return f"(555) 555-01{rng.randint(0, 99):02d}"


def email(name: str) -> str:
    local = name.split()[0].lower()
    return f"billing@{local}.example"
