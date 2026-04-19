# src/locality.py
"""Resolve locality from card data for filename derivation."""

KNOWN_LOCALITIES = ["Haaltert", "Kerksken", "Denderhoutem", "Terjoden"]
DEFAULT_LOCALITY = "Haaltert"


def _find_locality(place: str) -> str | None:
    """Find the known locality that appears earliest in the place string.

    Returns the matching locality (properly cased) or None.
    Case-insensitive substring matching with earliest-position tie-break.
    """
    place_lower = place.lower()
    best_match = None
    best_pos = len(place_lower)

    for loc in KNOWN_LOCALITIES:
        pos = place_lower.find(loc.lower())
        if pos != -1 and pos < best_pos:
            best_pos = pos
            best_match = loc

    return best_match


def derive_locality(card: dict) -> str:
    """Derive locality from death_place, then birth_place, defaulting to Haaltert.

    Checks death_place first, then birth_place. Each is matched against
    the known localities using case-insensitive substring matching.
    If neither matches, returns "Haaltert".
    """
    person = card.get("person", {})

    death_place = person.get("death_place")
    if death_place:
        match = _find_locality(death_place)
        if match:
            return match

    birth_place = person.get("birth_place")
    if birth_place:
        match = _find_locality(birth_place)
        if match:
            return match

    return DEFAULT_LOCALITY
