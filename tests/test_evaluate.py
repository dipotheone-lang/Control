from datetime import datetime

import pytest

from control.calendar import WorkingCalendar
from control.evaluate import (
    Materiality,
    ManualRule,
    ObligationSpec,
    OpeningRule,
    SubmissionDoc,
    TotalRule,
    evaluate,
)

CAL = WorkingCalendar()
DUE = datetime(2026, 8, 13, 12, 0)  # Thursday noon


def spec(**kw):
    base = dict(
        obligation_id="OPS-WPR-001",
        name="Weekly progress report",
        form_code="FRM-WPR",
        current_revision="3",
        due=DUE,
        mandatory_fields=["B2", "B3"],
        totals=[TotalRule("B10", ["B4", "B5", "B6"])],
        openings=[OpeningRule("B2", "closing")],
    )
    base.update(kw)
    return ObligationSpec(**base)


def doc(**kw):
    base = dict(
        received_at=datetime(2026, 8, 13, 9, 0),
        attachment_name="FRM-WPR_w32.xlsx",
        form_code="FRM-WPR",
        revision="3",
        fields={"B2": 100.0, "B3": "site A", "B4": 1.0, "B5": 2.0, "B6": 3.0, "B10": 6.0},
    )
    base.update(kw)
    return SubmissionDoc(**base)


def test_clean_submission_accepted():
    r = evaluate(spec(), doc(), CAL)
    assert r.verdict == "ACCEPTED"
    assert r.timeliness == "ON_TIME"
    assert r.findings == []


def test_late_but_correct_is_accepted_with_c1_finding():
    r = evaluate(spec(), doc(received_at=datetime(2026, 8, 16, 9, 0)), CAL)  # Sunday
    assert r.verdict == "ACCEPTED"
    assert r.timeliness == "LATE (1 working days)"
    assert r.findings[0].check == "C1"


def test_no_attachment_not_accepted():
    r = evaluate(spec(), doc(attachment_name=None, form_code=None, fields={}), CAL)
    assert r.verdict == "NOT_ACCEPTED"
    assert r.check_results["C2"] == "NO_ATTACHMENT"


def test_superseded_revision_returned():
    r = evaluate(spec(), doc(revision="2"), CAL)
    assert r.verdict == "RETURNED_FOR_REVISION"
    f = next(f for f in r.findings if f.check == "C2")
    assert "rev 3 (current)" in f.required and "rev 2 (superseded)" in f.observed


def test_incomplete_lists_exact_fields():
    r = evaluate(spec(), doc(fields={"B2": None, "B3": "TBD", "B4": 1, "B5": 2, "B6": 3, "B10": 6}), CAL)
    assert r.verdict == "RETURNED_FOR_REVISION"
    f = next(f for f in r.findings if f.check == "C3")
    assert "B2" in f.observed and "B3" in f.observed


def test_arithmetic_error_reports_stated_computed_delta():
    r = evaluate(spec(), doc(fields={"B2": 1, "B3": "x", "B4": 1.0, "B5": 2.0, "B6": 3.0, "B10": 7.0}), CAL)
    assert r.verdict == "RETURNED_FOR_REVISION"
    f = next(f for f in r.findings if f.check == "C4")
    assert "stated 7.0 / computed 6.0 / delta +1" in f.observed


def test_opening_vs_prior_closing_materiality():
    prior = {"closing": 90.0}
    mat = Materiality(floor_abs=5.0, floor_pct=5.0)
    r = evaluate(spec(), doc(), CAL, prior_fields=prior, materiality=mat)
    assert r.check_results["C5"] == "VARIANCE_UNEXPLAINED"  # 100 vs 90 = 11%
    # Below the floor: 100 vs 98 is 2 abs (< floor_abs 5) -> silent
    r2 = evaluate(spec(), doc(), CAL, prior_fields={"closing": 98.0}, materiality=mat)
    assert r2.check_results["C5"] == "CONSISTENT"


def test_insufficient_baseline_keeps_variance_silent():
    mat = Materiality(floor_abs=1.0, floor_pct=1.0, sufficient=False)
    r = evaluate(spec(), doc(), CAL, prior_fields={"closing": 50.0}, materiality=mat)
    assert r.check_results["C5"] == "CONSISTENT"


def test_copy_forward_suspected():
    fields = {"B2": 100.0, "B3": "site A", "B4": 1.0, "B5": 2.0, "B6": 3.0, "B10": 6.0}
    prior = {"B2": 100.0, "B4": 1.0, "B5": 2.0, "B6": 3.0, "B10": 6.0, "closing": 100.0}
    r = evaluate(spec(), doc(fields=dict(fields)), CAL, prior_fields=prior)
    assert r.check_results["C5"] == "SUSPECTED_COPY_FORWARD"
    assert r.verdict == "RETURNED_FOR_REVISION"


def test_manual_rule_quotes_clause():
    rules = [ManualRule("QM-03 §4.2", "HSE section completed for site reports",
                        lambda f: f.get("HSE") is not None)]
    r = evaluate(spec(manual_rules=rules), doc(), CAL)
    f = next(f for f in r.findings if f.check == "C6")
    assert f.reference == "QM-03 §4.2"
    assert r.verdict == "RETURNED_FOR_REVISION"


def test_minor_quality_only_accepted_with_observations():
    d = doc(fields={"B2": 1, "B3": "x", "B4": 1.0, "B5": 2.0, "B6": 3.0, "B10": 6.0, "C9": "???"})
    r = evaluate(spec(), d, CAL)
    assert r.verdict == "ACCEPTED_WITH_OBSERVATIONS"
    assert r.check_results["C7"] == "QUALITY_DEFECTS"


def test_unreadable_short_circuits():
    r = evaluate(spec(), doc(unreadable=True), CAL)
    assert r.verdict == "UNREADABLE"
    assert r.check_results["C3"] == "NOT_EVALUATED"


def test_confidential_reduced_set_never_returns():
    d = doc(confidential=True, fields={})
    r = evaluate(spec(), d, CAL)
    assert r.verdict == "RECEIVED_ON_TIME"
    assert r.check_results["C3"] == "NOT ASSESSED — CONFIDENTIAL SCOPE"
    assert r.check_results["C2"] == "CORRECT_FORM (filename only)"
    late = evaluate(spec(), doc(confidential=True, received_at=datetime(2026, 8, 17, 9, 0)), CAL)
    assert late.verdict == "RECEIVED_LATE"
    missing = evaluate(spec(), doc(confidential=True, attachment_name=None), CAL)
    assert missing.verdict == "NOT_RECEIVED"
