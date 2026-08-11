import shutil
from pathlib import Path

import pytest

from control import HaltError
from control.startup import run_startup

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def roots(tmp_path):
    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    return ub_root, control_root


def test_startup_succeeds_in_discovery(roots):
    ub_root, control_root = roots
    report = run_startup(control_root, ub_root, "DISCOVERY", "OBSERVE", 0, "2026-08-11")
    assert report.state.phase == 0
    assert report.open_disputes == 0
    ok, _ = report.audit.verify()
    assert ok
    assert report.db_path.exists()


def test_missing_config_halts(roots):
    ub_root, control_root = roots
    (control_root / "config" / "people.yaml").unlink()
    with pytest.raises(HaltError, match="people.yaml"):
        run_startup(control_root, ub_root, "DISCOVERY", "OBSERVE", 0, "2026-08-11")


def test_illegal_state_halts(roots):
    ub_root, control_root = roots
    with pytest.raises(HaltError, match="illegal state"):
        run_startup(control_root, ub_root, "LIVE", "OBSERVE", 0, "2026-08-11")


def test_learning_mode_mismatch_halts(roots):
    ub_root, control_root = roots
    # Repo config declares OBSERVE; the environment claiming PROPOSE must halt.
    with pytest.raises(HaltError, match="mismatch"):
        run_startup(control_root, ub_root, "LIVE", "PROPOSE", 3, "2026-08-11")


def test_d01_tamper_halts(roots):
    ub_root, control_root = roots
    conf = control_root / "config" / "confidential.yaml"
    conf.write_text(
        conf.read_text(encoding="utf-8").replace("processing: DISABLED", "processing: ENABLED"),
        encoding="utf-8",
    )
    with pytest.raises(HaltError, match="D-01"):
        run_startup(control_root, ub_root, "DISCOVERY", "OBSERVE", 0, "2026-08-11")


def test_unreachable_ub_root_halts(tmp_path):
    with pytest.raises(HaltError, match="UB_ROOT"):
        run_startup(tmp_path / "CONTROL", tmp_path / "missing", "DISCOVERY", "OBSERVE", 0, "2026-08-11")
