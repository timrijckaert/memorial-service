"""Tests for heemkring scraper."""

from scrape import LETTER_PAGES


def test_letter_pages_has_28_entries():
    assert len(LETTER_PAGES) == 28
