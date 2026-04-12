# Heemkring Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrape all biographical data and memorial card images from heemkringhaaltert.be into PERSON_SCHEMA JSON files.

**Architecture:** Single async Python script (`scraped/scrape.py`) using httpx for parallel HTTP + BeautifulSoup for HTML parsing. Self-contained sub-project with own `requirements.txt`. Idempotent — skips already-scraped persons.

**Tech Stack:** Python 3, httpx (async HTTP), beautifulsoup4 + lxml (HTML parsing), pytest (testing)

**Spec:** `docs/superpowers/specs/2026-04-12-heemkring-scraper-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `scraped/requirements.txt` | Dependencies: httpx, beautifulsoup4, lxml |
| `scraped/scrape.py` | Entire scraper: parsing, transforms, fetching, writing |
| `scraped/test_scrape.py` | All tests (fixtures inline) |

---

### Task 1: Project Setup

**Files:**
- Create: `scraped/requirements.txt`
- Create: `scraped/scrape.py` (empty module)
- Create: `scraped/test_scrape.py` (empty module)

- [ ] **Step 1: Create requirements.txt**

```
httpx
beautifulsoup4
lxml
pytest
```

- [ ] **Step 2: Create empty scrape.py with the hardcoded letter pages constant**

```python
"""Scrape heemkringhaaltert.be memorial card data into PERSON_SCHEMA JSON."""

BASE_URL = "https://heemkringhaaltert.be/"

LETTER_PAGES = {
    "A": 9498, "B": 9516, "C": 9560, "D": 9580, "D'h": 9706,
    "E": 9715, "F": 9726, "G": 9741, "H": 9758, "I": 9784,
    "J": 9794, "K": 9802, "L": 9809, "M": 9825, "N": 9843,
    "O": 9857, "P": 9863, "Q": 9934, "R": 9871, "S": 9886,
    "T": 9908, "U": 9919, "V": 5695, "Ve": 9953, "W": 9924,
    "X": 9938, "Y": 9942, "Z": 9948,
}
```

- [ ] **Step 3: Create empty test file**

```python
"""Tests for heemkring scraper."""

from scrape import LETTER_PAGES


def test_letter_pages_has_28_entries():
    assert len(LETTER_PAGES) == 28
```

- [ ] **Step 4: Install dependencies and run test**

```bash
cd scraped && python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m pytest test_scrape.py -v
```

Expected: PASS — `test_letter_pages_has_28_entries`

- [ ] **Step 5: Commit**

```bash
git add scraped/requirements.txt scraped/scrape.py scraped/test_scrape.py
git commit -m "feat(scraper): scaffold project with dependencies and letter page mapping"
```

---

### Task 2: Name Splitting (Tussenvoegsel Logic)

**Files:**
- Modify: `scraped/scrape.py`
- Modify: `scraped/test_scrape.py`

- [ ] **Step 1: Write failing tests**

Add to `test_scrape.py`:

```python
import pytest
from scrape import split_name


@pytest.mark.parametrize("full_name, expected_last, expected_first", [
    ("Ackerman Alina", "Ackerman", "Alina"),
    ("Van De Smet Maria", "Van De Smet", "Maria"),
    ("De Smet Joseph", "De Smet", "Joseph"),
    ("Van Den Berg Anna Maria", "Van Den Berg", "Anna Maria"),
    ("'t Jolle Pierre", "'t Jolle", "Pierre"),
    ("Janssens Maria Theresia", "Janssens", "Maria Theresia"),
    ("Van Der Linden Jan", "Van Der Linden", "Jan"),
    ("Te Boekhorst Hendrik", "Te Boekhorst", "Hendrik"),
])
def test_split_name(full_name, expected_last, expected_first):
    last, first = split_name(full_name)
    assert last == expected_last
    assert first == expected_first
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd scraped && .venv/bin/python -m pytest test_scrape.py::test_split_name -v
```

Expected: FAIL — `ImportError: cannot import name 'split_name'`

- [ ] **Step 3: Implement split_name**

Add to `scrape.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd scraped && .venv/bin/python -m pytest test_scrape.py::test_split_name -v
```

Expected: All 8 parametrized cases PASS

- [ ] **Step 5: Commit**

```bash
git add scraped/scrape.py scraped/test_scrape.py
git commit -m "feat(scraper): add tussenvoegsel-aware name splitting"
```

---

### Task 3: Date Conversion and Slug Generation

**Files:**
- Modify: `scraped/scrape.py`
- Modify: `scraped/test_scrape.py`

- [ ] **Step 1: Write failing tests for date conversion**

Add to `test_scrape.py`:

```python
from scrape import convert_date, make_slug


