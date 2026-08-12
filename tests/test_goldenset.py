from datetime import datetime

import pytest

from control.evaluate import ObligationSpec, SubmissionDoc, TotalRule
from control.goldenset import (
    add_case,
    ceo_worksheets,
    load_cases,
    regression_gate,
    report,
    run_golden_set,
)

SPEC = ObligationSpec(
    obligation_id="OPS-WPR-001", name="Weekly progress", form_code="FRM-WPR",
    current_revision="3", due=datetime(2026, 8, 13, 12, 0),
    mandatory_fields=["B2"], totals=[TotalRule("B10", ["B4", "B5"])],
)


def _doc(**kw):
    base = dict(
        received_at=datetime(2026, 8, 13, 9, 0),
        attachment_name="FRM-WPR.xlsx", form_code="FRM-WPR", revision="3",
        fields={"B2": 1.0, "B4": 1.0, "B5": 2.0, "B10": 3.0},
    )
    base.update(kw)
    return SubmissionDoc(**base)


@pytest.fixture
def golden_dir(tmp_path):
    d = tmp_path / "golden-set"
    add_case(d, "GS-001", "initial", SPEC, _doc(), "ACCEPTED", [])
    add_case(d, "GS-002", "initial", SPEC,
             _doc(fields={"B2": 1.0, "B4": 1.0, "B5": 2.0, "B10": 9.0}),
             "RETURNED_FOR_REVISION", ["C4"])
    add_case(d, "GS-003", "dispute-upheld", SPEC, _doc(revision="2"),
             "RETURNED_FOR_REVISION", ["C2"], ceo_notes="rev 2 superseded May-2026")
    return d


def test_roundtrip_and_full_agreement(golden_dir):
    cases = load_cases(golden_dir)
    assert [c.case_id for c in cases] == ["GS-001", "GS-002", "GS-003"]
    result = run_golden_set(cases)
    assert result.agreement_rate == 1.0
    assert result.false_returns == 0
    assert result.gate_passed
    assert "GATE: PASSED" in report(result)


def test_false_return_fails_gate_with_diagnosis(golden_dir):
    # CEO says this document is fine; plant an expectation the engine
    # disagrees with -> false return must fail the gate.
    add_case(golden_dir, "GS-004", "override", SPEC,
             _doc(fields={"B2": 1.0, "B4": 1.0, "B5": 2.0, "B10": 5.0}),
             "ACCEPTED", [], ceo_notes="B10 includes manual adjustment, accepted")
    result = run_golden_set(load_cases(golden_dir))
    assert result.false_returns == 1
    assert not result.gate_passed
    text = report(result)
    assert "GS-004" in text
    assert "engine flagged C4" in text


def test_fp_counted_per_check_not_per_document(golden_dir):
    result = run_golden_set(load_cases(golden_dir))
    assert result.fp_opportunities == 3 * 7      # V2: per check
    assert result.check_false_positive_count == 0


def test_worksheets_are_unanchored_batches(golden_dir):
    cases = load_cases(golden_dir)
    batches = ceo_worksheets(cases, batch_size=2)
    assert len(batches) == 2
    text = "\n".join(batches)
    # D-03: the engine's verdict never appears anywhere in a worksheet
    for token in ("ACCEPTED", "RETURNED", "expected", "verdict:"):
        assert token not in text.replace("Verdict: ___", "")
    assert "Verdict: ___" in text
    assert "5–8 minutes" in text


def test_cases_never_overwritten(golden_dir):
    with pytest.raises(FileExistsError):
        add_case(golden_dir, "GS-001", "initial", SPEC, _doc(), "ACCEPTED", [])


def test_regression_gate(golden_dir):
    baseline = run_golden_set(load_cases(golden_dir))
    # Candidate run where a previously passing case now fails: simulate by
    # mutating an expectation (as a tightened rule would).
    cases = load_cases(golden_dir)
    cases[0].expected_verdict = "RETURNED_FOR_REVISION"   # engine will say ACCEPTED
    cases[0].expected_failed_checks = ["C4"]
    candidate = run_golden_set(cases)
    ok, reasons = regression_gate(baseline, candidate)
    assert not ok
    assert any("previously passing" in r for r in reasons)

    # Coverage falling is also a rejection
    ok2, reasons2 = regression_gate(baseline, run_golden_set(load_cases(golden_dir)[:2]))
    assert not ok2 and any("coverage fell" in r for r in reasons2)

    # Identical run passes
    ok3, _ = regression_gate(baseline, run_golden_set(load_cases(golden_dir)))
    assert ok3
