"""Transport route — D-08 (16-Aug-2026).

§5.1 specifies Microsoft Graph with certificate authentication. Phase 0
has run on Outlook COM because Graph provisioning stalled and discovery
is read-only metadata. The CEO's decision keeps that for Phase 0 and
requires Graph before Phase 2.

The whole point of these tests is that the deadline is enforced rather
than remembered. An interim arrangement with no mechanism behind it is
just a plan to notice later.
"""

from pathlib import Path

import pytest
import yaml

from control import HaltError
from control.transport import assert_route_permitted, interim_route_note

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


def cfg(**over):
    base = {
        "route": "outlook_com",
        "interim": {"active": True,
                    "permitted_run_modes": ["DISCOVERY", "DRY_RUN"]},
        "graph": {"tenant_id": None, "client_id": None, "cert_thumbprint": None},
    }
    base.update(over)
    return base


# ---- the gate ---------------------------------------------------------

@pytest.mark.parametrize("mode", ["DISCOVERY", "DRY_RUN", "discovery"])
def test_permitted_phases_pass(mode):
    assert_route_permitted(cfg(), mode)


@pytest.mark.parametrize("mode", ["SUPERVISED", "LIVE"])
def test_phase_2_and_beyond_are_refused(mode):
    with pytest.raises(HaltError) as e:
        assert_route_permitted(cfg(), mode)
    assert "outlook_com" in str(e.value)
    assert mode in str(e.value)


def test_the_refusal_says_why_not_just_that():
    """Two reasons, both operational: schedules and scope enforcement."""
    with pytest.raises(HaltError) as e:
        assert_route_permitted(cfg(), "SUPERVISED")
    message = str(e.value)
    assert "laptop being awake" in message
    assert "enforced by Exchange" in message
    assert "transport.yaml route: graph" in message


def test_graph_is_permitted_everywhere():
    for mode in ("DISCOVERY", "DRY_RUN", "SUPERVISED", "LIVE"):
        assert_route_permitted({"route": "graph"}, mode)


def test_missing_config_defaults_to_graph_not_to_permission():
    """Absence must not read as 'the interim route is fine'."""
    assert_route_permitted(None, "LIVE")
    assert_route_permitted({}, "LIVE")


def test_deactivating_the_interim_lifts_the_gate():
    """Explicit, and visible in the file — not an implicit expiry."""
    assert_route_permitted(
        cfg(interim={"active": False}), "SUPERVISED")


def test_an_empty_permitted_list_permits_nothing():
    with pytest.raises(HaltError) as e:
        assert_route_permitted(cfg(interim={"active": True}), "DISCOVERY")
    assert "permits nothing" in str(e.value)


# ---- the weekly note --------------------------------------------------

def test_note_names_what_is_missing():
    note = interim_route_note(cfg())
    assert "D-08" in note
    assert "Phase 2 cannot start on this route" in note
    assert "tenant_id" in note and "cert_thumbprint" in note


def test_note_changes_once_graph_is_provisioned():
    note = interim_route_note(cfg(graph={
        "tenant_id": "t", "client_id": "c", "cert_thumbprint": "x"}))
    assert "not yet provisioned" not in note
    assert "Application Access Policy" in note


def test_no_note_on_the_chartered_route():
    assert interim_route_note({"route": "graph"}) is None
    assert interim_route_note(cfg(interim={"active": False})) is None


# ---- the repository config -------------------------------------------

def test_repo_config_records_the_interim_route():
    data = yaml.safe_load(
        (REPO_CONFIG / "transport.yaml").read_text(encoding="utf-8"))
    assert data["route"] == "outlook_com"
    assert data["interim"]["active"] is True
    assert data["interim"]["permitted_run_modes"] == ["DISCOVERY", "DRY_RUN"]
    # Graph is unprovisioned, and the file says so rather than
    # carrying placeholder credentials (§1.1).
    assert data["graph"]["tenant_id"] is None
    assert data["graph"]["application_access_policy"] is False


def test_repo_config_runs_phase_0_and_blocks_phase_2():
    data = yaml.safe_load(
        (REPO_CONFIG / "transport.yaml").read_text(encoding="utf-8"))
    assert_route_permitted(data, "DISCOVERY")
    with pytest.raises(HaltError):
        assert_route_permitted(data, "SUPERVISED")


def test_startup_refuses_phase_2_on_the_repo_config(tmp_path):
    """End to end: the gate is in the startup path, not just a helper."""
    import shutil

    from control.startup import run_startup

    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")

    run_startup(control_root, ub_root, "DISCOVERY", "OBSERVE", 0, "2026-08-16")
    with pytest.raises(HaltError) as e:
        run_startup(control_root, ub_root, "SUPERVISED", "OBSERVE", 2, "2026-08-16")
    assert "D-08" in str(e.value)


def test_weekly_report_carries_the_route(tmp_path):
    from datetime import date

    from control.db import init_db
    from control.report import weekly_report

    conn = init_db(tmp_path / "control.db")
    try:
        report = weekly_report(
            conn, as_of=date(2026, 8, 20), horizon=[], open_items=[],
            open_decisions=[], control_root=tmp_path, config_dir=REPO_CONFIG)
    finally:
        conn.close()
    assert "interim outlook_com route (D-08)" in report["body"]
