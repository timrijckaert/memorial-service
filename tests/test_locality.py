# tests/test_locality.py
from src.locality import derive_locality


def test_exact_match_death_place():
    card = {"person": {"death_place": "Kerksken", "birth_place": "Brussel"}}
    assert derive_locality(card) == "Kerksken"


def test_exact_match_death_place_haaltert():
    card = {"person": {"death_place": "Haaltert", "birth_place": "Gent"}}
    assert derive_locality(card) == "Haaltert"


def test_exact_match_death_place_denderhoutem():
    card = {"person": {"death_place": "Denderhoutem", "birth_place": None}}
    assert derive_locality(card) == "Denderhoutem"


def test_exact_match_death_place_terjoden():
    card = {"person": {"death_place": "Terjoden", "birth_place": None}}
    assert derive_locality(card) == "Terjoden"


def test_substring_match_earliest_position_wins():
    card = {"person": {"death_place": "Denderhoutem (Haaltert)", "birth_place": None}}
    assert derive_locality(card) == "Denderhoutem"


def test_substring_match_haaltert_first_in_string():
    card = {"person": {"death_place": "Haaltert-Denderhoutem", "birth_place": None}}
    assert derive_locality(card) == "Haaltert"


def test_case_insensitive_match():
    card = {"person": {"death_place": "kerksken", "birth_place": None}}
    assert derive_locality(card) == "Kerksken"


def test_fallback_to_birth_place():
    card = {"person": {"death_place": "Brussel", "birth_place": "Terjoden"}}
    assert derive_locality(card) == "Terjoden"


def test_fallback_to_birth_place_substring():
    card = {"person": {"death_place": "Gent", "birth_place": "Denderhoutem (Haaltert)"}}
    assert derive_locality(card) == "Denderhoutem"


def test_default_when_no_match():
    card = {"person": {"death_place": "Brussel", "birth_place": "Gent"}}
    assert derive_locality(card) == "Haaltert"


def test_default_when_both_none():
    card = {"person": {"death_place": None, "birth_place": None}}
    assert derive_locality(card) == "Haaltert"


def test_default_when_person_empty():
    card = {"person": {}}
    assert derive_locality(card) == "Haaltert"


def test_default_when_no_person_key():
    card = {}
    assert derive_locality(card) == "Haaltert"


def test_derive_locality_sets_on_card_dict():
    """Verify derive_locality works when called on a full card structure
    matching how interpret_text builds the 'existing' dict."""
    existing = {
        "person": {
            "first_name": "Jan",
            "last_name": "Peeters",
            "birth_place": "Gent",
            "death_place": "Kerksken",
        },
        "notes": [],
        "source": {},
    }
    existing["person"]["locality"] = derive_locality(existing)
    assert existing["person"]["locality"] == "Kerksken"
