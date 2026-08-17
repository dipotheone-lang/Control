"""OCR and its confidence floor — charter §5.5.

The Phase 0 scan is why this module exists. 362 legal documents
produced ZERO guarantee expiries, LD rates, notice periods or
defects-liability dates — not because there are none, but because 47%
of them are photographs of text, 81% for supplier legal documents. §2.2
calls a forfeited claim window the most expensive failure in this
charter, and the windows were in files nothing could read.

Almost every test here is about the floor, because the floor is what
makes OCR safe to use at all:

    "Never post an OCR figure below the floor. A wrong number in a
     register is worse than no number."

A permissive floor on a scanned Arabic contract produces plausible
dates that are wrong, and a wrong date in a class 2 register alerts
confidently on the wrong day.

The engine is injected throughout, so these run on a machine with no
Tesseract — which is also the machine most of this was written on.
"""

from pathlib import Path

import pytest
import yaml

from control.ocr import (
    DEFAULT_FLOOR, OcrSettings, engine_status, ocr_image, ocr_pdf,
    read_scanned, summarise,
)

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


def words(pairs):
    """A tesseract-shaped dict: (text, confidence) pairs."""
    return {"text": [t for t, _ in pairs], "conf": [c for _, c in pairs]}


def reader_for(pairs):
    def reader(_path, _languages):
        return words(pairs)
    return reader


ON = OcrSettings(enabled=True, floor=80.0)


# ---- the floor --------------------------------------------------------

def test_a_confident_reading_is_returned(tmp_path):
    result = ocr_image(tmp_path / "scan.png", ON, reader=reader_for(
        [("Guarantee", 95), ("expires", 92), ("31/12/2026", 90)]))
    assert result.accepted is True
    assert "31/12/2026" in result.text
    assert result.verdict == "OCR_ACCEPTED"


def test_a_reading_below_the_floor_returns_no_text_at_all(tmp_path):
    """The load-bearing test. Below-floor text is never handed back, so
    a caller cannot accidentally treat a guess as a reading."""
    result = ocr_image(tmp_path / "scan.png", ON, reader=reader_for(
        [("Guarantee", 40), ("expires", 35), ("31/12/2026", 30)]))
    assert result.accepted is False
    assert result.text == ""
    assert result.confidence == pytest.approx(35.0)
    assert "below the §5.5 floor" in result.reason
    assert result.verdict == "UNREADABLE — MANUAL REVIEW REQUIRED"


def test_the_boundary_is_inclusive_upward(tmp_path):
    exactly = ocr_image(tmp_path / "s.png", ON,
                        reader=reader_for([("x", 80)]))
    just_under = ocr_image(tmp_path / "s.png", ON,
                           reader=reader_for([("x", 79.9)]))
    assert exactly.accepted is True
    assert just_under.accepted is False


def test_unattempted_boxes_do_not_drag_the_average(tmp_path):
    """Tesseract emits -1 for boxes it did not attempt and empty strings
    for whitespace. Averaging those in would make confidence depend on
    layout rather than on legibility."""
    result = ocr_image(tmp_path / "s.png", ON, reader=lambda p, l: {
        "text": ["Guarantee", "", "expires", " "],
        "conf": [95, -1, 91, -1]})
    assert result.confidence == pytest.approx(93.0)
    assert result.accepted is True


def test_nothing_recognised_is_reported_as_such(tmp_path):
    result = ocr_image(tmp_path / "s.png", ON, reader=lambda p, l: {
        "text": ["", " "], "conf": [-1, -1]})
    assert result.accepted is False
    assert result.confidence is None
    assert result.reason == "no words recognised"
    assert result.verdict == "NOT ATTEMPTED"


def test_a_stricter_floor_rejects_what_a_looser_one_accepts(tmp_path):
    pairs = [("Guarantee", 85), ("expires", 85)]
    assert ocr_image(tmp_path / "s.png", OcrSettings(enabled=True, floor=80),
                     reader=reader_for(pairs)).accepted is True
    assert ocr_image(tmp_path / "s.png", OcrSettings(enabled=True, floor=90),
                     reader=reader_for(pairs)).accepted is False


