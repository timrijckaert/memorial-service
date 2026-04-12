"""Tests for heemkring scraper."""

import pytest
from scrape import LETTER_PAGES, split_name


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
