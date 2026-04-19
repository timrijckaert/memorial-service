# src/naming.py
"""Derive canonical filenames from extracted card data."""

_DUTCH_MONTHS = {
    1: "januari", 2: "februari", 3: "maart", 4: "april",
    5: "mei", 6: "juni", 7: "juli", 8: "augustus",
    9: "september", 10: "oktober", 11: "november", 12: "december",
}


def format_dutch_date(iso_date: str) -> str:
    """Convert ISO date 'YYYY-MM-DD' to 'DD month YYYY' with Dutch month names."""
    year, month, day = iso_date.split("-")
    return f"{day} {_DUTCH_MONTHS[int(month)]} {year}"


def derive_filename(card: dict) -> str:
    """Build a canonical filename from card data.

    Convention: Surname Firstname Locality bidprentje DD month YYYY
    Missing fields are omitted. Always includes 'bidprentje'.
    """
    person = card.get("person", {})
    parts = []

    if person.get("last_name"):
        parts.append(person["last_name"])
    if person.get("first_name"):
        parts.append(person["first_name"])
    if person.get("locality"):
        parts.append(person["locality"])

    parts.append("bidprentje")

    if person.get("death_date"):
        parts.append(format_dutch_date(person["death_date"]))

    return " ".join(parts)