# ---- refusals ---------------------------------------------------------

def test_ocr_disabled_reads_nothing_and_says_so(tmp_path):
    result = read_scanned(tmp_path / "s.png", OcrSettings(enabled=False))
    assert result.accepted is False
    assert "not enabled" in result.reason


def test_a_missing_engine_is_reported_not_worked_around(tmp_path):
    """No silent fallback, and no pretending the document had no terms
    when the truth is that nothing looked at it."""
    def explode(_path, _languages):
        raise RuntimeError("tesseract is not installed")

    result = ocr_image(tmp_path / "s.png", ON, reader=explode)
    assert result.accepted is False
    assert "tesseract is not installed" in result.reason


def test_engine_status_never_raises():
    status = engine_status()
    assert set(status) == {"ocr", "pdf_render", "languages", "notes"}
    assert isinstance(status["notes"], list)


def test_engine_status_names_what_is_missing():
    """A machine without OCR should learn which piece to install, not
    that 'OCR is unavailable'."""
    status = engine_status()
    if not status["ocr"]:
        assert any("pytesseract" in note for note in status["notes"])
    if not status["pdf_render"]:
        assert any("pymupdf" in note.lower() for note in status["notes"])


# ---- scanned PDFs -----------------------------------------------------

def two_pages(_path, _dpi, _max):
    return [b"page-1", b"page-2"]


def test_a_scanned_pdf_is_rendered_then_read(tmp_path):
    result = ocr_pdf(tmp_path / "contract.pdf", ON, renderer=two_pages,
                     reader=lambda image, l: words(
                         [("Guarantee", 93), ("31/12/2026", 91)]))
    assert result.accepted is True
    assert result.pages == 2
    assert result.text.count("Guarantee") == 2


def test_page_confidence_is_weighted_by_words_recognised(tmp_path):
    """One near-blank page must not sink a readable contract, and one
    clean cover page must not lift a bad scan over the floor."""
    pages = iter([
        words([("x", 30)]),                                  # 1 word, poor
        words([("a", 95), ("b", 95), ("c", 95), ("d", 95)]),  # 4 words, good
    ])
    result = ocr_pdf(tmp_path / "c.pdf", ON, renderer=two_pages,
                     reader=lambda image, l: next(pages))
    # (30*1 + 95*4) / 5 = 82 — above the floor, where a flat mean of
    # 62.5 would have wrongly rejected it.
    assert result.confidence == pytest.approx(82.0)
    assert result.accepted is True


def test_a_cover_page_cannot_lift_a_bad_scan(tmp_path):
    pages = iter([
        words([("CONTRACT", 99)]),                       # 1 clean word
        words([(f"w{i}", 40) for i in range(20)]),        # 20 poor words
    ])
    result = ocr_pdf(tmp_path / "c.pdf", ON, renderer=two_pages,
                     reader=lambda image, l: next(pages))
    assert result.accepted is False
    assert result.confidence < 80


def test_an_unrenderable_pdf_is_a_gap(tmp_path):
    def explode(_path, _dpi, _max):
        raise RuntimeError("PyMuPDF missing")

    result = ocr_pdf(tmp_path / "c.pdf", ON, renderer=explode)
    assert result.accepted is False
    assert "PyMuPDF missing" in result.reason


def test_read_scanned_routes_pdfs_to_the_renderer(tmp_path):
    result = read_scanned(tmp_path / "c.pdf", ON, renderer=two_pages,
                          reader=lambda image, l: words([("x", 95)]))
    assert result.pages == 2


# ---- reporting --------------------------------------------------------

