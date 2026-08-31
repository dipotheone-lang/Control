"""Deliberate deletion — §12.5, §1.9.

    "Deletion is deliberate and logged."

Personal data removed without a record leaves the same evidence as
personal data that was never collected. One of those is a controller
discharging an obligation and the other is nothing having happened, and
only a log tells them apart afterwards.
"""

from datetime import date
from pathlib import Path

import pytest

from control import HaltError
from control.audit import AuditLog
from control.purge import purge_discovery, render


def _root(tmp_path):
    root = tmp_path / "CONTROL"
    (root / "discovery" / "stage-b").mkdir(parents=True)
    (root / "logs").mkdir()
    (root / "discovery" / "DISCOVERY-REPORT.md").write_text("senders", encoding="utf-8")
    (root / "discovery" / "file-inventory.csv").write_text("paths", encoding="utf-8")
    (root / "discovery" / "stage-b" / "scan.json").write_text("{}", encoding="utf-8")
    (root / "discovery" / "README.md").write_text("why this exists", encoding="utf-8")
    (root / "discovery" / ".gitkeep").write_text("", encoding="utf-8")
    return root


def test_the_content_goes_and_the_structure_stays(tmp_path):
    """A directory that vanishes takes with it the fact that it is meant
    to exist."""
    root = _root(tmp_path)
    result = purge_discovery(root, reason="D-15 scope", ordered_by="Ahmed Diab")

    assert result.files == 3
    assert not (root / "discovery" / "DISCOVERY-REPORT.md").exists()
    assert not (root / "discovery" / "stage-b").exists()
    assert (root / "discovery" / "README.md").exists()
    assert (root / "discovery" / ".gitkeep").exists()


def test_the_deletion_is_written_to_the_hash_chain(tmp_path):
    root = _root(tmp_path)
    audit = AuditLog(root / "logs")
    purge_discovery(root, reason="scanned under a scope that forbids it",
                    ordered_by="Ahmed Diab", audit=audit)

    ok, detail = audit.verify()
    assert ok, detail
    import json
    entries = [json.loads(line)
               for path in sorted((root / "logs").glob("*.jsonl"))
               for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    entry = next(e for e in entries if e["event"] == "purge.discovery")
    assert entry["data"]["files"] == 3
    assert entry["data"]["ordered_by"] == "Ahmed Diab"
    assert "forbids it" in entry["data"]["reason"]


def test_a_deletion_without_a_reason_or_a_person_is_refused(tmp_path):
    """Both go into the log. Neither is guessed."""
    root = _root(tmp_path)
    for reason, who in (("", "Ahmed Diab"), ("a reason", ""), ("  ", "  ")):
        with pytest.raises(HaltError) as caught:
            purge_discovery(root, reason=reason, ordered_by=who)
        assert "needs a reason and a person" in str(caught.value)
    # And nothing was deleted on the way to refusing.
    assert (root / "discovery" / "DISCOVERY-REPORT.md").exists()


def test_an_archive_still_holding_a_copy_is_named(tmp_path):
    """An archive is a copy. A deletion that leaves one unremarked is
    not a deletion."""
    root = _root(tmp_path)
    dest = tmp_path / "OneDrive" / "UBCSIS-Control-Backup"
    dest.mkdir(parents=True)
    (dest / "control-backup-2026-08-31.enc").write_bytes(b"ciphertext")

    result = purge_discovery(
        root, reason="r", ordered_by="Ahmed Diab",
        backup_config={"destination": {"path": str(dest)}})

    assert result.archives_still_holding == ["control-backup-2026-08-31.enc"]
    text = render(result, date(2026, 8, 31))
    assert "STILL HOLDING A COPY" in text
    assert "not complete while they exist" in text
    # And the order matters: a clean backup before the old one goes.
    assert text.index("python -m control backup") < text.index("delete the archives")


def test_nothing_to_delete_says_so_rather_than_claiming_success(tmp_path):
    root = tmp_path / "CONTROL"
    (root / "logs").mkdir(parents=True)
    result = purge_discovery(root, reason="r", ordered_by="Ahmed Diab")

    assert result.files == 0
    assert "does not exist" in render(result, date(2026, 8, 31))


def test_the_sync_recycle_bin_is_named_as_part_of_the_deletion(tmp_path):
    """A cloud folder keeps deleted files in an online recycle bin for
    weeks after they leave the disk. A deletion that stops at the folder
    has moved the copies rather than removed them."""
    root = _root(tmp_path)
    dest = tmp_path / "OneDrive" / "UBCSIS-Control-Backup"
    dest.mkdir(parents=True)
    (dest / "control-backup-2026-08-16.enc").write_bytes(b"ciphertext")

    text = render(purge_discovery(
        root, reason="r", ordered_by="Ahmed Diab",
        backup_config={"destination": {"path": str(dest)}}), date(2026, 8, 31))

    assert "empty the recycle bin" in text
    assert "30 days" in text
    assert "moved the copies rather than removed them" in text
