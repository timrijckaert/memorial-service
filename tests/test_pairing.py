# tests/test_pairing.py
from src.images.pairing import normalize_filename, similarity_score


def test_normalize_strips_extension():
    assert normalize_filename("photo.jpeg") == "photo"


def test_normalize_lowercases():
    assert normalize_filename("Photo.JPEG") == "photo"


def test_normalize_collapses_whitespace():
    assert normalize_filename("Vanden  Bruelle   Emiel.jpeg") == "vanden bruelle emiel"


def test_normalize_removes_back_suffix_space_1():
    assert normalize_filename("Person Name 1.jpeg") == "person name"


def test_normalize_removes_back_suffix_underscore_back():
    assert normalize_filename("Person_Name_back.jpeg") == "person name"


def test_normalize_removes_achterkant_suffix():
    assert normalize_filename("bidprentje_achterkant.jpeg") == "bidprentje"


def test_similarity_identical_names():
    score = similarity_score("person name 1920", "person name 1920")
    assert score == 100


def test_similarity_front_back_pair():
    score = similarity_score(
        "vanden bruelle emiel jozef haaltert bidprentje 18 december 1928",
        "vanden bruelle emiel jozef haaltert bidprentje 18 december 1928",
    )
    assert score == 100


def test_similarity_partial_overlap():
    score = similarity_score(
        "de smet maria theresia bidprentje",
        "de smet maria bidprentje",
    )
    assert 50 < score < 100


def test_similarity_no_overlap():
    score = similarity_score("aaa bbb ccc", "xxx yyy zzz")
    assert score < 20


def test_similarity_typo_resilience():
    score = similarity_score(
        "pieters jan baptist haaltert 1952",
        "pieters jan batist haaltert 1952",
    )
    assert score > 80