@pytest.mark.parametrize("input_date, expected", [
    ("15/11/1902", "1902-11-15"),
    ("08/08/1911", "1911-08-08"),
    ("01/01/2000", "2000-01-01"),
    ("", None),
    ("—", None),
    ("invalid", None),
])
def test_convert_date(input_date, expected):
    assert convert_date(input_date) == expected
```

- [ ] **Step 2: Write failing tests for slug generation**

Add to `test_scrape.py`:

```python
@pytest.mark.parametrize("last, first, expected", [
    ("Ackerman", "Alina", "ackerman-alina"),
    ("Van De Smet", "Maria", "van-de-smet-maria"),
    ("Janssens", "Aloïs", "janssens-alois"),
    ("D'Hondt", "Pierre", "d-hondt-pierre"),
])
def test_make_slug(last, first, expected):
    assert make_slug(last, first) == expected
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd scraped && .venv/bin/python -m pytest test_scrape.py -k "test_convert_date or test_make_slug" -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 4: Implement convert_date and make_slug**

Add to `scrape.py`:

```python
import re
import unicodedata
from datetime import datetime


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

    Normalizes unicode to ASCII, lowercases, replaces non-alphanum with hyphens.
    """
    full = f"{last_name} {first_name}"
    # Normalize unicode to ASCII (Aloïs -> Alois)
    nfkd = unicodedata.normalize("NFKD", full)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    # Lowercase, replace non-alphanum with hyphens, collapse multiple hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_str.lower()).strip("-")
    return slug
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd scraped && .venv/bin/python -m pytest test_scrape.py -k "test_convert_date or test_make_slug" -v
```

Expected: All 10 cases PASS

- [ ] **Step 6: Commit**

```bash
git add scraped/scrape.py scraped/test_scrape.py
git commit -m "feat(scraper): add date conversion and slug generation"
```

---

### Task 4: HTML Row Parsing

**Files:**
- Modify: `scraped/scrape.py`
- Modify: `scraped/test_scrape.py`

- [ ] **Step 1: Write failing test with HTML fixture**

Add to `test_scrape.py`:

```python
from scrape import parse_page

FIXTURE_HTML = """
<table>
<thead>
<tr><th>Naam</th><th>Eega</th><th>Geboren te</th><th>Geboren op</th><th>Overleden te</th><th>Overleden op</th></tr>
</thead>
<tbody>
<tr>
  <td><a href="https://heemkringhaaltert.be/wp-content/uploads/2025/12/Ackerman-Alina.jpg">Ackerman Alina</a></td>
  <td>Boone Pierre</td>
  <td>Everberg</td>
  <td>15/11/1902</td>
  <td>Haaltert</td>
  <td>16/12/1966</td>
</tr>
<tr>
  <td><a href="https://heemkringhaaltert.be/wp-content/uploads/2025/11/Allaer-Alois.jpg">Allaer Aloïs</a></td>
  <td>—</td>
  <td>Denderhoutem</td>
  <td>25/09/1866</td>
  <td>Denderhoutem</td>
  <td>08/02/1925</td>
</tr>
<tr>
  <td><a href="https://heemkringhaaltert.be/wp-content/uploads/2026/02/Van-De-Smet-Maria.jpg">Van De Smet Maria</a></td>
  <td>Janssens Karel</td>
  <td>Haaltert</td>
  <td>01/03/1910</td>
  <td>Aalst</td>
  <td>22/07/1985</td>
</tr>
</tbody>
</table>
"""


def test_parse_page_extracts_persons():
    persons = parse_page(FIXTURE_HTML, "https://heemkringhaaltert.be/?page_id=9498")
    assert len(persons) == 3

    p1 = persons[0]
    assert p1["person"]["last_name"] == "Ackerman"
    assert p1["person"]["first_name"] == "Alina"
    assert p1["person"]["birth_date"] == "1902-11-15"
    assert p1["person"]["birth_place"] == "Everberg"
    assert p1["person"]["death_date"] == "1966-12-16"
    assert p1["person"]["death_place"] == "Haaltert"
    assert p1["person"]["age_at_death"] is None
    assert p1["person"]["spouses"] == ["Boone Pierre"]
    assert p1["source"]["image_url"] == "https://heemkringhaaltert.be/wp-content/uploads/2025/12/Ackerman-Alina.jpg"
    assert p1["slug"] == "ackerman-alina"


def test_parse_page_empty_spouse():
    persons = parse_page(FIXTURE_HTML, "https://heemkringhaaltert.be/?page_id=9498")
    p2 = persons[1]
    assert p2["person"]["spouses"] == []
    assert p2["person"]["first_name"] == "Aloïs"


def test_parse_page_tussenvoegsel_name():
    persons = parse_page(FIXTURE_HTML, "https://heemkringhaaltert.be/?page_id=9498")
    p3 = persons[2]
    assert p3["person"]["last_name"] == "Van De Smet"
    assert p3["person"]["first_name"] == "Maria"
    assert p3["slug"] == "van-de-smet-maria"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd scraped && .venv/bin/python -m pytest test_scrape.py -k "test_parse_page" -v
```

