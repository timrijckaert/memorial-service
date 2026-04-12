"""Scrape heemkringhaaltert.be memorial card data into PERSON_SCHEMA JSON."""

import re
import unicodedata
from datetime import datetime

from bs4 import BeautifulSoup

BASE_URL = "https://heemkringhaaltert.be/"

# Two-word particles must be checked before single-word ones
_PARTICLES_MULTI = {"van de", "van den", "van der"}
_PARTICLES_SINGLE = {"van", "de", "den", "der", "te", "ten", "ter", "'t"}


def split_name(full_name: str) -> tuple[str, str]:
    """Split 'LastName FirstName' using tussenvoegsel-aware logic.

    Returns (last_name, first_name).
    """
    words = full_name.split()
    i = 0

    while i < len(words) - 1:  # Must leave at least 1 word for surname core
        # Try two-word particle first
        if i + 1 < len(words) - 1:
            pair = f"{words[i]} {words[i+1]}".lower()
            if pair in _PARTICLES_MULTI:
                i += 2
                continue

        # Try single-word particle
        if words[i].lower() in _PARTICLES_SINGLE:
            i += 1
            continue

        break

    # Next word after particles is the surname core
    surname_end = i + 1
    last_name = " ".join(words[:surname_end])
    first_name = " ".join(words[surname_end:])
    return last_name, first_name

def convert_date(date_str: str) -> str | None:
    """Convert DD/MM/YYYY to YYYY-MM-DD. Returns None for empty/invalid."""
    date_str = date_str.strip()
    if not date_str or date_str == "—":
        return None
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def make_slug(last_name: str, first_name: str) -> str:
    """Create a filename-safe slug from name parts.

    Normalizes unicode to ASCII (Aloïs -> Alois), lowercases,
    replaces non-alphanum with hyphens, collapses multiple hyphens.
    """
    full = f"{last_name} {first_name}"
    # Normalize unicode to ASCII
    nfkd = unicodedata.normalize("NFKD", full)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    # Lowercase, replace non-alphanum with hyphens, collapse and strip
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_str.lower()).strip("-")
    return slug


LETTER_PAGES = {
    "A": 9498, "B": 9516, "C": 9560, "D": 9580, "D'h": 9706,
    "E": 9715, "F": 9726, "G": 9741, "H": 9758, "I": 9784,
    "J": 9794, "K": 9802, "L": 9809, "M": 9825, "N": 9843,
    "O": 9857, "P": 9863, "Q": 9934, "R": 9871, "S": 9886,
    "T": 9908, "U": 9919, "V": 5695, "Ve": 9953, "W": 9924,
    "X": 9938, "Y": 9942, "Z": 9948,
}


def parse_page(html: str, page_url: str) -> list[dict]:
    """Parse a letter page's HTML table into a list of person dicts."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return []

    persons = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        # Extract name and image link
        name_cell = cells[0]
        link = name_cell.find("a")
        full_name = name_cell.get_text(strip=True)
        image_url = link["href"] if link and link.has_attr("href") else None

        # Extract other fields
        eega = cells[1].get_text(strip=True)
        birth_place = cells[2].get_text(strip=True)
        birth_date_raw = cells[3].get_text(strip=True)
        death_place = cells[4].get_text(strip=True)
        death_date_raw = cells[5].get_text(strip=True)

        # Transform
        last_name, first_name = split_name(full_name)
        spouses = [eega] if eega and eega != "—" else []

        slug = make_slug(last_name, first_name)

        person = {
            "person": {
                "first_name": first_name,
                "last_name": last_name,
                "birth_date": convert_date(birth_date_raw),
                "birth_place": birth_place or None,
                "death_date": convert_date(death_date_raw),
                "death_place": death_place or None,
                "age_at_death": None,
                "spouses": spouses,
            },
            "notes": [],
            "source": {
                "url": page_url,
                "image_url": image_url,
                "image_file": f"{slug}.jpg" if image_url else None,
            },
            "slug": slug,
        }
        persons.append(person)

    return persons


def deduplicate_slugs(persons: list[dict]) -> None:
    """Append -2, -3, etc. to duplicate slugs. Mutates in place."""
    seen: dict[str, int] = {}
    for person in persons:
        slug = person["slug"]
        if slug in seen:
            seen[slug] += 1
            new_slug = f"{slug}-{seen[slug]}"
            person["slug"] = new_slug
            # Update image_file to match
            if person["source"]["image_file"]:
                person["source"]["image_file"] = f"{new_slug}.jpg"
        else:
            seen[slug] = 1
