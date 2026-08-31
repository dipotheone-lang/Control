"""Continuity — §5.2, decision D-11 (16-Aug-2026).

    "A chain that is not backed up can be truncated undetectably by a
     dead laptop."

That is the sentence these tests exist to honour. Losing the database
costs the record; losing the hash chain costs the ability to prove the
record was never altered, including for the period before the loss.

So the tests that matter are the refusals: never write plaintext to a
synced folder, never report a missing backup as a fresh one, never
accept an archive that decrypts but does not match its manifest.
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from control import HaltError
from control.backup import (
    ARCHIVE_PREFIX, backup_age_days, continuity_lines, create_backup,
    ensure_daily_backup, latest_backup, prune, resolve_destination, restore,
    restore_test,
)

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
KEY = "0" * 43 + "="          # a valid 32-byte urlsafe base64 Fernet key


@pytest.fixture
def key():
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


@pytest.fixture
def root(tmp_path):
    """A CONTROL_ROOT with something in every directory that matters."""
    control_root = tmp_path / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    (control_root / "outbox" / "sent").mkdir(parents=True)
    (control_root / "backup").mkdir()
    (control_root / "data" / "control.db").write_bytes(b"pretend database")
    (control_root / "logs" / "2026-08-16.jsonl").write_text("{}\n")
    (control_root / "outbox" / "sent" / "m1.json").write_text("{}")
    (control_root / "backup" / "old.enc").write_bytes(b"should not recurse")
    return control_root


def cfg(destination, key_value, **over):
    base = {
        "destination": {"path": str(destination), "subfolder": None},
        "encryption": {"enabled": True, "env_var": "TEST_BACKUP_KEY",
                       "keyring_service": "unused-in-tests"},
        "schedule": {"daily": True},
        "retention": {"keep_days": 365, "keep_minimum": 7},
        "restore_test": {"every_days": 30, "last_tested": None},
    }
    base.update(over)
    return base, {"TEST_BACKUP_KEY": key_value}


# ---- destination ------------------------------------------------------

def test_no_destination_resolves_to_none_not_a_guess():
    assert resolve_destination({}) is None
    assert resolve_destination({"destination": {"path": None}}) is None


def test_onedrive_is_auto_detected():
    config = {"destination": {"auto_detect": "onedrive",
                              "subfolder": "UBCSIS-Control-Backup"}}
    found = resolve_destination(config, {"OneDriveCommercial": "/od/work"})
    assert found == Path("/od/work/UBCSIS-Control-Backup")


def test_commercial_onedrive_wins_over_personal():
    config = {"destination": {"auto_detect": "onedrive"}}
    found = resolve_destination(
        config, {"OneDrive": "/od/personal", "OneDriveCommercial": "/od/work"})
    assert found == Path("/od/work")


def test_auto_detect_without_onedrive_is_none_not_the_home_directory():
    config = {"destination": {"auto_detect": "onedrive"}}
    assert resolve_destination(config, {}) is None


# ---- the refusal that matters ----------------------------------------

def test_no_key_halts_rather_than_writing_plaintext(root, tmp_path):
    """A synced folder is the last place to put this unencrypted."""
    config = {
        "destination": {"path": str(tmp_path / "dest")},
        "encryption": {"env_var": "ABSENT_VAR", "keyring_service": None},
        "schedule": {"daily": True},
    }
    with pytest.raises(HaltError) as e:
        create_backup(root, config, on_date=date(2026, 8, 16), env={})
    assert "unencrypted backup" in str(e.value)
    assert not (tmp_path / "dest").exists()


def test_unconfigured_destination_is_a_gap_not_a_crash(root, key):
    config, env = cfg("/nowhere", key)
    config["destination"] = {"path": None}
    result = create_backup(root, config, on_date=date(2026, 8, 16), env=env)
    assert not result.written
    assert any("NOT CONFIGURED" in g for g in result.gaps)


# ---- writing ----------------------------------------------------------

def test_backup_covers_the_whole_root_not_just_the_database(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key)
    result = create_backup(root, config, on_date=date(2026, 8, 16), env=env)
    assert result.written
    assert result.files == 3          # db, log, outbox — not backup/old.enc

    unpacked = restore(result.path, tmp_path / "out", config, env)
    names = {p.relative_to(unpacked).as_posix()
             for p in unpacked.rglob("*") if p.is_file()}
    assert names == {"data/control.db", "logs/2026-08-16.jsonl",
                     "outbox/sent/m1.json"}


def test_backups_are_not_backed_up(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key)
    result = create_backup(root, config, on_date=date(2026, 8, 16), env=env)
    unpacked = restore(result.path, tmp_path / "out", config, env)
    assert not (unpacked / "backup").exists()


def test_the_archive_is_actually_encrypted(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key)
    result = create_backup(root, config, on_date=date(2026, 8, 16), env=env)
    raw = result.path.read_bytes()
    assert b"pretend database" not in raw
    assert b"control.db" not in raw


def test_a_manifest_travels_beside_the_archive(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key)
    result = create_backup(root, config, on_date=date(2026, 8, 16), env=env)
    manifest = yaml.safe_load(
        result.path.with_name(result.path.name + ".manifest.json")
        .read_text(encoding="utf-8"))
    assert manifest["files"] == 3
    assert manifest["sha256"] == result.sha256


# ---- reading back -----------------------------------------------------

def test_the_wrong_key_is_an_incident_not_an_empty_restore(root, tmp_path, key):
    from cryptography.fernet import Fernet

    config, env = cfg(tmp_path / "dest", key)
    result = create_backup(root, config, on_date=date(2026, 8, 16), env=env)
    other = {"TEST_BACKUP_KEY": Fernet.generate_key().decode()}
    with pytest.raises(HaltError) as e:
        restore(result.path, tmp_path / "out", config, other)
    assert "continuity incident" in str(e.value)


def test_a_tampered_archive_is_refused(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key)
    result = create_backup(root, config, on_date=date(2026, 8, 16), env=env)
    result.path.write_bytes(result.path.read_bytes()[:-20] + b"x" * 20)
    with pytest.raises(HaltError):
        restore(result.path, tmp_path / "out", config, env)


def test_restore_test_checks_the_chain_not_just_the_files(tmp_path, key):
    """§13.3: existence is not the test."""
    from control.audit import AuditLog
    from control.db import init_db

    control_root = tmp_path / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    init_db(control_root / "data" / "control.db").close()
    log = AuditLog(control_root / "logs")
    log.append("TEST", {"n": 1})
    log.append("TEST", {"n": 2})

    config, env = cfg(tmp_path / "dest", key)
    create_backup(control_root, config, on_date=date(2026, 8, 16), env=env)

    outcome = restore_test(config, tmp_path / "restored", env)
    assert outcome["ok"] is True
    assert outcome["db"] == "OK"
    assert outcome["chain"].startswith("OK")


def test_restore_test_reports_no_backup_rather_than_passing(tmp_path, key):
    config, env = cfg(tmp_path / "empty", key)
    outcome = restore_test(config, tmp_path / "restored", env)
    assert outcome["ok"] is False
    assert outcome["error"] == "no backup to test"


# ---- age and retention ------------------------------------------------

def test_missing_backup_is_none_never_age_zero(tmp_path, key):
    config, _ = cfg(tmp_path / "empty", key)
    assert backup_age_days(config, on_date=date(2026, 8, 16)) is None


def test_age_is_measured_from_the_newest(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key)
    create_backup(root, config, on_date=date(2026, 8, 10), env=env)
    create_backup(root, config, on_date=date(2026, 8, 14), env=env)
    assert backup_age_days(config, on_date=date(2026, 8, 16), env=env) == 2


def test_pruning_never_goes_below_the_minimum(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key,
                      retention={"keep_days": 5, "keep_minimum": 3})
    for day in range(1, 9):
        create_backup(root, config, on_date=date(2026, 1, day), env=env)
    prune(config, on_date=date(2026, 6, 1), env=env)   # all are past 5 days
    left = list((tmp_path / "dest").glob(f"{ARCHIVE_PREFIX}*.enc"))
    assert len(left) == 3


def test_pruning_keeps_what_is_inside_retention(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key,
                      retention={"keep_days": 30, "keep_minimum": 1})
    create_backup(root, config, on_date=date(2026, 1, 1), env=env)
    create_backup(root, config, on_date=date(2026, 8, 10), env=env)
    removed = prune(config, on_date=date(2026, 8, 16), env=env)
    assert removed == [f"{ARCHIVE_PREFIX}2026-01-01.enc"]
    assert latest_backup(config, env).name == f"{ARCHIVE_PREFIX}2026-08-10.enc"


def test_an_unparseable_filename_is_left_alone_not_guessed(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key,
                      retention={"keep_days": 1, "keep_minimum": 0})
    create_backup(root, config, on_date=date(2026, 1, 1), env=env)
    stray = tmp_path / "dest" / f"{ARCHIVE_PREFIX}not-a-date.enc"
    stray.write_bytes(b"?")
    prune(config, on_date=date(2026, 8, 16), env=env)
    assert stray.exists()


# ---- the daily guard --------------------------------------------------

def test_today_is_not_backed_up_twice(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key)
    first = ensure_daily_backup(root, config, on_date=date(2026, 8, 16), env=env)
    (root / "data" / "new.txt").write_text("added after the first backup")
    second = ensure_daily_backup(root, config, on_date=date(2026, 8, 16), env=env)
    assert first.path == second.path
    assert second.files == 0          # nothing rewritten


def test_daily_off_means_no_backup(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key, schedule={"daily": False})
    assert not ensure_daily_backup(
        root, config, on_date=date(2026, 8, 16), env=env).written


# ---- what the report says --------------------------------------------

def test_unconfigured_destination_says_the_chain_is_exposed():
    lines = continuity_lines({}, on_date=date(2026, 8, 16))
    assert len(lines) == 1
    assert "NOT CONFIGURED" in lines[0]
    assert "truncated undetectably" in lines[0]


def test_no_backup_present_is_reported(tmp_path, key):
    config, _ = cfg(tmp_path / "dest", key)
    (tmp_path / "dest").mkdir()
    lines = continuity_lines(config, on_date=date(2026, 8, 16))
    assert any("no backup found" in line for line in lines)


def test_a_stale_backup_is_reported(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key)
    create_backup(root, config, on_date=date(2026, 8, 10), env=env)
    lines = continuity_lines(config, on_date=date(2026, 8, 16), env=env)
    assert any("6 days old" in line for line in lines)


def test_an_untested_backup_is_called_a_hope(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key)
    create_backup(root, config, on_date=date(2026, 8, 16), env=env)
    lines = continuity_lines(config, on_date=date(2026, 8, 16), env=env)
    assert any("hope, not a control" in line for line in lines)


def test_an_overdue_restore_test_is_reported(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key,
                      restore_test={"every_days": 30,
                                    "last_tested": "2026-06-01"})
    create_backup(root, config, on_date=date(2026, 8, 16), env=env)
    lines = continuity_lines(config, on_date=date(2026, 8, 16), env=env)
    assert any("restore test is 46 day(s) overdue" in line for line in lines)


def test_a_healthy_backup_says_nothing(root, tmp_path, key):
    config, env = cfg(tmp_path / "dest", key,
                      restore_test={"every_days": 30,
                                    "last_tested": "2026-08-15"})
    create_backup(root, config, on_date=date(2026, 8, 16), env=env)
    assert continuity_lines(config, on_date=date(2026, 8, 16), env=env) == []


# ---- the repository config -------------------------------------------

def test_repo_config_records_the_decision():
    data = yaml.safe_load((REPO_CONFIG / "backup.yaml").read_text(encoding="utf-8"))
    assert data["encryption"]["enabled"] is True
    assert data["destination"]["auto_detect"] == "onedrive"
    assert data["schedule"]["daily"] is True
    assert data["schedule"]["before_first_write"] is True
    assert data["restore_test"]["last_tested"] is None

    # Null again, and for the original reason: a path here bakes in one
    # machine's user name, and this file is version controlled.
    #
    # It was briefly set to E: under D-59, then measured: C: and E: are
    # partitions of the same physical disk, so that backup survived none
    # of the events D-11 exists for. D-60 moved it to OneDrive, which
    # auto_detect resolves per machine.
    assert data["destination"]["path"] is None
    assert data["destination"]["auto_detect"] == "onedrive"


def test_repo_config_reports_itself_as_unprotected_here():
    """On a machine with no OneDrive, the honest answer is still 'not
    backed up' — and it names what it looked for, so the reader can tell
    an absent account from a misconfigured path."""
    data = yaml.safe_load((REPO_CONFIG / "backup.yaml").read_text(encoding="utf-8"))
    lines = continuity_lines(data, on_date=date(2026, 8, 16), env={})
    assert any("NOT CONFIGURED" in line for line in lines)


def test_a_destination_that_cannot_be_written_is_not_silent(tmp_path):
    """A backup that did not happen must read as a finding, never as a
    quiet success (§1.1) — and must not stop a run whose only output is
    class 1 alerts."""
    from control.backup import ensure_daily_backup

    data = yaml.safe_load((REPO_CONFIG / "backup.yaml").read_text(encoding="utf-8"))
    result = ensure_daily_backup(
        REPO_CONFIG.parent, data, on_date=date(2026, 8, 16),
        # A destination that resolves but has no key behind it.
        env={"OneDrive": str(tmp_path)}, must_succeed=False)
    assert not result.written
    assert result.gaps and "BACKUP DID NOT RUN" in result.gaps[0]


# ---- finding the destination without trusting the environment ---------
#
# `OneDriveCommercial` and `OneDrive` are set for the interactive session
# that signed in. A scheduled task, a service, or a shell opened before
# sign-in does not inherit them — so a check reading only the environment
# reports "not configured" on the machine where the folder is sitting
# there. The same defect the OCR language path had, one variable over.

ONEDRIVE = {"destination": {"path": None, "auto_detect": "onedrive",
                            "subfolder": "UBCSIS-Control-Backup"}}


def test_the_environment_variable_is_used_when_it_is_there(tmp_path):
    from control.backup import resolve_destination

    assert resolve_destination(
        ONEDRIVE, {"OneDriveCommercial": str(tmp_path)}
    ) == tmp_path / "UBCSIS-Control-Backup"


def test_the_folder_is_found_on_disk_when_the_variable_is_absent(tmp_path):
    from control.backup import resolve_destination

    (tmp_path / "OneDrive - UBCSIS").mkdir()
    assert resolve_destination(
        ONEDRIVE, {"USERPROFILE": str(tmp_path)}
    ) == tmp_path / "OneDrive - UBCSIS" / "UBCSIS-Control-Backup"


def test_two_synced_tenants_are_refused_rather_than_picked_between(tmp_path):
    """Picking one would put the company's records in whichever sorted
    first (§1.1)."""
    from control.backup import describe_destination, resolve_destination

    (tmp_path / "OneDrive - UBCSIS").mkdir()
    (tmp_path / "OneDrive - Other").mkdir()
    env = {"USERPROFILE": str(tmp_path)}

    assert resolve_destination(ONEDRIVE, env) is None
    reason = describe_destination(ONEDRIVE, env)
    assert "2 OneDrive folders" in reason
    assert "set destination.path to say which" in reason


def test_the_three_reasons_for_no_destination_are_told_apart():
    """"NOT CONFIGURED" was true of a config that never asked, a machine
    with no OneDrive, and one with two — three different fixes behind one
    message."""
    from control.backup import describe_destination

    never_asked = describe_destination({"destination": {"path": None}}, {})
    assert "nothing was asked to look anywhere" in never_asked

    no_profile = describe_destination(ONEDRIVE, {})
    assert "no USERPROFILE" in no_profile

    import tempfile
    with tempfile.TemporaryDirectory() as empty:
        absent = describe_destination(ONEDRIVE, {"USERPROFILE": empty})
    assert "no OneDrive folder under" in absent


def test_an_explicit_path_still_wins(tmp_path):
    from control.backup import describe_destination, resolve_destination

    config = {"destination": {"path": str(tmp_path), "auto_detect": "onedrive"}}
    assert resolve_destination(config, {"OneDrive": "/somewhere/else"}) == tmp_path
    assert "destination.path in backup.yaml" in describe_destination(config, {})


# ---- recording the restore test ---------------------------------------

def test_the_restore_test_records_itself(tmp_path):
    """§13.3 wants backup age AND last successful restore. The command
    used to print "record this in backup.yaml" and leave a human to do
    it — and the test is meant to repeat every 30 days, so the one step
    nobody keeps doing by hand decides whether the control keeps
    working."""
    from control.backup import record_restore_test

    root = tmp_path / "CONTROL"
    (root / "config").mkdir(parents=True)
    (root / "config" / "backup.yaml").write_text(
        "restore_test:\n"
        "  # a comment carrying the reasoning\n"
        "  every_days: 30\n"
        "  last_tested: null\n"
        "  last_result: null\n", encoding="utf-8")

    note = record_restore_test(root, on_date=date(2026, 8, 31), passed=True)
    body = (root / "config" / "backup.yaml").read_text(encoding="utf-8")

    assert "last_tested: 2026-08-31" in body
    assert "last_result: PASS" in body
    assert "every_days: 30" in body
    # Edited line by line: safe_dump would have taken the comment, and
    # this file carries the whole reasoning for D-11, D-59 and D-60.
    assert "# a comment carrying the reasoning" in body
    assert "31-Aug-2026" in note


def test_a_failed_restore_is_recorded_too(tmp_path):
    """A stale last_tested with no result reads as "never tried", and
    those are different facts (§1.1)."""
    from control.backup import record_restore_test

    root = tmp_path / "CONTROL"
    (root / "config").mkdir(parents=True)
    (root / "config" / "backup.yaml").write_text(
        "restore_test:\n  last_tested: null\n  last_result: null\n",
        encoding="utf-8")

    record_restore_test(root, on_date=date(2026, 8, 31), passed=False)
    body = (root / "config" / "backup.yaml").read_text(encoding="utf-8")
    assert "last_result: FAIL" in body


def test_it_refuses_rather_than_guessing_where_to_write(tmp_path):
    from control.backup import record_restore_test

    root = tmp_path / "CONTROL"
    (root / "config").mkdir(parents=True)
    (root / "config" / "backup.yaml").write_text(
        "schedule:\n  daily: true\n", encoding="utf-8")

    with pytest.raises(HaltError) as caught:
        record_restore_test(root, on_date=date(2026, 8, 31), passed=True)
    assert "Not guessing" in str(caught.value)


def test_a_last_tested_elsewhere_in_the_file_is_not_touched(tmp_path):
    """Only the restore_test section. Another key of the same name under
    a different heading is a different fact."""
    from control.backup import record_restore_test

    root = tmp_path / "CONTROL"
    (root / "config").mkdir(parents=True)
    (root / "config" / "backup.yaml").write_text(
        "other_section:\n  last_tested: 2020-01-01\n"
        "restore_test:\n  last_tested: null\n  last_result: null\n",
        encoding="utf-8")

    record_restore_test(root, on_date=date(2026, 8, 31), passed=True)
    body = (root / "config" / "backup.yaml").read_text(encoding="utf-8")
    assert "last_tested: 2020-01-01" in body
    assert "last_tested: 2026-08-31" in body


# ---- rotating the key -------------------------------------------------
#
# `--init-key` reads like setup, so it invites being run twice. The
# second run is not setup: it destroys every archive written under the
# first key, silently, with no error at the time and no error until
# somebody needs a restore. The refusal below is the whole control.

def test_creating_a_second_key_over_a_first_one_is_refused(root, tmp_path, key):
    from control.backup import create_key

    config, env = cfg(tmp_path / "dest", key)
    create_backup(root, config, on_date=date(2026, 8, 31), env=env)

    with pytest.raises(HaltError) as e:
        create_key(config, env=env)
    message = str(e.value)
    assert "already stored" in message
    assert "--rotate" in message


def test_the_refusal_names_the_archives_that_would_be_lost(root, tmp_path, key):
    from control.backup import create_key

    config, env = cfg(tmp_path / "dest", key)
    create_backup(root, config, on_date=date(2026, 8, 31), env=env)

    with pytest.raises(HaltError) as e:
        create_key(config, env=env)
    assert "control-backup-2026-08-31.enc" in str(e.value)


def test_no_key_stored_means_init_key_is_ordinary_setup(tmp_path):
    """The refusal must not block the first run, which has nothing to lose."""
    from control.backup import key_is_stored

    config, _ = cfg(tmp_path / "dest", "unused")
    assert key_is_stored(config, {}) is False


def test_key_is_stored_never_returns_the_key(tmp_path, key):
    from control.backup import key_is_stored

    config, env = cfg(tmp_path / "dest", key)
    assert key_is_stored(config, env) is True


def test_existing_archives_is_empty_when_the_destination_does_not_exist():
    from control.backup import existing_archives

    assert existing_archives({"destination": {"path": "/nowhere/at/all"}}) == []
