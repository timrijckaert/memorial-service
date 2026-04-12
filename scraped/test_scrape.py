"""Tests for heemkring scraper."""

import pytest
from scrape import LETTER_PAGES, convert_date, make_slug, split_name


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