Expected: FAIL — `ImportError: cannot import name 'parse_page'`

- [ ] **Step 3: Implement parse_page**

Add to `scrape.py`:

```python
from bs4 import BeautifulSoup


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
            "slug": slug,  # Used internally for filenames, stripped before writing
        }
        persons.append(person)

    return persons
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd scraped && .venv/bin/python -m pytest test_scrape.py -k "test_parse_page" -v
```

Expected: All 3 parse tests PASS

- [ ] **Step 5: Commit**

```bash
git add scraped/scrape.py scraped/test_scrape.py
git commit -m "feat(scraper): add HTML table parsing with field transformation"
```

---

### Task 5: Duplicate Slug Handling

**Files:**
- Modify: `scraped/scrape.py`
- Modify: `scraped/test_scrape.py`

- [ ] **Step 1: Write failing test**

Add to `test_scrape.py`:

```python
from scrape import deduplicate_slugs


def test_deduplicate_slugs():
    persons = [
        {"slug": "de-smet-maria", "person": {"last_name": "De Smet", "first_name": "Maria"}},
        {"slug": "janssens-karel", "person": {"last_name": "Janssens", "first_name": "Karel"}},
        {"slug": "de-smet-maria", "person": {"last_name": "De Smet", "first_name": "Maria"}},
        {"slug": "de-smet-maria", "person": {"last_name": "De Smet", "first_name": "Maria"}},
    ]
    deduplicate_slugs(persons)
    slugs = [p["slug"] for p in persons]
    assert slugs == ["de-smet-maria", "janssens-karel", "de-smet-maria-2", "de-smet-maria-3"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd scraped && .venv/bin/python -m pytest test_scrape.py::test_deduplicate_slugs -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement deduplicate_slugs**

Add to `scrape.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd scraped && .venv/bin/python -m pytest test_scrape.py::test_deduplicate_slugs -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scraped/scrape.py scraped/test_scrape.py
git commit -m "feat(scraper): handle duplicate person slugs"
```

---

### Task 6: Async Fetching, Writing, and Main Entry Point

**Files:**
- Modify: `scraped/scrape.py`
- Modify: `scraped/test_scrape.py`

- [ ] **Step 1: Write failing test for write_person_json**

Add to `test_scrape.py`:

```python
import json
from pathlib import Path
from scrape import write_person_json


