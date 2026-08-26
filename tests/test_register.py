"""Stage D proposals to an approved register — §6.

*"Phase 0 ends when the CEO approves the obligation register."*

That sentence had no mechanism. Stage D wrote candidates to a markdown
report, the engine read an empty `obligations.yaml`, and nothing joined
them — so Control tracked zero class 3 obligations, had nothing to
remind anyone about, and had no submissions to build a golden set from.

The tests here are about the join keeping its two halves apart.
Proposing is inference. Approving is a decision, it carries a name, and
without it nothing is tracked.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from control.discovery.analyse import ObligationCandidate
from control.register import approve, propose, render_worksheet, to_rows

TODAY = date(2026, 8, 19)
ROSTER = {"hse@ubcsis.com", "a.elsayed@ubcsis.com", "hadeer@ubcsis.com"}


def candidate(**over):
    row = dict(
        sender="hse@ubcsis.com", subject_template="weekly hse report",
        occurrences=40, first_seen="01-Jan-2025", last_seen="01-Aug-2026",
        median_gap_days=7.0, cadence="weekly", confidence="HIGH",
        regular=True, attachment_rate=0.95, example_attachments=["FRM-HSE.xlsx"],
        pattern_kind="RECURRING", modal_weekday="sunday",
        modal_day_of_month=0, modal_hour=10,
    )
    row.update(over)
    return ObligationCandidate(**row)


# ---- what becomes a proposal ------------------------------------------

def test_a_weekly_arrival_becomes_a_computable_deadline():
    proposals, _ = propose([candidate()], ROSTER)
    assert len(proposals) == 1
    assert proposals[0].cadence == "weekly"
    assert proposals[0].due == "sunday 10:00"
    assert proposals[0].usable


def test_the_due_expression_the_engine_will_actually_parse():
    """A proposal the loader then refuses is not a proposal, it is a
    gap dressed as one."""
    from control.loader import parse_due

    proposals, _ = propose([candidate()], ROSTER)
    due, problem = parse_due(proposals[0].due, proposals[0].cadence,
                             date(2026, 8, 19))
    assert due is not None and problem == ""


def test_a_monthly_arrival_uses_the_observed_day():
    proposals, _ = propose(
        [candidate(median_gap_days=30.0, modal_weekday="", modal_day_of_month=5,
                   modal_hour=9)], ROSTER)
    assert proposals[0].due == "day 5 09:00"


# ---- what is refused a date -------------------------------------------

def test_a_weekly_arrival_on_no_consistent_day_gets_no_date():
    """§2.1. A deadline that alerts confidently on the wrong day teaches
    people the system is wrong, and a tie in the timestamps is not a
    day."""
    proposals, _ = propose([candidate(modal_weekday="")], ROSTER)
    assert proposals[0].due == ""
    assert "no consistent day" in proposals[0].problem
    assert not proposals[0].usable


def test_a_day_beyond_the_28th_is_refused_rather_than_clamped():
    """Not every month has a 31st, and choosing which day it becomes is
    a decision about a deadline."""
    proposals, _ = propose(
        [candidate(median_gap_days=30.0, modal_weekday="",
                   modal_day_of_month=31)], ROSTER)
    assert proposals[0].due == ""
    assert "not every month has one" in proposals[0].problem


def test_a_fortnightly_gap_is_reported_rather_than_rounded():
    proposals, _ = propose([candidate(median_gap_days=14.0)], ROSTER)
    assert proposals[0].due == ""
    assert "between weekly and monthly" in proposals[0].problem


def test_an_unrecognisable_gap_says_what_it_measured():
    proposals, _ = propose([candidate(median_gap_days=200.0)], ROSTER)
    assert "median gap of 200 days" in proposals[0].problem


# ---- what is not proposed at all --------------------------------------

def test_a_bulk_send_is_not_an_obligation():
    """Hundreds of messages on one day is a mailshot with a median gap
    of zero."""
    proposals, declined = propose(
        [candidate(pattern_kind="BULK")], ROSTER)
    assert proposals == []
    assert declined["bulk send"] == 1


def test_a_conversation_is_not_an_obligation():
    proposals, declined = propose(
        [candidate(pattern_kind="THREAD")], ROSTER)
    assert proposals == []
    assert declined["conversation"] == 1


def test_a_recurring_subject_with_no_attachment_is_a_notification():
    proposals, declined = propose(
        [candidate(attachment_rate=0.1)], ROSTER)
    assert proposals == []
    assert declined["no attachment"] == 1


def test_a_sender_off_the_roster_is_not_given_an_obligation():
    """An obligation owned by an address that is not a person is not an
    obligation; it is a system sending mail."""
    proposals, declined = propose(
        [candidate(sender="noreply@vendor.com")], ROSTER)
    assert proposals == []
    assert declined["sender not on the roster"] == 1


def test_low_confidence_candidates_are_held_back_by_default():
    proposals, declined = propose([candidate(confidence="LOW")], ROSTER)
    assert proposals == []
    assert declined["below confidence"] == 1


def test_what_was_declined_is_counted_not_dropped():
    """A register that showed only what it proposed would read as a
    complete reading of the archive."""
    _, declined = propose(
        [candidate(pattern_kind="BULK"), candidate(pattern_kind="THREAD"),
         candidate(confidence="LOW")], ROSTER)
    assert sum(declined.values()) == 3
    text = render_worksheet([], declined, TODAY)
    assert "What was not proposed, and why" in text
    assert "bulk send" in text


# ---- approval is a decision, and only that ----------------------------

@pytest.fixture
def files(tmp_path):
    proposals, _ = propose(
        [candidate(), candidate(sender="a.elsayed@ubcsis.com",
                                subject_template="daily site report",
                                modal_weekday="")], ROSTER)
    proposals_path = tmp_path / "PROPOSED.yaml"
    proposals_path.write_text(
        yaml.safe_dump({"obligations": to_rows(proposals)},
                       allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    obligations_path = tmp_path / "obligations.yaml"
    obligations_path.write_text("obligations: []\n", encoding="utf-8")
    return proposals_path, obligations_path


def test_a_proposal_file_on_its_own_tracks_nothing(files):
    """`approved_by_ceo` is null until a human sets it, and
    `build_obligations` refuses every row without it — so a proposal
    file written by mistake tracks nothing rather than everything."""
    from control.loader import build_obligations

    proposals_path, _ = files
    data = yaml.safe_load(proposals_path.read_text(encoding="utf-8"))
    assert all(row["approved_by_ceo"] is None for row in data["obligations"])

    specs, tracked, gaps = build_obligations(
        data, {"people": []}, date(2026, 8, 19))
    assert specs == {} and tracked == []
    assert any("not approved by the CEO" in g for g in gaps)


def test_approving_writes_the_name_and_ends_phase_0(files):
    proposals_path, obligations_path = files
    approved, _ = approve(proposals_path, obligations_path,
                          "ahmed@ubcsis.com")
    assert len(approved) == 1
    live = yaml.safe_load(obligations_path.read_text(encoding="utf-8"))
    assert live["obligations"][0]["approved_by_ceo"] == "ahmed@ubcsis.com"


def test_an_approved_register_is_actually_tracked(files):
    """End to end, and the only measure that matters: does an obligation
    come out of the other end?"""
    from control.loader import build_obligations

    proposals_path, obligations_path = files
    approve(proposals_path, obligations_path, "ahmed@ubcsis.com")

    people = {"people": [{"email": "hse@ubcsis.com", "name": "Mostafa Hassan",
                          "reports_to": "ghareeb@ubcsis.com", "tier": 2}]}
    specs, tracked, _ = build_obligations(
        yaml.safe_load(obligations_path.read_text(encoding="utf-8")),
        people, date(2026, 8, 19))
    assert len(tracked) == 1
    assert tracked[0].owner == "hse@ubcsis.com"


def test_a_proposal_with_no_date_is_never_approved(files):
    """An approved row that tracks nothing is worse than an unapproved
    one, because it looks like coverage."""
    proposals_path, obligations_path = files
    approved, skipped = approve(proposals_path, obligations_path,
                                "ahmed@ubcsis.com")
    assert len(skipped) == 1
    assert "no computable due date" in skipped[0]
    assert "no consistent day" in skipped[0]


def test_approving_a_named_subset_leaves_the_rest(files):
    proposals_path, obligations_path = files
    approved, _ = approve(proposals_path, obligations_path,
                          "ahmed@ubcsis.com", only={"OPS-HSE-001"})
    assert approved == ["OPS-HSE-001"]


def test_approving_twice_does_not_duplicate(files):
    proposals_path, obligations_path = files
    approve(proposals_path, obligations_path, "ahmed@ubcsis.com")
    approved, skipped = approve(proposals_path, obligations_path,
                                "ahmed@ubcsis.com")
    assert approved == []
    assert any("already in the register" in item for item in skipped)


def test_approval_never_removes_what_was_already_there(files):
    proposals_path, obligations_path = files
    obligations_path.write_text(
        yaml.safe_dump({"obligations": [
            {"id": "OPS-EXISTING-001", "class": 3, "name": "kept",
             "owner": "hadeer@ubcsis.com", "cadence": "weekly",
             "due": "monday 09:00", "approved_by_ceo": "ahmed@ubcsis.com"}]},
            allow_unicode=True, sort_keys=False), encoding="utf-8")

    approve(proposals_path, obligations_path, "ahmed@ubcsis.com")

    live = yaml.safe_load(obligations_path.read_text(encoding="utf-8"))
    assert any(r["id"] == "OPS-EXISTING-001" for r in live["obligations"])


# ---- the seam between the two halves ----------------------------------

def test_a_not_established_due_is_refused_like_an_empty_one(tmp_path):
    """The seam that would have let every dateless row through.

    `register_proposal` writes `due: "NOT ESTABLISHED"` rather than a
    blank, and a presence check calls that truthy. Every proposal with
    no deadline at all would have been approved, and an approved row
    that tracks nothing is worse than an unapproved one because it
    looks like coverage.
    """
    proposals_path = tmp_path / "PROPOSED.yaml"
    proposals_path.write_text(yaml.safe_dump({"obligations": [
        {"id": "OPS-DRIVE-001", "class": 3, "name": "Progress report",
         "owner": "a.elsayed@ubcsis.com", "cadence": "monthly",
         "due": "NOT ESTABLISHED", "approved_by_ceo": None},
    ]}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    obligations_path = tmp_path / "obligations.yaml"
    obligations_path.write_text("obligations: []\n", encoding="utf-8")

    approved, skipped = approve(proposals_path, obligations_path,
                                "ahmed@ubcsis.com")
    assert approved == []
    assert "no computable due date" in skipped[0]
    live = yaml.safe_load(obligations_path.read_text(encoding="utf-8"))
    assert live["obligations"] == []


def test_the_shipped_starter_register_is_approvable_and_tracks(tmp_path):
    """The register that ships in `config/obligations.yaml`.

    The CEO asked for a system that is up and running, not for six rows
    to hand-edit. That makes this the test that matters: does the file
    Control assigned from the archive actually come out the other end as
    tracked obligations when one command stamps it?

    It runs against the real file rather than a fixture, because a
    starter register that parses in a test and not in `config/` is the
    same as no starter register.
    """
    import shutil

    from control.loader import build_obligations
    from control.register import approve_in_place

    root = Path(__file__).resolve().parents[1]
    shipped = root / "config" / "obligations.yaml"
    obligations_path = tmp_path / "obligations.yaml"
    shutil.copy(shipped, obligations_path)

    before = yaml.safe_load(obligations_path.read_text(encoding="utf-8"))
    assert before["obligations"], "the starter register is empty"
    assert all(row["approved_by_ceo"] is None for row in before["obligations"]), \
        "a row ships pre-approved — §6 makes that approval the CEO's act"

    specs, tracked, gaps = build_obligations(before, {"people": []}, TODAY)
    assert tracked == [], "unapproved rows are tracked"

    approved, skipped = approve_in_place(obligations_path, "ahmed@ubcsis.com")
    assert len(approved) == len(before["obligations"])
    assert skipped == []

    after = yaml.safe_load(obligations_path.read_text(encoding="utf-8"))
    specs, tracked, gaps = build_obligations(after, {"people": []}, TODAY)
    assert len(tracked) == len(after["obligations"])


def test_approving_in_place_keeps_the_comments(tmp_path):
    """A register that loses the record of its own provenance the first
    time it is approved is the §1.1 failure, arriving by a helpful door.

    Every date in the starter register was assigned by Control rather
    than observed, and the header is where that is written down.
    `yaml.safe_dump` drops every comment in a file, so the approval path
    edits lines instead.
    """
    from control.register import approve_in_place

    obligations_path = tmp_path / "obligations.yaml"
    obligations_path.write_text(
        "# NOT ONE OF THESE DEADLINES WAS OBSERVED\n"
        "obligations:\n"
        "  - id: OPS-TO-001\n"
        "    class: 3\n"
        "    name: Weekly Site Progress Report\n"
        "    owner: shymaa@ubcsis.com\n"
        "    cadence: weekly\n"
        "    due: sunday 10:00\n"
        "    approved_by_ceo: null\n", encoding="utf-8")

    approve_in_place(obligations_path, "ahmed@ubcsis.com")

    text = obligations_path.read_text(encoding="utf-8")
    assert "# NOT ONE OF THESE DEADLINES WAS OBSERVED" in text
    assert "approved_by_ceo: ahmed@ubcsis.com" in text


def test_approving_in_place_leaves_a_dateless_row_unapproved(tmp_path):
    from control.register import approve_in_place

    obligations_path = tmp_path / "obligations.yaml"
    obligations_path.write_text(
        "obligations:\n"
        "  - id: OPS-DRIVE-001\n"
        "    class: 3\n"
        "    name: Progress report\n"
        "    owner: a.elsayed@ubcsis.com\n"
        "    cadence: monthly\n"
        "    due: NOT ESTABLISHED\n"
        "    approved_by_ceo: null\n", encoding="utf-8")

    approved, skipped = approve_in_place(obligations_path, "ahmed@ubcsis.com")
    assert approved == []
    assert "no computable due date" in skipped[0]
    assert "approved_by_ceo: null" in obligations_path.read_text(
        encoding="utf-8")


def test_approving_in_place_twice_does_not_restamp(tmp_path):
    from control.register import approve_in_place

    obligations_path = tmp_path / "obligations.yaml"
    obligations_path.write_text(
        "obligations:\n"
        "  - id: OPS-TO-001\n"
        "    class: 3\n"
        "    name: Weekly Site Progress Report\n"
        "    owner: shymaa@ubcsis.com\n"
        "    cadence: weekly\n"
        "    due: sunday 10:00\n"
        "    approved_by_ceo: null\n", encoding="utf-8")

    approve_in_place(obligations_path, "ahmed@ubcsis.com")
    approved, skipped = approve_in_place(obligations_path, "ghareeb@ubcsis.com")
    assert approved == []
    assert "already approved by ahmed@ubcsis.com" in skipped[0]


def test_a_real_due_from_the_drive_builder_is_approved(tmp_path):
    """The other side of it: a proposal the engine can actually parse
    goes through, so the refusal is a filter and not a wall."""
    proposals_path = tmp_path / "PROPOSED.yaml"
    proposals_path.write_text(yaml.safe_dump({"obligations": [
        {"id": "OPS-DRIVE-002", "class": 3, "name": "Weekly progress",
         "owner": "a.elsayed@ubcsis.com", "cadence": "weekly",
         "due": "sunday 10:00", "approved_by_ceo": None},
    ]}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    obligations_path = tmp_path / "obligations.yaml"
    obligations_path.write_text("obligations: []\n", encoding="utf-8")

    approved, _ = approve(proposals_path, obligations_path,
                          "ahmed@ubcsis.com")
    assert approved == ["OPS-DRIVE-002"]
