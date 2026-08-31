"""Deliberate deletion — charter §12.5, §1.9.

    "Deletion is deliberate and logged."

That sentence is why this module exists rather than a `Remove-Item`.
Personal data removed without a record leaves the same evidence as
personal data that was never collected, and those are different facts:
one of them is a controller discharging an obligation, and only a log
can tell them apart afterwards.

The first use was not a retention schedule. On 31-Aug-2026 `phase0` ran
under `OPERATING_SCOPE=STATUTORY_ONLY` and scanned fourteen mailboxes,
because the scope refusal was wired into `cycle` and not into
discovery. The scan was metadata-only by construction, but it was still
processing personal data with no documented lawful basis and nobody
notified (§12.2, §12.4). The CEO ordered the output deleted.

**What deletion here does and does not reach.** It removes the files.
It does not reach an encrypted backup archive already written, and
saying so is the point — an archive is a copy, and a deletion that
quietly leaves one is not a deletion. The archives holding it are named
in the result so the decision about them is taken rather than assumed.
"""

import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import HaltError

# Structure survives; contents do not. A directory that vanishes takes
# with it the fact that it is meant to exist.
_KEEP = {".gitkeep", "README.md"}


@dataclass
class PurgeResult:
    files: int = 0
    bytes_freed: int = 0
    kept: list = field(default_factory=list)
    archives_still_holding: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def purge_discovery(control_root: Path, *, reason: str, ordered_by: str,
                    audit=None, backup_config: dict | None = None,
                    env: dict | None = None) -> PurgeResult:
    """Delete everything Phase 0 wrote, and log that it was deleted."""
    control_root = Path(control_root)
    target = control_root / "discovery"
    result = PurgeResult()

    if not reason.strip() or not ordered_by.strip():
        raise HaltError(
            "a deletion needs a reason and a person who ordered it "
            "(§12.5). Both are written to the audit log; neither is "
            "guessed.")
    if not target.is_dir():
        result.notes.append(f"nothing to delete: {target} does not exist")
        return result

    for path in sorted(target.rglob("*"), key=lambda p: -len(p.parts)):
        if path.is_dir():
            continue
        if path.name in _KEEP:
            result.kept.append(path.name)
            continue
        try:
            result.bytes_freed += path.stat().st_size
        except OSError:
            pass
        path.unlink()
        result.files += 1

    for path in sorted(target.rglob("*"), key=lambda p: -len(p.parts)):
        if path.is_dir() and not any(path.iterdir()):
            shutil.rmtree(path, ignore_errors=True)

    # An archive is a copy. A deletion that leaves one unremarked is not
    # a deletion, so they are named rather than left to be discovered.
    if backup_config:
        from .backup import ARCHIVE_PREFIX, resolve_destination

        destination = resolve_destination(backup_config, env)
        if destination and destination.is_dir():
            result.archives_still_holding = sorted(
                p.name for p in destination.glob(f"{ARCHIVE_PREFIX}*"))

    if audit is not None:
        audit.append("purge.discovery", {
            "files": result.files,
            "bytes": result.bytes_freed,
            "reason": reason.strip(),
            "ordered_by": ordered_by.strip(),
            "archives_still_holding": result.archives_still_holding,
        })
    return result


def render(result: PurgeResult, today: date) -> str:
    lines = [f"DISCOVERY OUTPUT DELETED — {today:%d-%b-%Y}", ""]
    if not result.files and not result.notes:
        lines.append("Nothing was there to delete.")
    for note in result.notes:
        lines.append(note)
    if result.files:
        lines += [
            f"  files deleted: {result.files}",
            f"  freed:         {result.bytes_freed:,} bytes",
        ]
        if result.kept:
            lines.append(f"  kept:          {', '.join(sorted(set(result.kept)))}"
                         "  (structure, not content)")
        lines += ["", "Logged to the hash-chained audit log (§12.5, §1.9). A "
                  "deletion nobody", "can see is indistinguishable from data "
                  "that was never collected."]

    if result.archives_still_holding:
        lines += [
            "",
            "STILL HOLDING A COPY — "
            f"{len(result.archives_still_holding)} backup archive(s):",
            "",
        ]
        for name in result.archives_still_holding:
            lines.append(f"  {name}")
        lines += [
            "",
            "These are encrypted, and they are still copies. The deletion is",
            "not complete while they exist. To finish it:",
            "",
            "  1. python -m control backup        (writes a clean archive)",
            "  2. delete the archives listed above",
            "  3. empty the recycle bin of wherever they were synced",
            "",
            "In that order — deleting first would leave no backup at all,",
            "and §13.3 counts backup age as a control.",
            "",
            "Step 3 is not housekeeping. A cloud sync folder keeps deleted",
            "files in an online recycle bin for weeks after they leave the",
            "disk — OneDrive holds them for 30 days — so a deletion that",
            "stops at step 2 has moved the copies rather than removed them.",
            "The same is true of the local Recycle Bin for anything deleted",
            "through Explorer rather than PowerShell.",
        ]
    return "\n".join(lines)
