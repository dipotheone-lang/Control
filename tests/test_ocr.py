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


def test_a_confidential_scan_is_ocrd_for_dates_under_d14(tmp_path):
    """Decision D-14 (17-Aug-2026) extended D-05 to permit OCR here.

    This test previously asserted the opposite, and was right to: until
    the CEO decided, widening an NDA exception by inference was the
    direction §12.1.1 forbids. The decision was taken because the first
    live Stage C run found 47% of legal documents are photographs — so
    the guarantee expiries D-05 exists to catch were exactly the ones
    unreachable.
    """
    (tmp_path / "KNAUF").mkdir()
    (tmp_path / "KNAUF" / "contract.jpg").write_bytes(b"\xff\xd8\xff secret")
    ocr = _fake_ocr(_contract_text())

    result = run_stage_c(tmp_path, CLIENTS, [], ocr=ocr,
                         permit_confidential_dates=True)

    assert ocr.calls, "D-14 permits OCR on a confidential contract for dates"
    assert [t.found_date for t in result.terms], "the dates are the whole point"


def test_a_confidential_scan_keeps_the_date_and_never_the_clause(tmp_path):
    """D-14's added condition: the OCR text buffer is never retained.

    Redaction happens at capture, so no later template change can leak
    what was never stored.
    """
    (tmp_path / "KNAUF").mkdir()
    (tmp_path / "KNAUF" / "contract.jpg").write_bytes(b"\xff\xd8\xff secret")

    result = run_stage_c(tmp_path, CLIENTS, [], ocr=_fake_ocr(_contract_text()),
                         permit_confidential_dates=True)

    body = _contract_text()
    for term in result.terms:
        assert "REDACTED" in term.context
        assert term.context not in body
        assert term.found_date, "a term with no date has nothing to justify it"

    # And nothing anywhere in the rendered output carries the body.
    from control.discovery.stage_c import render_commercial_exposure
    rendered = render_commercial_exposure(result)
    for fragment in body.split():
        if len(fragment) > 8 and fragment.isalpha():
            assert fragment not in rendered


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
    import sys
    import types

    import control.ocr as ocr_module

    # Stand in for the optional engine bindings. Without this the test
    # passes or fails according to what happens to be pip-installed,
    # which measures the machine rather than the rule.
    for name in ("pytesseract", "pymupdf"):
        monkeypatch.setitem(sys.modules, name,
                            sys.modules.get(name) or types.ModuleType(name))
    monkeypatch.setattr(ocr_module, "resolve_binary", lambda: "tesseract")
    monkeypatch.setattr(ocr_module, "resolve_tessdata", lambda: "/tessdata")
    monkeypatch.setattr(ocr_module, "_languages", lambda b, t: {"eng", "osd"})

    usable, reason = ocr_module.available()
    assert usable is False
    assert "Arabic" in reason


def test_the_run_banner_matches_what_the_code_actually_does(tmp_path, capsys,
                                                            monkeypatch):
    """A false statement about a confidentiality control is the failure
    this guards.

    The integration of the laptop branch carried over a banner saying
    "OCR is NOT applied to confidential documents" while the merged code,
    under D-14, applied it. The behaviour was the decided one; the
    sentence was the stale one. Either would have been a defect — a
    control that says the wrong thing about itself is not a control.
    """
    import control.ocr as ocr_module
    from control.__main__ import main

    monkeypatch.setattr(ocr_module, "available",
                        lambda: (True, "tesseract with ara, eng"))
    monkeypatch.setattr(ocr_module, "ocr_document",
                        lambda path, **kw: OcrResult(source=str(path),
                                                     error="stub"))
    source = tmp_path / "src" / "KNAUF"
    source.mkdir(parents=True)
    (source / "c.txt").write_text("Bond valid until 30/11/2026.\n",
                                  encoding="utf-8")
    root = tmp_path / "CONTROL"
    main(["init", "--control-root", str(root)])
    capsys.readouterr()

    base = ["contracts", "--control-root", str(root),
            "--source", str(tmp_path / "src"), "--ocr"]

    main(base)
    without = capsys.readouterr().out
    assert "are NOT OCR'd on this run" in without
    assert "ARE included" not in without

    main(base + ["--confidential-dates"])
    with_flag = capsys.readouterr().out
    assert "Confidential contracts ARE included" in with_flag
    assert "D-14" in with_flag
    assert "never retained" in with_flag
    assert "NOT OCR'd" not in with_flag
