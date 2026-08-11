import shutil
from datetime import date
from pathlib import Path

import pytest

from control import HaltError
from control.discovery.runner import run_discovery
from control.startup import run_startup

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def roots(tmp_path):
    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    (ub_root / "site-reports").mkdir()
    (ub_root / "site-reports" / "weekly.xlsx").write_bytes(b"data")
    (ub_root / "site-reports" / "note.eml").write_bytes(
        b"From: a.elsayed@ubcsis.com\nTo: control@ubcsis.com\nSubject: Weekly\n\nbody\n"
    )
    return ub_root, control_root


def test_discovery_runs_and_writes_outputs(roots):
    ub_root, control_root = roots
    report = run_startup(control_root, ub_root, "DISCOVERY", "OBSERVE", 0, "2026-08-11")
    result = run_discovery(report, ub_root, control_root, today=date(2026, 8, 11))

    out = control_root / "discovery"
    assert (out / "mail-archive-index.csv").exists()
    assert (out / "file-inventory.csv").exists()
    assert (out / "DISCOVERY-LIMITATIONS.md").exists()
    assert result["stage_a"]["messages_indexed"] == 1
    # config copies under CONTROL_ROOT are excluded from the inventory
    inventory = (out / "file-inventory.csv").read_text(encoding="utf-8")
    assert "people.yaml" not in inventory

    ok, detail = report.audit.verify()
    assert ok, detail


def test_discovery_refuses_wrong_state(roots):
    ub_root, control_root = roots
    report = run_startup(control_root, ub_root, "DRY_RUN", "OBSERVE", 1, "2026-08-11")
    with pytest.raises(HaltError, match="RUN_MODE=DISCOVERY"):
        run_discovery(report, ub_root, control_root)