def test_write_person_json(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    person = {
        "person": {
            "first_name": "Alina",
            "last_name": "Ackerman",
            "birth_date": "1902-11-15",
            "birth_place": "Everberg",
            "death_date": "1966-12-16",
            "death_place": "Haaltert",
            "age_at_death": None,
            "spouses": ["Boone Pierre"],
        },
        "notes": [],
        "source": {
            "url": "https://heemkringhaaltert.be/?page_id=9498",
            "image_url": "https://example.com/image.jpg",
            "image_file": "ackerman-alina.jpg",
        },
        "slug": "ackerman-alina",
    }

    write_person_json(person, json_dir)

    out_file = json_dir / "ackerman-alina.json"
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert data["person"]["first_name"] == "Alina"
    # slug should be stripped from output
    assert "slug" not in data


def test_write_person_json_skips_existing(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir()

    person = {
        "person": {"first_name": "Alina", "last_name": "Ackerman",
                    "birth_date": None, "birth_place": None,
                    "death_date": None, "death_place": None,
                    "age_at_death": None, "spouses": []},
        "notes": [],
        "source": {"url": "", "image_url": None, "image_file": None},
        "slug": "ackerman-alina",
    }

    # Pre-create file
    (json_dir / "ackerman-alina.json").write_text('{"existing": true}')

    written = write_person_json(person, json_dir)
    assert written is False
    # Should not overwrite
    data = json.loads((json_dir / "ackerman-alina.json").read_text())
    assert data == {"existing": True}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd scraped && .venv/bin/python -m pytest test_scrape.py -k "test_write_person" -v
```

Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement write_person_json**

Add to `scrape.py`:

```python
import json
from pathlib import Path


def write_person_json(person: dict, json_dir: Path) -> bool:
    """Write person dict to JSON file. Returns False if skipped (already exists)."""
    slug = person["slug"]
    out_file = json_dir / f"{slug}.json"

    if out_file.exists():
        return False

    # Strip internal slug field before writing
    output = {k: v for k, v in person.items() if k != "slug"}
    out_file.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd scraped && .venv/bin/python -m pytest test_scrape.py -k "test_write_person" -v
```

Expected: Both PASS

- [ ] **Step 5: Implement async fetch_pages, download_images, and main**

Add to `scrape.py`:

```python
import asyncio
import httpx


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


async def download_image(client: httpx.AsyncClient, image_url: str, dest: Path) -> bool:
    """Download image if dest doesn't exist. Returns True if downloaded."""
    if dest.exists():
        return False
    resp = await client.get(image_url)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return True


async def download_images(client: httpx.AsyncClient, persons: list[dict], images_dir: Path) -> int:
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
        tasks.append(download_image(client, image_url, dest))

    if not tasks:
        return 0

    results = await asyncio.gather(*tasks, return_exceptions=True)
    downloaded = sum(1 for r in results if r is True)
    errors = sum(1 for r in results if isinstance(r, Exception))
    if errors:
        print(f"  Warning: {errors} image download(s) failed")
    return downloaded


async def run() -> None:
    """Main scraper entry point."""
    script_dir = Path(__file__).parent
    json_dir = script_dir / "json"
    images_dir = script_dir / "images"
    json_dir.mkdir(exist_ok=True)
    images_dir.mkdir(exist_ok=True)

    print("Fetching letter pages...")
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        pages = await fetch_pages(client)
        print(f"  Fetched {len(pages)} pages")

        # Parse all pages
        all_persons = []
        for letter, html in sorted(pages.items()):
            page_url = f"{BASE_URL}?page_id={LETTER_PAGES[letter]}"
            persons = parse_page(html, page_url)
            all_persons.extend(persons)
        print(f"  Found {len(all_persons)} persons total")

        # Deduplicate slugs
        deduplicate_slugs(all_persons)

        # Write JSON files
        new_count = 0
        skip_count = 0
        for person in all_persons:
            if write_person_json(person, json_dir):
                new_count += 1
            else:
                skip_count += 1

        print(f"  JSON: {new_count} new, {skip_count} skipped (existing)")

        # Download images
        print("Downloading images...")
        img_count = await download_images(client, all_persons, images_dir)
        print(f"  Images: {img_count} downloaded")

    print("Done!")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run all tests**

```bash
cd scraped && .venv/bin/python -m pytest test_scrape.py -v
```

Expected: All tests PASS (name splitting, date conversion, slug generation, parse page, dedup, write JSON)

- [ ] **Step 7: Commit**

```bash
git add scraped/scrape.py scraped/test_scrape.py
git commit -m "feat(scraper): add async fetching, image download, and main entry point"
```

---

### Task 7: End-to-End Smoke Test

**Files:**
- No code changes — run against live site

- [ ] **Step 1: Run the scraper against the live site**

```bash
cd scraped && .venv/bin/python scrape.py
```

Expected output (approximate):
```
Fetching letter pages...
  Fetched 28 pages
  Found ~XXX persons total
  JSON: XXX new, 0 skipped (existing)
Downloading images...
  Images: XXX downloaded
Done!
```

- [ ] **Step 2: Verify output**

```bash
ls scraped/json/ | head -5
ls scraped/images/ | head -5
cat scraped/json/ackerman-alina.json
```

Verify:
- JSON files exist in `scraped/json/`
- Images exist in `scraped/images/`
- JSON content matches PERSON_SCHEMA format

- [ ] **Step 3: Verify idempotency — re-run should skip everything**

```bash
cd scraped && .venv/bin/python scrape.py
```

Expected:
```
Fetching letter pages...
  Fetched 28 pages
  Found ~XXX persons total
  JSON: 0 new, XXX skipped (existing)
Downloading images...
  Images: 0 downloaded
Done!
```

- [ ] **Step 4: Commit any fixes if needed, then final commit**

```bash
git add scraped/
git commit -m "feat(scraper): verified end-to-end against live site"
```
