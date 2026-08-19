"""The `event` command — the way an event-driven statutory clock starts.

`build_event_items` computes deadlines from recorded events, but until
this command existed nothing could record one, so the two obligations
it serves stayed at zero rows forever. Same shape of gap as the missing
`cycle` and `report` commands.

M1 is why it is a command and not a detector: ETA rejections arrive in
`accounts@`, which Control cannot see. A person enters them, and the
tests below are mostly about that person's entry not being able to hide
anything — not the lag, not who typed it, not a future date.
"""

import shutil
from pathlib import Path

import pytest

from control.__main__ import main
from control.db import init_db

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def root(tmp_path):
    control_root = tmp_path / "UB" / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    init_db(control_root / "data" / "control.db").close()
    return control_root


def run(root, *extra):
    return main(["event", "--control-root", str(root),
                 "--today", "2026-08-18", *extra])


def test_an_empty_register_says_it_is_counting_nothing(root, capsys):
    assert run(root) == 0
    out = capsys.readouterr().out
    assert "No statutory events on record — nothing is being counted." in out
    # And the two obligations name themselves, so the reader knows which
    # windows are dark rather than absent.
    assert "STAT-ETA-REJ" in out and "STAT-SI-HEADCOUNT" in out
    assert "not that none occurred" in out


def test_recording_an_event_computes_and_prints_the_deadline(root, capsys):
    assert run(root, "--obligation", "STAT-ETA-REJ", "--type",
               "ETA_REJECTION", "--date", "2026-08-14", "--reference",
               "INV-9912", "--by", "hadeer@ubcsis.com") == 0
    out = capsys.readouterr().out
    assert "STAT-ETA-REJ on 14-Aug-2026" in out
    assert "due 21-Aug-2026 (T-3)" in out
    assert "owner accounts@ubcsis.com" in out


def test_the_registration_lag_is_stated_at_entry_not_only_in_the_report(root,
                                                                       capsys):
    """The person entering it is the one who can still do something
    about the remaining days, so they are told at the keyboard."""
    run(root, "--obligation", "STAT-SI-HEADCOUNT", "--type", "JOINER",
        "--date", "2026-08-01", "--by", "hr@ubcsis.com")
    out = capsys.readouterr().out
    assert "registered 17 day(s) after the event" in out
    assert "already spent before Control could start counting" in out


def test_a_future_event_is_refused(root, capsys):
    """A clock cannot start on something that has not happened, and a
    typo in the year would otherwise book a deadline decades out."""
    assert run(root, "--obligation", "STAT-ETA-REJ", "--date", "2027-01-04",
               "--by", "hadeer@ubcsis.com") == 1
    assert "starts no clock" in capsys.readouterr().out


def test_a_missing_event_date_is_refused_rather_than_defaulted_to_today(
        root, capsys):
    """Defaulting to today would silently compute the deadline from the
    registration date — precisely what B4 forbids."""
    assert run(root, "--obligation", "STAT-ETA-REJ", "--by",
               "hadeer@ubcsis.com") == 1
    assert "--date is required" in capsys.readouterr().out


def test_an_unattributed_entry_is_refused(root, capsys):
    """§5.2. For a manually detected event the entrant is the only
    evidence of where the date came from."""
    assert run(root, "--obligation", "STAT-ETA-REJ", "--date", "2026-08-14") == 1
    assert "--by is required" in capsys.readouterr().out


def test_listing_shows_the_window_the_lag_and_the_detection(root, capsys):
    run(root, "--obligation", "STAT-SI-HEADCOUNT", "--type", "LEAVER",
        "--date", "2026-08-10", "--reference", "EMP-101",
        "--by", "hr@ubcsis.com")
    capsys.readouterr()

    assert run(root) == 0
    out = capsys.readouterr().out
    assert "1 open statutory event(s)" in out
    assert "LEAVER on 10-Aug-2026" in out
    assert "due 09-Sep-2026 (T-22)" in out
    assert "ref EMP-101" in out
    assert "registered 8 day(s) late" in out
    assert "detection: MANUAL" in out


def test_discharging_closes_the_window_and_leaves_the_event_row(root, capsys):
    run(root, "--obligation", "STAT-ETA-REJ", "--type", "ETA_REJECTION",
        "--date", "2026-08-14", "--by", "hadeer@ubcsis.com")
    capsys.readouterr()

    assert run(root, "--discharge", "1", "--on", "2026-08-17",
               "--by", "hadeer@ubcsis.com") == 0
    out = capsys.readouterr().out
    assert "discharged on 17-Aug-2026" in out
    assert "closure is its own row" in out

    assert run(root) == 0
    assert "No statutory events on record" in capsys.readouterr().out


def test_discharging_an_unknown_event_records_nothing(root, capsys):
    assert run(root, "--discharge", "99", "--by", "hadeer@ubcsis.com") == 1
    assert "No open event 99" in capsys.readouterr().out


def test_the_recorded_event_reaches_the_weekly_horizon(root, capsys, tmp_path):
    """End to end. An event-driven window is a class 1 deadline like any
    other once it exists, and the report is where it has to show up."""
    for name in ("outbox/pending-approval", "outbox/sent",
                 "reports/management"):
        (root / name).mkdir(parents=True, exist_ok=True)
    run(root, "--obligation", "STAT-ETA-REJ", "--type", "ETA_REJECTION",
        "--date", "2026-08-19", "--reference", "INV-9912",
        "--by", "hadeer@ubcsis.com", "--today", "2026-08-19")
    capsys.readouterr()

    main(["report", "--control-root", str(root), "--ub-root",
          str(root.parent), "--run-mode", "DRY_RUN", "--learning-mode",
          "OBSERVE", "--as-of", "2026-08-20"])
    out = capsys.readouterr().out
    horizon = out.split("2. OPEN")[0]
    assert "rejection clearance — INV-9912" in horizon
    assert "26-Aug-2026 (T-6)" in horizon
