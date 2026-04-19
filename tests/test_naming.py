# tests/test_naming.py
from src.naming import format_dutch_date, derive_filename


def test_format_dutch_date_januari():
    assert format_dutch_date("1913-01-21") == "21 januari 1913"


def test_format_dutch_date_december():
    assert format_dutch_date("1980-12-15") == "15 december 1980"


def test_format_dutch_date_mei():
    assert format_dutch_date("1927-05-04") == "04 mei 1927"


def test_format_dutch_date_strips_leading_zero_not():
    # Convention keeps leading zero: "05 januari" not "5 januari"
    assert format_dutch_date("1898-01-05") == "05 januari 1898"


def test_derive_filename_all_fields():
    card = {
        "person": {
            "first_name": "Dominicus",
            "last_name": "Meganck",
            "locality": "Kerksken",
            "death_date": "1913-12-21",
        }
    }
    assert derive_filename(card) == "Meganck Dominicus Kerksken bidprentje 21 december 1913"


def test_derive_filename_no_locality():
    card = {
        "person": {
            "first_name": "Dominicus",
            "last_name": "Meganck",
            "locality": None,
            "death_date": "1913-12-21",
        }
    }
    assert derive_filename(card) == "Meganck Dominicus bidprentje 21 december 1913"


def test_derive_filename_no_death_date():
    card = {
        "person": {
            "first_name": "Dominicus",
            "last_name": "Meganck",
            "locality": "Kerksken",
            "death_date": None,
        }
    }
    assert derive_filename(card) == "Meganck Dominicus Kerksken bidprentje"


def test_derive_filename_only_last_name():
    card = {
        "person": {
            "first_name": None,
            "last_name": "Meganck",
            "locality": None,
            "death_date": None,
        }
    }
    assert derive_filename(card) == "Meganck bidprentje"


def test_derive_filename_empty_person():
    card = {"person": {}}
    assert derive_filename(card) == "bidprentje"


def test_derive_filename_missing_person_key():
    card = {}
    assert derive_filename(card) == "bidprentje"
