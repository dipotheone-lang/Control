"""§5.5 OCR — the floor, and the confidentiality gate in front of it."""

from pathlib import Path

from control.discovery.stage_c import run_stage_c
from control.ocr import DEFAULT_CONFIDENCE_FLOOR, OcrResult

CLIENTS = ["Siemens Energy", "KNAUF"]


def _contract_text():
    return (
        "The performance bond shall remain valid until 30/11/2026.\n"
        "The Contractor shall give notice of any claim within 28 days.\n"
    )


def _fake_ocr(text, *, confidence=90.0, below=False, error=""):
    """An OCR callable with a known verdict, so the gate and the floor
    can be tested without an engine installed."""
    calls: list[Path] = []

    def run(path):
        calls.append(Path(path))
        return OcrResult(
            source=str(path),
            text=None if (below or error) else text,
            mean_confidence=confidence,
            words=0 if error else 40,
            pages_read=1, pages_total=1,
            below_floor=below, error=error,
        )

    run.calls = calls
    return run


def test_ocr_reads_a_scan_that_would_otherwise_be_a_gap(tmp_path):
    (tmp_path / "scan.jpg").write_bytes(b"\xff\xd8\xff not really an image")
    ocr = _fake_ocr(_contract_text())

    result = run_stage_c(tmp_path, CLIENTS, [], ocr=ocr)

    assert result.unreadable == []
    assert result.ocr_read == ["scan.jpg"]
    kinds = {t.kind for t in result.terms}
    assert "GUARANTEE_EXPIRY" in kinds and "NOTICE_PERIOD" in kinds


def test_without_ocr_a_scan_stays_a_declared_gap(tmp_path):
    (tmp_path / "scan.jpg").write_bytes(b"\xff\xd8\xff nope")

    result = run_stage_c(tmp_path, CLIENTS, [])

    assert len(result.unreadable) == 1
    assert "not enabled on this run" in result.unreadable[0].note
    assert result.terms == []


def test_below_the_floor_nothing_is_posted(tmp_path):
    """§5.5: a wrong number in a register is worse than no number. The
    text must not reach find_terms at all."""
    (tmp_path / "faint.jpg").write_bytes(b"\xff\xd8\xff faint")
    ocr = _fake_ocr(_contract_text(), confidence=31.0, below=True)

    result = run_stage_c(tmp_path, CLIENTS, [], ocr=ocr)

    assert result.terms == []
    assert len(result.unreadable) == 1
    assert "below the §5.5 confidence floor" in result.unreadable[0].note
    assert result.ocr_read == []
    assert result.ocr_below_floor and "31.0" in result.ocr_below_floor[0]


def test_ocr_failure_is_recorded_not_fatal(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"\xff\xd8\xff one")
    (tmp_path / "b.txt").write_text(_contract_text(), encoding="utf-8")
    ocr = _fake_ocr("", error="PdfError: broken xref")

    result = run_stage_c(tmp_path, CLIENTS, [], ocr=ocr)

    # The good document still made it through.
    assert any(t.found_date == "2026-11-30" for t in result.terms)
    assert result.ocr_failed and "broken xref" in result.ocr_failed[0]
    assert any("OCR failed" in r.note for r in result.unreadable)


def test_confidential_scans_are_never_ocrd_even_under_d05(tmp_path):
    """confidential.yaml lists OCR under metadata_only_mode.prohibited,
    and D-05 as recorded covers dates, not OCR. Widening an NDA
    exception by inference is the direction §12.1.1 forbids."""
    (tmp_path / "KNAUF").mkdir()
    (tmp_path / "KNAUF" / "contract.jpg").write_bytes(b"\xff\xd8\xff secret")
    ocr = _fake_ocr(_contract_text())

    result = run_stage_c(tmp_path, CLIENTS, [], ocr=ocr,
                         permit_confidential_dates=True)

    assert ocr.calls == [], "OCR must not be invoked on a confidential document"
    assert result.terms == []
    assert len(result.unreadable) == 1
    note = result.unreadable[0].note
    assert "not OCR'd: confidential" in note
    assert "D-05 covers dates, not OCR" in note


def test_confidential_scan_blocked_without_d05_too(tmp_path):
    (tmp_path / "KNAUF").mkdir()
    (tmp_path / "KNAUF" / "contract.jpg").write_bytes(b"\xff\xd8\xff secret")
    ocr = _fake_ocr(_contract_text())

    result = run_stage_c(tmp_path, CLIENTS, [], ocr=ocr)

    assert ocr.calls == []
    assert len(result.blocked) == 1
    assert result.terms == []


def test_textless_pdf_falls_through_to_ocr(tmp_path):
    """A PDF with no text layer is a scan in a PDF wrapper. Before this,
    it was filed unreadable without OCR ever being offered it."""
    (tmp_path / "wrapped.txt").write_text("   \n  ", encoding="utf-8")
    ocr = _fake_ocr(_contract_text())

    result = run_stage_c(tmp_path, CLIENTS, [], ocr=ocr)

    assert ocr.calls, "empty extractable text should have been offered to OCR"
    assert any(t.found_date == "2026-11-30" for t in result.terms)


def test_floor_default_is_not_zero():
    """A floor of 0 would admit anything, which is the failure mode §5.5
    exists to prevent."""
    assert DEFAULT_CONFIDENCE_FLOOR >= 50


def test_available_reports_unusable_without_arabic(monkeypatch):
    """§5.5 requires Arabic. English-only must read as unusable, not as
    a working engine that quietly fabricates Arabic text."""
    import control.ocr as ocr_module

    monkeypatch.setattr(ocr_module, "resolve_binary", lambda: "tesseract")
    monkeypatch.setattr(ocr_module, "_languages", lambda b, t: {"eng", "osd"})
    usable, reason = ocr_module.available()
    assert usable is False
    assert "Arabic" in reason