def test_below_floor_is_counted_apart_from_engine_failure(tmp_path):
    """Different problems. One means the engine read it and the reading
    was not trustworthy; the other means nothing looked at it. Collapsing
    them would hide which the company actually has."""
    results = [
        ocr_image(tmp_path / "a.png", ON, reader=reader_for([("x", 95)])),
        ocr_image(tmp_path / "b.png", ON, reader=reader_for([("x", 40)])),
        ocr_image(tmp_path / "c.png", ON,
                  reader=lambda p, l: (_ for _ in ()).throw(RuntimeError("no engine"))),
    ]
    counts = summarise(results)
    assert counts == {
        "total": 3, "accepted": 1, "below_floor": 1,
        "not_attempted_or_failed": 1, "mean_confidence_accepted": 95.0}


# ---- Stage C integration ---------------------------------------------

def test_stage_c_reads_a_scan_when_ocr_clears_the_floor(tmp_path, monkeypatch):
    from control.discovery import stage_c

    (tmp_path / "Contracts").mkdir()
    (tmp_path / "Contracts" / "guarantee.png").write_bytes(b"not really a png")

    monkeypatch.setattr(stage_c, "read_scanned", None, raising=False)
    import control.ocr as ocr_module

    monkeypatch.setattr(
        ocr_module, "ocr_image",
        lambda path, settings, **kw: ocr_module.OcrResult(
            path=str(path), text="Letter of guarantee valid until 31/12/2026",
            confidence=94.0, floor=settings.floor, accepted=True))

    result = stage_c.run_stage_c(
        tmp_path, [], [], ocr_settings=OcrSettings(enabled=True))
    assert result.ocr_results and result.ocr_results[0].accepted
    assert any(t.kind == "GUARANTEE_EXPIRY" for t in result.terms)
    assert result.unreadable == []


def test_stage_c_leaves_a_below_floor_scan_unreadable(tmp_path, monkeypatch):
    from control.discovery import stage_c

    (tmp_path / "scan.png").write_bytes(b"x")
    import control.ocr as ocr_module

    monkeypatch.setattr(
        ocr_module, "ocr_image",
        lambda path, settings, **kw: ocr_module.OcrResult(
            path=str(path), confidence=42.0, floor=settings.floor,
            accepted=False, reason="mean confidence 42.0 is below the §5.5 floor"))

    result = stage_c.run_stage_c(
        tmp_path, [], [], ocr_settings=OcrSettings(enabled=True))
    assert result.terms == []
    assert len(result.unreadable) == 1
    assert "below the §5.5 floor" in result.unreadable[0].note


def test_stage_c_without_ocr_behaves_exactly_as_before(tmp_path):
    from control.discovery import stage_c

    (tmp_path / "scan.png").write_bytes(b"x")
    result = stage_c.run_stage_c(tmp_path, [], [])
    assert result.ocr_results == []
    assert len(result.unreadable) == 1
    assert "OCR required" in result.unreadable[0].note


# ---- the shipped config ----------------------------------------------

def test_the_repo_config_ships_with_ocr_off():
    """Absent an engine, nothing should change silently."""
    data = yaml.safe_load((REPO_CONFIG / "ocr.yaml").read_text(encoding="utf-8"))
    assert data["enabled"] is False
    settings = OcrSettings.from_config(data)
    assert settings.enabled is False


def test_arabic_is_listed_first():
    """Most of this document estate is Arabic; language order matters to
    tesseract's segmentation."""
    data = yaml.safe_load((REPO_CONFIG / "ocr.yaml").read_text(encoding="utf-8"))
    assert data["languages"][0] == "ara"


def test_the_shipped_floor_is_the_conservative_default():
    data = yaml.safe_load((REPO_CONFIG / "ocr.yaml").read_text(encoding="utf-8"))
    assert data["confidence_floor"] == DEFAULT_FLOOR
    assert data["dpi"] >= 300


def test_missing_config_yields_ocr_off_not_ocr_on():
    assert OcrSettings.from_config(None).enabled is False
    assert OcrSettings.from_config({}).enabled is False
    assert OcrSettings.from_config({}).floor == DEFAULT_FLOOR
