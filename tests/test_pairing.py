# tests/test_pairing.py
from pathlib import Path
from src.merge import find_pairs


def test_find_pairs_matches_front_and_back(tmp_path):
    front = tmp_path / "Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928.jpeg"
    back = tmp_path / "Vanden Bruelle Emiel Jozef Haaltert  bidprentje 18 december 1928 1.jpeg"
    front.touch()
    back.touch()

    pairs, errors = find_pairs(tmp_path)

    assert len(pairs) == 1
    assert pairs[0] == (front, back)
    assert errors == []


def test_find_pairs_reports_missing_back(tmp_path):
    front = tmp_path / "De Smet Maria Aalst  bidprentje 3 maart 1945.jpeg"
    front.touch()

    pairs, errors = find_pairs(tmp_path)

    assert pairs == []
    assert len(errors) == 1
    assert "missing back" in errors[0].lower()


def test_find_pairs_reports_missing_front(tmp_path):
    back = tmp_path / "De Smet Maria Aalst  bidprentje 3 maart 1945 1.jpeg"
    back.touch()

    pairs, errors = find_pairs(tmp_path)

    assert pairs == []
    assert len(errors) == 1
    assert "missing front" in errors[0].lower()


def test_find_pairs_handles_multiple_pairs_and_jpg_extension(tmp_path):
    # Pair 1: .jpeg
    (tmp_path / "Person A  bidprentje 1920.jpeg").touch()
    (tmp_path / "Person A  bidprentje 1920 1.jpeg").touch()
    # Pair 2: .jpg
    (tmp_path / "Person B  bidprentje 1930.jpg").touch()
    (tmp_path / "Person B  bidprentje 1930 1.jpg").touch()

    pairs, errors = find_pairs(tmp_path)

    assert len(pairs) == 2
    assert errors == []


def test_find_pairs_handles_uppercase_extension(tmp_path):
    front = tmp_path / "Person C  bidprentje 1940.JPEG"
    back = tmp_path / "Person C  bidprentje 1940 1.JPEG"
    front.touch()
    back.touch()

    pairs, errors = find_pairs(tmp_path)

    assert len(pairs) == 1
    assert errors == []


def test_find_pairs_empty_directory(tmp_path):
    pairs, errors = find_pairs(tmp_path)

    assert pairs == []
    assert errors == []
