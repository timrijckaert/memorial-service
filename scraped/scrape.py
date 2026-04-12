"""Scrape heemkringhaaltert.be memorial card data into PERSON_SCHEMA JSON."""

import asyncio
import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

LOG_FILE = Path(__file__).parent / "scrape.log"

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
    tables = soup.find_all("table")
    if not tables:
        return []

    persons = []
    for table in tables:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 6:
                continue

            # Skip header rows (they use <strong> inside <td>)
            if cells[0].find("strong"):
                continue

            # Skip navigation rows (letter links like A, B, C -- no dates)
            if not re.search(r"\d{2}/\d{2}/\d{4}", cells[3].get_text()):
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

            # Use image filename as slug (unique), fall back to name-based slug
            broken_url = None
            if image_url and image_url.lower().endswith((".jpg", ".jpeg", ".png")):
                image_filename = image_url.rsplit("/", 1)[-1]
                slug = image_filename.rsplit(".", 1)[0].lower()
                image_file = image_filename
            else:
                slug = make_slug(last_name, first_name)
                image_file = None
                if image_url:
                    broken_url = image_url
                image_url = None

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
                    "image_file": image_file,
                },
                "slug": slug,
                "broken_url": broken_url,
            }
            persons.append(person)

    return persons



def write_person_json(person: dict, json_dir: Path) -> bool:
    """Write person dict to JSON file. Returns False if skipped (already exists)."""
    slug = person["slug"]
    out_file = json_dir / f"{slug}.json"

    if out_file.exists():
        return False

    # Strip internal fields before writing
    output = {k: v for k, v in person.items() if k not in ("slug", "broken_url")}
    out_file.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    return True


async def fetch_pages(client: httpx.AsyncClient) -> dict[str, str]:
    """Fetch all letter pages in parallel. Returns {letter: html}."""
    async def fetch_one(letter: str, page_id: int) -> tuple[str, str]:
        url = f"{BASE_URL}?page_id={page_id}"
        resp = await client.get(url)
        resp.raise_for_status()
        return letter, resp.text

    tasks = [fetch_one(letter, pid) for letter, pid in LETTER_PAGES.items()]
    results = await asyncio.gather(*tasks)
    return dict(results)


async def download_image(
    client: httpx.AsyncClient, image_url: str, dest: Path, person_name: str,
    logger: logging.Logger, retries: int = 3,
) -> bool:
    """Download image if dest doesn't exist. Retries on failure. Returns True if downloaded."""
    if dest.exists():
        return False
    for attempt in range(1, retries + 1):
        try:
            resp = await client.get(image_url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return True
        except (httpx.HTTPError, OSError) as e:
            if attempt < retries:
                await asyncio.sleep(2 * attempt)
            else:
                logger.error(f"Image failed for '{person_name}': {e} (url: {image_url})")
                return False
    return False


async def download_images(
    client: httpx.AsyncClient, persons: list[dict], images_dir: Path, logger: logging.Logger
) -> int:
    """Download all images in parallel. Returns count of newly downloaded."""
    tasks = []
    for person in persons:
        image_url = person["source"]["image_url"]
        image_file = person["source"]["image_file"]
        if not image_url or not image_file:
            continue
        dest = images_dir / image_file
        if dest.exists():
            continue
        p = person["person"]
        person_name = f"{p['last_name']} {p['first_name']}"
        tasks.append(download_image(client, image_url, dest, person_name, logger))

    if not tasks:
        return 0

    results = await asyncio.gather(*tasks)
    downloaded = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is False)
    if failed:
        print(f"  Warning: {failed} image download(s) failed (see {LOG_FILE.name})")
    return downloaded


async def run() -> None:
    """Main scraper entry point."""
    script_dir = Path(__file__).parent
    json_dir = script_dir / "json"
    images_dir = script_dir / "images"
    json_dir.mkdir(exist_ok=True)
    images_dir.mkdir(exist_ok=True)

    # Set up file logging
    logger = logging.getLogger("scraper")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(levelname)s  %(message)s"))
    logger.addHandler(handler)

    print("Fetching letter pages...")
    limits = httpx.Limits(max_connections=5, max_keepalive_connections=5)
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, limits=limits) as client:
        pages = await fetch_pages(client)
        print(f"  Fetched {len(pages)} pages")

        # Parse all pages
        all_persons = []
        for letter, html in sorted(pages.items()):
            page_url = f"{BASE_URL}?page_id={LETTER_PAGES[letter]}"
            persons = parse_page(html, page_url)
            all_persons.extend(persons)
        print(f"  Found {len(all_persons)} persons total")

        # Log broken image URLs
        for person in all_persons:
            if person.get("broken_url"):
                p = person["person"]
                logger.error(
                    f"Broken image link for '{p['last_name']} {p['first_name']}': "
                    f"{person['broken_url']}"
                )

        # Write JSON files (fall back to name-based slug on collision)
        new_count = 0
        skip_count = 0
        for person in all_persons:
            if write_person_json(person, json_dir):
                new_count += 1
            elif not (json_dir / f"{person['slug']}.json").exists():
                # Shouldn't happen -- file didn't exist but write returned False
                skip_count += 1
            else:
                # Slug collision: different person shares same image URL on the website
                p = person["person"]
                name = f"{p['last_name']} {p['first_name']}"
                fallback = make_slug(p["last_name"], p["first_name"])
                logger.warning(
                    f"Slug collision for '{name}': {person['slug']} already exists, "
                    f"using fallback '{fallback}'"
                )
                person["slug"] = fallback
                if write_person_json(person, json_dir):
                    new_count += 1
                else:
                    skip_count += 1

        print(f"  JSON: {new_count} new, {skip_count} skipped (existing)")

        # Download images
        print("Downloading images...")
        img_count = await download_images(client, all_persons, images_dir, logger)
        print(f"  Images: {img_count} downloaded")

    print(f"Done! (log: {LOG_FILE.name})")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
