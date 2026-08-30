"""One page of what the runs actually found — for a go/no-go decision.

The question of whether to continue this project had been resting on a
summary of a summary, because the numbers live in six places: the
register, the database, the Stage C cache, the config, the discovery
folder and the gate.
"""

import json
from datetime import date

from control.status import build, render

TODAY = date(2026, 8, 30)


def root(tmp_path, obligations=None, statutory=None):
    import yaml

    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "obligations.yaml").write_text(
        yaml.safe_dump({"obligations": obligations or []}), encoding="utf-8")
    (tmp_path / "config" / "statutory-calendar.yaml").write_text(
        yaml.safe_dump({"obligations": statutory or []}), encoding="utf-8")
    return tmp_path


def test_an_absent_number_is_not_reported_as_a_zero(tmp_path):
    """The distinction the whole page exists for. "No guarantees in the
    register" reads the same whether the registers were never populated
    or the company has none, and those need opposite answers (§1.1)."""
    text = render(build(root(tmp_path), TODAY), TODAY)
    assert "NOT CREATED" in text          # database, never reached
    assert "NEVER RUN" in text            # Stage C, never completed
    assert "absent, not empty" in text


def test_class_1_usability_agrees_with_the_engine(tmp_path):
    """Decided by the engine's own parser, not a second reading of the
    same field — and the field is `rule`, not `due`, which a
    re-implementation got wrong on the first attempt. A status page that
    disagrees with the engine about what is tracked is worse than none.
    """
    from control.loader import parse_due

    statutory = [
        {"id": "STAT-VAT", "cadence": "monthly",
         "rule": "end of the following month, -5 working days"},
        {"id": "STAT-PAYROLL", "cadence": "quarterly",
         "rule": "UNVERIFIED — quarterly dates pending"},
    ]
    text = render(build(root(tmp_path, statutory=statutory), TODAY), TODAY)
    assert "2   class 1 statutory obligations" in text
    assert "1   with a date Control can count down to" in text

    engine = sum(1 for r in statutory
                 if parse_due(r["rule"], r["cadence"], TODAY)[0] is not None)
    assert engine == 1


def test_an_unapproved_obligation_is_counted_apart(tmp_path):
    """§6: an unapproved row is a proposal and tracks nothing. Counting
    it with the approved ones would report coverage that does not
    exist."""
    rows = [{"id": "A", "approved_by_ceo": "ahmed@ubcsis.com",
             "date_basis": "assigned_by_control"},
            {"id": "B", "approved_by_ceo": None}]
    text = render(build(root(tmp_path, obligations=rows), TODAY), TODAY)
    assert "2   class 3 obligations in the register" in text
    assert "1   approved by the CEO" in text


def test_deadlines_control_assigned_are_named_as_such(tmp_path):
    rows = [{"id": "A", "approved_by_ceo": "ahmed@ubcsis.com",
             "date_basis": "assigned_by_control"}]
    text = render(build(root(tmp_path, obligations=rows), TODAY), TODAY)
    assert "1   whose deadline Control assigned rather than observed" in text


def test_the_stage_c_cache_is_read_rather_than_rescanned(tmp_path):
    cache = tmp_path / "data" / "stage-c-cache"
    cache.mkdir(parents=True)
    (cache / "a.json").write_text(json.dumps({
        "outcome": "terms", "d05": True,
        "terms": [{"found_date": "2026-12-31"}, {"found_date": ""}],
        "ocr": {"attempted": True, "read": True, "confidence": 71.4}}),
        encoding="utf-8")
    text = render(build(root(tmp_path), TODAY), TODAY)
    assert "1   documents scanned" in text
    assert "2   commercial terms found" in text
    assert "1   of those, carrying a date" in text
    assert "median confidence 71.4" in text


def test_it_recommends_nothing(tmp_path):
    """§15 keeps the decision with the CEO, and this is a larger version
    of the same decision."""
    text = render(build(root(tmp_path), TODAY), TODAY).lower()
    for word in ("recommend", "you should", "we should", "suggest"):
        assert word not in text


def test_out_of_scope_sections_are_labelled_not_dropped(tmp_path):
    """The page the narrowing was decided on has to survive it.

    Dropping the out-of-scope sections would be the same mistake in a new
    place: "no guarantees in the register" and "guarantees are not this
    system's job any more" are different facts, and showing only the
    second would hide an exposure that has not moved (§3.2).
    """
    text = render(build(root(tmp_path), TODAY, "STATUTORY_ONLY"), TODAY)

    assert "CLASS 1 — STATUTORY" in text
    assert "OUT OF SCOPE (D-15), still reported" in text
    # Still measured: the section reports its state under the label
    # rather than being replaced by the label.
    assert "no run has reached it — this is absent, not empty" in text
    assert "narrowing the software does not narrow the risk" in text


def test_class_1_is_never_labelled_out_of_scope(tmp_path):
    """It is the one thing the narrowed scope operates on."""
    text = render(build(root(tmp_path), TODAY, "STATUTORY_ONLY"), TODAY)
    heading = next(line for line in text.splitlines()
                   if line.startswith("CLASS 1"))
    assert "OUT OF SCOPE" not in heading


def test_the_full_scope_labels_nothing(tmp_path):
    text = render(build(root(tmp_path), TODAY), TODAY)
    assert "OUT OF SCOPE" not in text
    assert "OPERATING_SCOPE" not in text
