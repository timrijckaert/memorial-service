# Heemkring Haaltert Website Scraper

**Date:** 2026-04-12
**Status:** Draft
**Scope:** Disposable scraping tool to extract existing memorial card data from heemkringhaaltert.be into PERSON_SCHEMA JSON format.

## Goal

Scrape all biographical data and memorial card images from the Heemkring Haaltert website (https://heemkringhaaltert.be/?page_id=9498) into the project's existing JSON schema. This is a one-time data import tool -- run a few times to capture the current website state, then discard.

## Project Structure

```
scraped/
├── requirements.txt          # httpx, beautifulsoup4, lxml
├── scrape.py                 # Single standalone async script
├── json/                     # Output: one JSON per person
│   ├── ackerman-alina.json
│   └── ...
└── images/                   # Output: downloaded memorial card images
    ├── ackerman-alina.jpg
    └── ...
```

Self-contained sub-project with its own `requirements.txt`. No integration with the main `src/` package.

## Letter Page Mapping (Hardcoded)

Each letter has a dedicated WordPress page. Special pages exist for `D'h` and `Ve` due to high surname frequency.

```python
LETTER_PAGES = {
    "A": 9498, "B": 9516, "C": 9560, "D": 9580, "D'h": 9706,
    "E": 9715, "F": 9726, "G": 9741, "H": 9758, "I": 9784,
    "J": 9794, "K": 9802, "L": 9809, "M": 9825, "N": 9843,
    "O": 9857, "P": 9863, "Q": 9934, "R": 9871, "S": 9886,
    "T": 9908, "U": 9919, "V": 5695, "Ve": 9953, "W": 9924,
    "X": 9938, "Y": 9942, "Z": 9948,
}
```

## Website Table Structure

Each letter page contains a server-rendered HTML table with these columns:

| Column | PERSON_SCHEMA field | Transformation |
|--------|-------------------|----------------|
| Naam | `last_name` + `first_name` | Tussenvoegsel-aware name splitting |
| Eega | `spouses[]` | Direct mapping, wrapped in array |
| Geboren te | `birth_place` | Direct mapping |
| Geboren op | `birth_date` | DD/MM/YYYY -> YYYY-MM-DD |
| Overleden te | `death_place` | Direct mapping |
| Overleden op | `death_date` | DD/MM/YYYY -> YYYY-MM-DD |

Fields not on the website:
- `age_at_death`: always `null` (never calculated per project rules)
- `notes`: always `[]`

Each person's name links to a memorial card image at:
`/wp-content/uploads/YYYY/MM/{Name}-{Location}-bidprentje-{Date}.jpg`

## Name Splitting Algorithm

Dutch/Flemish surnames use tussenvoegsel (surname particles). The algorithm:

1. Split full name into words
2. Consume words from the front that form a known tussenvoegsel
3. Next word = core surname
4. Remaining words = first name

```python
TUSSENVOEGSELS = {
    "van", "de", "den", "der",
    "van de", "van den", "van der",
    "te", "ten", "ter", "'t",
}
```

Examples:
- `"Ackerman Alina"` -> last=`"Ackerman"`, first=`"Alina"`
- `"Van De Smet Maria"` -> last=`"Van De Smet"`, first=`"Maria"`
- `"De Smet Joseph"` -> last=`"De Smet"`, first=`"Joseph"`

The Eega (spouse) column is taken as-is and placed into the `spouses` array. No name splitting needed.

## Date Conversion

Website format: `DD/MM/YYYY` (e.g. `15/11/1902`)
Schema format: ISO 8601 `YYYY-MM-DD` (e.g. `1902-11-15`)

Dates that fail to parse (malformed, empty, `—`) are stored as `null`.

## Output JSON Format

Each person gets a file at `scraped/json/{slug}.json` where the slug is `{lastname}-{firstname}` lowercased and ASCII-normalized.

```json
{
  "person": {
    "first_name": "Alina",
    "last_name": "Ackerman",
    "birth_date": "1902-11-15",
    "birth_place": "Everberg",
    "death_date": "1966-12-16",
    "death_place": "Haaltert",
    "age_at_death": null,
    "spouses": ["Boone Pierre"]
  },
  "notes": [],
  "source": {
    "url": "https://heemkringhaaltert.be/?page_id=9498",
    "image_url": "https://heemkringhaaltert.be/wp-content/uploads/2025/12/Ackermans-Alina-Haaltert-bidprentje-16-december-1966.jpg",
    "image_file": "ackerman-alina.jpg"
  }
}
```

## Script Flow

```
1. Create output directories (scraped/json/, scraped/images/) if missing

2. Fetch all 28 letter pages (async, parallel via httpx)

3. Parse each page with BeautifulSoup
   - Extract table rows
   - For each row: extract 6 columns + image link from name href

4. Transform each row to PERSON_SCHEMA
   - Split name (tussenvoegsel-aware)
   - Convert dates (DD/MM/YYYY -> ISO 8601)
   - Map spouse name
   - Build source metadata

5. Write JSON + download images (async, parallel)
   - Skip if scraped/json/{slug}.json already exists (idempotent)
   - Skip image download if scraped/images/{slug}.jpg already exists

6. Print summary
   - "Scraped X new, skipped Y existing, Z images downloaded"
```

## Idempotency

The script is safe to re-run:
- If `scraped/json/{slug}.json` exists, the person is skipped entirely (both JSON write and image download)
- If only the JSON exists but the image is missing, the image is re-downloaded
- No update detection -- we assume website data does not change

## Dependencies

```
# scraped/requirements.txt
httpx
beautifulsoup4
lxml
```

## Edge Cases

- **Empty Eega column** (`—` or blank): `spouses` = `[]`
- **Missing image link**: `source.image_url` = `null`, no image downloaded
- **Duplicate slugs** (two people with same name): append a counter, e.g. `de-smet-maria-2.json`
- **Malformed dates**: stored as `null`
- **Special characters in names** (e.g. accents like Aloïs): normalized to ASCII for filenames, preserved in JSON fields
