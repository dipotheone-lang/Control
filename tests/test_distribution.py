"""Report distribution by phase — decision D-13 (16-Aug-2026).

Narrowed to CEO and COO for Phase 2, widening at the gate.

The reasoning is about first impressions, not secrecy. During the 30
supervised days the report carries Control's own false positives — that
is what the phase is for — and §13.1 warns that a system which wrongly
returns correct work loses authority permanently, with one chance to
make that impression.

So the test that matters is the one asserting this stays a narrowing by
PHASE and not a private pilot: the report says why the list is short,
and Control never widens or narrows it on its own.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from control import HaltError
from control.db import init_db
from control.report import report_recipients, weekly_report

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
CEO, COO = "ahmed@ubcsis.com", "ghareeb@ubcsis.com"


def test_phase_2_narrows_to_two():
    data = yaml.safe_load(
        (REPO_CONFIG / "distribution.yaml").read_text(encoding="utf-8"))
    recipients, note = report_recipients(data)
    assert recipients == [CEO, COO]
    assert "narrowed to CEO and COO for Phase 2" in note


def test_the_narrowing_carries_its_reason():
    """A recipient set that changed for a reason should say the reason,
    not look like a configuration accident."""
    data = yaml.safe_load(
        (REPO_CONFIG / "distribution.yaml").read_text(encoding="utf-8"))
    _, note = report_recipients(data)
    assert "own false positives" in note
    assert "widens to the §11 default at the Phase 2 gate" in note
    assert "not a private pilot" in note


def test_steady_state_restores_the_charter_default():
    data = yaml.safe_load(
        (REPO_CONFIG / "distribution.yaml").read_text(encoding="utf-8"))
    data["management_reports"]["phase"] = "STEADY_STATE"
    recipients, note = report_recipients(data)
    assert recipients == [CEO, COO, "accounts@ubcsis.com", "info@ubcsis.com"]
    assert note == ""          # nothing to explain once it is the default


def test_an_unknown_phase_halts_rather_than_guessing():
    with pytest.raises(HaltError) as e:
        report_recipients({"management_reports": {"phase": "PILOT"}})
    assert "D-13" in str(e.value)


def test_missing_config_falls_back_to_steady_state_not_to_silence():
    """An absent phase must not shrink the distribution by accident."""
    recipients, _ = report_recipients(
        {"management_reports": {"default_recipients": [CEO, COO]}})
    assert recipients == [CEO, COO]
    assert report_recipients({}) == ([], "")


def test_the_weekly_report_discloses_the_narrowing():
    conn = init_db(Path("/tmp") / "d13.db") if False else init_db(":memory:")
    try:
        report = weekly_report(
            conn, as_of=date(2026, 8, 20), horizon=[], open_items=[],
            open_decisions=[], control_root=Path("/tmp/claude-0"),
            config_dir=REPO_CONFIG)
    finally:
        conn.close()
    assert "DISTRIBUTION: narrowed to CEO and COO" in report["body"]


def test_the_steady_state_list_is_never_lost_while_narrowed():
    """Widening later must not require reconstructing the list."""
    data = yaml.safe_load(
        (REPO_CONFIG / "distribution.yaml").read_text(encoding="utf-8"))
    assert data["management_reports"]["phase"] == "PHASE_2"
    assert len(data["management_reports"]["steady_state_recipients"]) == 4
    assert "widen_when" in data["management_reports"]
