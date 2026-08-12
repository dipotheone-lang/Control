import json
import shutil
from pathlib import Path

import pytest

from control.__main__ import main

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def roots(tmp_path):
    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    (ub_root / "mail").mkdir()
    (ub_root / "mail" / "note.eml").write_bytes(
        b"From: donia@ubcsis.com\nTo: control@ubcsis.com\nSubject: RFQ\n\nbody\n"
    )
    return ub_root, control_root


def _args(cmd, ub, cr):
    return [cmd, "--control-root", str(cr), "--ub-root", str(ub)]


def test_startup_command(roots, capsys):
    ub, cr = roots
    assert main(_args("startup", ub, cr)) == 0
    out = capsys.readouterr().out
    assert "startup OK — phase 0" in out


def test_discovery_command_produces_outputs(roots, capsys):
    ub, cr = roots
    assert main(_args("discovery", ub, cr)) == 0
    out = capsys.readouterr().out
    assert "stage A: 1 archives" in out
    assert (cr / "discovery" / "DISCOVERY-LIMITATIONS.md").exists()


def test_verify_command_detects_tampering(roots, capsys):
    ub, cr = roots
    main(_args("startup", ub, cr))          # creates db + audit entries
    assert main(["verify", "--control-root", str(cr)]) == 0

    log = next((cr / "logs").glob("*.jsonl"))
    lines = log.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["data"]["run_mode"] = "LIVE"      # tamper
    lines[0] = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert main(["verify", "--control-root", str(cr)]) == 1
    assert "critical incident" in capsys.readouterr().out


def test_illegal_state_halts_with_exit_2(roots, capsys):
    ub, cr = roots
    code = main(_args("startup", ub, cr) + ["--run-mode", "LIVE",
                                            "--learning-mode", "OBSERVE",
                                            "--level", "0"])
    assert code == 2
    assert "HALT" in capsys.readouterr().err


def test_ambiguous_level_requires_flag(roots):
    ub, cr = roots
    with pytest.raises(SystemExit):
        main(_args("startup", ub, cr) + ["--run-mode", "LIVE",
                                         "--learning-mode", "ADAPTIVE"])
