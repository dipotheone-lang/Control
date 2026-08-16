"""An interim position must not become permanent by silence.

D-06 (16-Aug-2026): authority thresholds stay at zero — every
commitment itemised — while a month of real volume is observed. That is
a legitimate choice. Letting its review date pass unremarked would not
be.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from control.db import init_db
from control.report import HorizonItem, interim_reviews_due, weekly_report

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "control.db")
    yield c
    c.close()


def test_repo_config_records_the_interim_position():
    data = yaml.safe_load((REPO_CONFIG / "authority.yaml").read_text(encoding="utf-8"))
    interim = data["interim"]
    assert interim["active"] is True
    assert interim["decided"] == date(2026, 8, 16)
    assert interim["review_due"] == date(2026, 9, 16)
    # Zero means itemise everything — the conservative default is live,
    # not switched off (§3.2).
    assert data["thresholds"]["ceo_weekly_itemisation"] == 0


def test_silent_well_before_the_review():
    assert interim_reviews_due(REPO_CONFIG, date(2026, 8, 20)) == []


def test_warns_in_the_week_before():
    due = interim_reviews_due(REPO_CONFIG, date(2026, 9, 12))
    assert len(due) == 1
    assert "reviews 16-Sep-2026" in due[0]
    assert "4 days" in due[0]


def test_escalates_once_overdue():
    due = interim_reviews_due(REPO_CONFIG, date(2026, 9, 30))
    assert len(due) == 1
    assert "14 day(s) past its 16-Sep-2026 review" in due[0]
    assert "still being itemised" in due[0]


def test_inactive_interim_is_silent(tmp_path):
    (tmp_path / "authority.yaml").write_text(
        yaml.safe_dump({"interim": {"active": False, "review_due": "2026-01-01"}}),
        encoding="utf-8")
    assert interim_reviews_due(tmp_path, date(2026, 9, 30)) == []


def test_missing_or_broken_config_does_not_crash_the_report(tmp_path):
    assert interim_reviews_due(tmp_path, date(2026, 9, 30)) == []
    (tmp_path / "authority.yaml").write_text("{{ not yaml", encoding="utf-8")
    assert interim_reviews_due(tmp_path, date(2026, 9, 30)) == []


def test_review_appears_in_the_weekly_report(conn, tmp_path):
    report = weekly_report(
        conn, as_of=date(2026, 9, 30), horizon=[], open_items=[],
        open_decisions=[], control_root=tmp_path, config_dir=REPO_CONFIG)
    assert "past its 16-Sep-2026 review" in report["body"]
    assert "D-06" in report["body"]


def test_weekly_report_still_works_without_a_config_dir(conn, tmp_path):
    report = weekly_report(
        conn, as_of=date(2026, 9, 30), horizon=[], open_items=[],
        open_decisions=[], control_root=tmp_path)
    assert "DECISIONS REQUIRED" in report["body"]
