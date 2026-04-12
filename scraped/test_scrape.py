"""Tests for heemkring scraper."""

import pytest
from scrape import LETTER_PAGES, convert_date, deduplicate_slugs, make_slug, split_name


def test_letter_pages_has_28_entries():
    assert len(LETTER_PAGES) == 28


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


@pytest.mark.parametrize("last, first, expected", [
    ("Ackerman", "Alina", "ackerman-alina"),
    ("Van De Smet", "Maria", "van-de-smet-maria"),
    ("Janssens", "Aloïs", "janssens-alois"),
    ("D'Hondt", "Pierre", "d-hondt-pierre"),
])
def test_make_slug(last, first, expected):
    assert make_slug(last, first) == expected


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


def test_deduplicate_slugs():
    persons = [
        {"slug": "de-smet-maria", "person": {"last_name": "De Smet", "first_name": "Maria"}, "source": {"image_file": "de-smet-maria.jpg"}},
        {"slug": "janssens-karel", "person": {"last_name": "Janssens", "first_name": "Karel"}, "source": {"image_file": "janssens-karel.jpg"}},
        {"slug": "de-smet-maria", "person": {"last_name": "De Smet", "first_name": "Maria"}, "source": {"image_file": "de-smet-maria.jpg"}},
        {"slug": "de-smet-maria", "person": {"last_name": "De Smet", "first_name": "Maria"}, "source": {"image_file": "de-smet-maria.jpg"}},
    ]
    deduplicate_slugs(persons)
    slugs = [p["slug"] for p in persons]
    assert slugs == ["de-smet-maria", "janssens-karel", "de-smet-maria-2", "de-smet-maria-3"]
    # Also check image_file was updated
    assert persons[2]["source"]["image_file"] == "de-smet-maria-2.jpg"
    assert persons[3]["source"]["image_file"] == "de-smet-maria-3.jpg"
