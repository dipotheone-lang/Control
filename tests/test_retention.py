"""Retention — §12.5, execution order B11.

*"Deletion mechanism — does not exist; build before first retention
falls due. Retention schedule is a document without it."*

It is still a document, and these tests are mostly about why. §5.2
makes the record tables append-only with triggers, and §12.5 requires
deletion. For `submissions`, `findings`, `anomalies`, `disputes` and
`external_threads` — most of the personal data the schedule covers —
both cannot hold. Control does not pick between two charter rules
(§1.3); it measures the problem and raises it.

The asymmetry here runs opposite to everywhere else in this system.
Elsewhere, when in doubt, flag. Here, when in doubt, keep: deletion is
the one operation that cannot be undone, and removing a commercial book
before its statutory minimum is a breach that a report cannot fix.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from control.db import init_db
from control.retention import blockers, cutoff, render, survey

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
TODAY = date(2026, 8, 20)


@pytest.fixture(scope="module")
def config():
    return yaml.safe_load(
        (REPO_CONFIG / "retention.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "control.db")
    yield c
    c.close()


def _aged_submission(conn, days: int):
    conn.execute(
        "INSERT INTO submissions (obligation_id, source, posted_at)"
        " VALUES ('OPS-X', 'LIVE', ?)",
        ((date.today() - timedelta(days=days)).isoformat(),))
    conn.commit()


# ---- the conflict this exists to surface ------------------------------

def test_an_expired_record_is_reported_as_undeletable(conn, tmp_path, config):
    """The finding. §5.2 blocks DELETE with a trigger; §12.5 requires
    it. Both are in the charter and neither is Control's to overrule."""
    _aged_submission(conn, days=1000)
    found = survey(conn, tmp_path, config, TODAY)
    submissions = next(d for d in found if d.class_id == "SUBMISSIONS")
    assert submissions.rows == 1
    what, why = next(b for b in submissions.blocked if "submissions" in b[0])
    assert "append-only" in why
    assert "blocked by a trigger, not by convention" in why
    assert "cannot both hold" in why


def test_the_conflict_is_named_as_needing_a_decision(config):
    """Three resolutions exist and none is Control's to pick — §1.3
    resolves a conflict by quoting the clause and escalating, never by
    choosing."""
    item = next(u for u in config["unbuilt"]
                if u["id"] == "APPEND_ONLY_CONFLICT")
    assert set(item["affects"]) == {
        "submissions", "findings", "anomalies", "disputes",
        "external_threads"}
    assert "none is Control's to pick" in " ".join(item["needs"].split())


def test_the_database_really_does_refuse(conn):
    """Not a claim about the schema — the schema, asked."""
    import sqlite3

    _aged_submission(conn, days=1000)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM submissions")


# ---- nothing is deleted, and the reasons are ordered ------------------

def test_an_unconfirmed_schedule_blocks_every_deletion(config):
    """O-10. Deleting on a schedule nobody qualified has checked is
    irreversible in the direction that matters."""
    reasons = blockers(config)
    assert any("not confirmed by counsel (O-10)" in r for r in reasons)
    assert any("not recoverable" in r for r in reasons)


def test_a_missing_schedule_says_retention_does_not_exist_here():
    reasons = blockers(None)
    assert len(reasons) == 1
    assert "retention.yaml is missing" in reasons[0]
    assert "does not exist on this machine" in reasons[0]


def test_the_statutory_floor_applies_per_class_not_to_everything(config):
    """The error this pins was mine, and it pushed the wrong way.

    Applying a five-year floor to every class would hold an anomaly
    flag for five years because a tax rule about ledgers says so —
    personal data kept longer than needed, which is the PDPL failure
    §12.5 exists to prevent, arriving from the opposite direction.
    """
    floored = [c["id"] for c in config["classes"]
               if c.get("statutory_floor_applies")]
    assert floored == ["SUBMITTED_FILES"]
    reasons = blockers(config)
    floor_note = next(r for r in reasons if "statutory floor" in r)
    assert "SUBMITTED_FILES" in floor_note
    assert "ANOMALIES" not in floor_note
    assert "commercial or supporting records" in floor_note


def test_a_confirmed_schedule_still_refuses_below_the_floor(config):
    """A schedule cannot authorise less than the law requires, so
    counsel confirming the rest does not release this one."""
    confirmed = {**config, "confirmed_by_counsel": True}
    reasons = blockers(confirmed)
    assert not [r for r in reasons if "O-10" in r]
    assert any("statutory floor" in r for r in reasons)


# ---- the audit log is never swept -------------------------------------

def test_the_audit_log_is_never_swept_at_any_age(conn, tmp_path, config):
    """Deletion IS a chain break and a chain break is a critical
    incident (§13.3). Ageing the log out is a decision taken knowing
    that, not a sweep that happens on a schedule."""
    logs = tmp_path / "logs"
    logs.mkdir()
    old = logs / "2015-01-01.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    import os
    ancient = (date(2015, 1, 1) - date(1970, 1, 1)).days * 86400
    os.utime(old, (ancient, ancient))

    found = survey(conn, tmp_path, config, TODAY)
    audit = next(d for d in found if d.class_id == "AUDIT")
    assert audit.files == 1
    assert audit.deletable_paths == [], "never a candidate, whatever its age"
    assert any("chain break" in why for _, why in audit.blocked)


# ---- what the report refuses to imply ---------------------------------

def test_an_empty_result_reads_as_young_not_as_clean(config):
    text = render([], blockers(config), config, TODAY)
    assert "That is a young system rather than a clean one" in text
    assert "reads empty until the first class ages out" in text


def test_the_report_leads_with_nothing_being_deleted(config):
    text = render([], blockers(config), config, TODAY)
    assert text.index("Nothing was deleted") < text.index("Past its period")


def test_the_unbuilt_items_reach_the_page(config):
    text = render([], blockers(config), config, TODAY)
    assert "What cannot be built without a decision" in text
    assert "APPEND_ONLY_CONFLICT" in text
    assert "DISPUTE_SPLIT" in text


# ---- the arithmetic ----------------------------------------------------

def test_a_month_is_not_thirty_days():
    """Twenty-four "months" at 30 days each is 21 days short of two
    years, and the direction of that error decides whether a record
    goes before its minimum."""
    assert cutoff(24, date(2026, 8, 20)) == date(2024, 8, 20)
    assert cutoff(12, date(2026, 8, 20)) == date(2025, 8, 20)


def test_a_record_inside_its_period_is_not_reported(conn, tmp_path, config):
    _aged_submission(conn, days=30)
    found = survey(conn, tmp_path, config, TODAY)
    assert not [d for d in found
                if d.class_id == "SUBMISSIONS" and d.rows]
