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


from pathlib import Path
from PIL import Image
from src.images.pairing import read_image_metadata


def test_read_image_metadata(tmp_path):
    img_path = tmp_path / "test.jpeg"
    img = Image.new("RGB", (200, 300))
    img.save(img_path, "JPEG")

    meta = read_image_metadata(img_path)

    assert meta["filename"] == "test.jpeg"
    assert meta["width"] == 200
    assert meta["height"] == 300
    assert "dpi" in meta
    assert meta["file_size_bytes"] > 0


def test_read_image_metadata_with_dpi(tmp_path):
    img_path = tmp_path / "hires.jpeg"
    img = Image.new("RGB", (100, 100))
    img.save(img_path, "JPEG", dpi=(300, 300))

    meta = read_image_metadata(img_path)

    assert meta["dpi"] == 300


from src.images.pairing import scan_and_match


def _make_image(path, width=100, height=100):
    """Helper: create a minimal JPEG at the given path."""
    Image.new("RGB", (width, height)).save(path, "JPEG")


def test_scan_and_match_obvious_pair(tmp_path):
    _make_image(tmp_path / "Person A bidprentje 1920.jpeg")
    _make_image(tmp_path / "Person A bidprentje 1920 1.jpeg")

    result = scan_and_match(tmp_path)

    assert len(result["pairs"]) == 1
    assert len(result["unmatched"]) == 0
    pair = result["pairs"][0]
    assert pair["score"] > 80
    assert pair["status"] == "auto_confirmed"


def test_scan_and_match_low_score_not_auto_confirmed(tmp_path):
    _make_image(tmp_path / "aaa bbb ccc.jpeg")
    _make_image(tmp_path / "xxx yyy zzz.jpeg")

    result = scan_and_match(tmp_path)

    # Score too low to pair — both should be unmatched
    assert len(result["unmatched"]) == 2
    assert len(result["pairs"]) == 0


def test_scan_and_match_multiple_pairs_greedy(tmp_path):
    _make_image(tmp_path / "De Smet Maria 1945.jpeg")
    _make_image(tmp_path / "De Smet Maria 1945 1.jpeg")
    _make_image(tmp_path / "Pieters Jan 1952.jpeg")
    _make_image(tmp_path / "Pieters Jan 1952 1.jpeg")

    result = scan_and_match(tmp_path)

    assert len(result["pairs"]) == 2
    assert len(result["unmatched"]) == 0
    names = {
        (p["image_a"]["filename"], p["image_b"]["filename"])
        for p in result["pairs"]
    }
    assert ("De Smet Maria 1945.jpeg", "De Smet Maria 1945 1.jpeg") in names or \
           ("De Smet Maria 1945 1.jpeg", "De Smet Maria 1945.jpeg") in names


def test_scan_and_match_odd_image_out(tmp_path):
    _make_image(tmp_path / "Person A 1920.jpeg")
    _make_image(tmp_path / "Person A 1920 1.jpeg")
    _make_image(tmp_path / "orphan_scan.jpeg")

    result = scan_and_match(tmp_path)

    assert len(result["pairs"]) == 1
    assert len(result["unmatched"]) == 1
    assert result["unmatched"][0]["filename"] == "orphan_scan.jpeg"


def test_scan_and_match_empty_dir(tmp_path):
    result = scan_and_match(tmp_path)

    assert result["pairs"] == []
    assert result["unmatched"] == []


def test_scan_and_match_includes_metadata(tmp_path):
    _make_image(tmp_path / "Card.jpeg", width=200, height=300)
    _make_image(tmp_path / "Card 1.jpeg", width=200, height=300)

    result = scan_and_match(tmp_path)

    pair = result["pairs"][0]
    assert pair["image_a"]["width"] == 200
    assert pair["image_a"]["height"] == 300
    assert pair["image_b"]["width"] == 200
    assert pair["image_b"]["height"] == 300
