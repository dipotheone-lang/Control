"""The weekly management report, produced end to end — §11.

`weekly_report` existed and was tested, but nothing could invoke it:
there was no CLI command, so the artefact the CEO actually reads could
not be produced. Same shape of gap as the missing `cycle` command.

The tests here are about what the report refuses to hide. §11's hard
rule is that a number with no traceable row does not appear and the gap
is stated instead — so an empty register must read as an empty register,
never as a clear week.
"""

import shutil
from pathlib import Path

import pytest

from control.__main__ import main

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def root(tmp_path):
    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    for name in ("data", "logs", "outbox/pending-approval", "outbox/sent",
                 "reports/management"):
        (control_root / name).mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_CONFIG, control_root / "config")
    return ub_root, control_root


def run(root, *extra):
    ub_root, control_root = root
    return main(["report", "--control-root", str(control_root),
                 "--ub-root", str(ub_root), "--run-mode", "DRY_RUN",
                 "--learning-mode", "OBSERVE", "--as-of", "2026-08-20",
                 *extra])


def test_the_report_is_produced_and_written(root, capsys):
    _, control_root = root
    assert run(root) == 0
    written = control_root / "reports" / "management" / "2026" / \
        "weekly-2026-08-20.md"
    assert written.is_file()
    assert "WEEKLY CONTROL REPORT" in written.read_text(encoding="utf-8")


def test_it_is_always_a_draft(root, capsys):
    """§10 keeps management reports at DRAFT in every mode, permanently."""
    _, control_root = root
    run(root)
    out = capsys.readouterr().out
    assert "DRAFT" in out
    assert "never auto-sent, in any mode" in out
    assert list((control_root / "outbox" / "pending-approval").glob("*.json"))
    assert not list((control_root / "outbox" / "sent").glob("*.json"))


def test_a_partial_register_reads_as_partial_not_as_clear(root, capsys):
    """§11's hard rule. A reassuring number is the failure mode, and
    four class 1 alerts on a twelve-row register is exactly that shape.
    """
    run(root)
    out = capsys.readouterr().out
    assert "7 of 13 class 1 obligations have a usable date" in out
    assert "the register is incomplete" in out


def test_every_loader_gap_reaches_the_page(root, capsys):
    """Each gap is something Control is NOT doing. A report that showed
    only what was found would read as assurance over unseen ground."""
    run(root)
    out = capsys.readouterr().out
    # Was "obligations.yaml is empty" until the starter register shipped
    # on 26-Aug-2026. The gap did not close, it got specific: six named
    # rows are waiting on the CEO's name instead of a register being
    # absent. Both are things Control is not doing, and both belong on
    # the page.
    assert "not approved by the CEO" in out
    assert "not advisor-verified" in out
    assert "only class carrying fines" in out


def test_the_standing_limitations_are_carried_in_both_languages(root, capsys):
    run(root)
    out = capsys.readouterr().out
    assert "Traffic in sales@ and procure@ is not visible" in out
    assert "غير مرئية لهذا النظام" in out
    assert "Client-confidential documents are tracked" in out
    assert "ولا يتم تقييم محتواها" in out


def test_the_pending_scope_decision_is_disclosed(root, capsys):
    run(root)
    out = capsys.readouterr().out
    assert "D-07" in out and "not yet in effect" in out
    assert "3 precondition(s) remain open" in out


def test_the_report_names_its_recipients_and_why(root, capsys):
    run(root)
    out = capsys.readouterr().out
    assert "ahmed@ubcsis.com, ghareeb@ubcsis.com" in out
    assert "narrowed to CEO and COO for Phase 2" in out


def test_running_twice_does_not_duplicate(root, capsys):
    """§1.10 — the register is checked before every send."""
    _, control_root = root
    pending = control_root / "outbox" / "pending-approval"
    assert run(root) == 0
    capsys.readouterr()

    assert run(root) == 0
    out = capsys.readouterr().out
    assert "not duplicated" in out
    assert len(list(pending.glob("*.json"))) == 1


def test_a_duplicate_run_leaves_the_pending_version_standing(root, capsys):
    """The draft awaiting release is the version of record.

    Rewriting the file underneath it would leave the copy on disk saying
    something the CEO's pending draft does not — a divergence with
    nothing on either to say which is current.
    """
    _, control_root = root
    written = control_root / "reports" / "management" / "2026" / \
        "weekly-2026-08-20.md"
    run(root)
    written.write_text("released version", encoding="utf-8")
    capsys.readouterr()

    run(root)
    assert written.read_text(encoding="utf-8") == "released version"
    assert "left as it was" in capsys.readouterr().out


def test_a_stalled_golden_set_batch_reaches_the_report(root, capsys):
    """§13.1: Phase 1 cannot complete without the CEO's time, and a
    batch out beyond two weeks is raised rather than waited out."""
    import yaml

    _, control_root = root
    ledger = control_root / "tests" / "golden-set" / "worksheets" / "batches.yaml"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(yaml.safe_dump({"batches": [
        {"number": 1, "issued": "2026-07-20", "case_ids": ["GS-001"]}]}),
        encoding="utf-8")

    run(root)
    out = capsys.readouterr().out
    assert "Golden-set batch 1" in out
    assert "DEPLOYMENT BLOCKER" in out
    assert "cannot be delegated" in out


def test_an_illegal_state_halts_before_any_report(root):
    """§5.6: the state check comes first, and a report from an illegal
    state would be a record of something that should not have run."""
    ub_root, control_root = root
    code = main(["report", "--control-root", str(control_root),
                 "--ub-root", str(ub_root), "--run-mode", "LIVE",
                 "--learning-mode", "OBSERVE", "--level", "1"])
    assert code == 2
    assert not list(
        (control_root / "reports" / "management").rglob("*.md"))
