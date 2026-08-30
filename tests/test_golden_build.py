"""Pending golden-set cases from the archive — §13.1, D-03.

The Phase 1 gate reported the golden set as BLOCKED, reason "no judged
cases and no pending cases", owner Ahmed Diab. The harness could issue
batches, read them back and run the gate — and nothing ever put a case
into `pending/`. The block was a missing step, and naming the CEO as its
owner sent the bill to the wrong person.
"""

from datetime import date, datetime
from pathlib import Path

from control.golden_build import build, due_for, render, to_cases

TODAY = date(2026, 8, 30)


def obligation(**over):
    row = dict(id="OPS-FA-001", name="Monthly finance ledger",
               owner="accounts@ubcsis.com", cadence="monthly",
               due="day 12 17:00", form="", approved_by_ceo="ahmed@ubcsis.com")
    row.update(over)
    return row


FOLDERS = {"accounts@ubcsis.com": ["8. Finance"]}


def documents(count=6, folder="8. Finance/Y2025"):
    return [(Path(f"{folder}/ledger-{i}.xlsx"),
             datetime(2025, 1 + i, 15, 10, 0)) for i in range(count)]


def test_documents_are_matched_by_owner_and_folder_not_by_name():
    """A set assembled by fuzzy name matching puts the wrong document
    under the wrong obligation, and the CEO then judges a mismatch
    rather than the engine."""
    rows = build([obligation()], documents() + [
        (Path("9. HR Department/payroll-1.xlsx"), datetime(2025, 3, 1))],
        FOLDERS)
    assert len(rows[0].documents) == 6
    assert all("8. Finance" in str(p) for p, _ in rows[0].documents)


def test_an_obligation_with_no_documents_says_so():
    rows = build([obligation(owner="hse@ubcsis.com")], documents(), FOLDERS)
    assert rows[0].documents == []
    text = "\n".join(render(rows, [], TODAY))
    assert "no document on the drive is filed under this obligation" in text


def test_cases_are_spread_across_the_series_not_taken_from_one_end():
    """§13.1 asks for "a realistic spread of good and defective work —
    not a curated sample of clean ones", and the most recent files of a
    series are the ones most likely to be clean."""
    rows = build([obligation()], documents(count=11), FOLDERS,
                 per_obligation=4)
    months = [when.month for _, when in rows[0].documents]
    assert months == sorted(months)
    assert months[0] == 1 and months[-1] > 6


def test_a_case_carries_no_expected_verdict_at_all():
    """D-03. Not a blank verdict — absent. A case with an empty expected
    outcome is one edit away from carrying Control's."""
    rows = build([obligation()], documents(count=2), FOLDERS)
    cases = to_cases(rows, [obligation()])
    assert cases and all("expected" not in case for case in cases)


def test_a_case_records_which_checks_it_could_exercise():
    """The CEO is being asked to judge a document. Which checks the
    engine could even run against it changes what his verdict means, so
    it goes on the case rather than in a summary that gets skimmed."""
    rows = build([obligation()], documents(count=1), FOLDERS)
    case = to_cases(rows, [obligation()])[0]
    assert case["checks_available"] == ["C1"]
    assert "C2" in case["checks_unavailable"]
    assert "C6" in case["checks_unavailable"]


def test_the_summary_refuses_to_call_a_c1_only_set_a_passing_gate():
    """§13.1's gate counts false positives per check. A check that
    cannot run cannot produce one, so a set built only on C1 would pass
    the gate without testing what the gate is for — a test the engine
    cannot fail, which §13.1 names as the failure the unanchored method
    exists to prevent."""
    rows = build([obligation()], documents(count=2), FOLDERS)
    # Normalised: the summary is wrapped for a terminal, so a phrase
    # that matters can sit across two lines.
    text = " ".join(" ".join(render(rows, to_cases(rows, [obligation()]),
                                    TODAY)).split())
    assert "cannot run: C2, C3, C4, C5, C6, C7" in text
    assert "a test the engine cannot fail" in text
    assert "LIVE 0" in text


def test_the_deadline_is_the_documents_own_period_not_the_next_one():
    """`parse_due` answers "when is this next due", which for a document
    filed in March 2025 puts the deadline in the future and makes C1
    unjudgeable — ten rows of the CEO's time spent on nothing."""
    assert due_for(obligation(), datetime(2025, 3, 20)) == "2025-03-12T17:00"
    assert due_for(obligation(due="sunday 10:00", cadence="weekly"),
                   datetime(2025, 3, 20)) == "2025-03-23T10:00"


def test_an_uncomputable_deadline_is_left_empty_rather_than_invented():
    assert due_for(obligation(due="day 31 17:00"),
                   datetime(2025, 2, 10)) == ""
    assert due_for(obligation(due="NOT ESTABLISHED"),
                   datetime(2025, 2, 10)) == ""


def test_an_unapproved_obligation_builds_no_cases():
    """§6: an unapproved row is a proposal. Judging documents against
    one would put the CEO's ruling behind an obligation he never
    adopted."""
    rows = build([obligation(approved_by_ceo=None)], documents(), FOLDERS)
    assert rows == []


def test_the_drive_walk_is_materialised_before_it_is_counted(tmp_path):
    """`series.walk` yields, and the register proposal counted it with
    len(). So on any machine with no Stage B inventory — which is every
    machine before its first scan — the whole register proposal reported
    as a failed step and was skipped, inside a runner whose point is
    that it does not stop halfway.
    """
    from control.discovery import series

    (tmp_path / "8. Finance").mkdir()
    (tmp_path / "8. Finance" / "ledger.xlsx").write_text("x", encoding="utf-8")
    rows = list(series.walk(tmp_path))
    assert len(rows) >= 1
