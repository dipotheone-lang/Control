"""Continuity — charter §5.2, CEO decision D-11.

    "Daily encrypted backup of the whole of CONTROL_ROOT — database,
     hash-chained logs, outbox, learning records — before first write.
     A chain that is not backed up can be truncated undetectably by a
     dead laptop. Documented cold-start procedure."

That sentence is the whole design brief, and the emphasis on the hash
chain is the part that is easy to miss. Losing the database costs the
record. Losing the chain costs the ability to prove the record was
never altered — including proving it about the period before the loss.

Three properties follow, and each is enforced rather than assumed:

**Whole-root, not just the database.** A backup of `control.db` alone
would restore the numbers and lose the evidence that they are the
original numbers.

**Encrypted, or not written at all.** The destination is a synced
company folder. An unencrypted copy of this data sitting there would
be a worse exposure than the risk it mitigates, so a missing key is a
halt — never a quiet fallback to plaintext.

**Verified by restoring, not by existing.** §13.3 asks for backup age
*and* last successful restore test. A backup nobody has ever restored
is a hope. `restore_test` unpacks a real archive, checks the database
integrity and re-verifies the audit chain end to end.
"""

import hashlib
import json
import os
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from . import HaltError

ARCHIVE_PREFIX = "control-backup-"
ARCHIVE_SUFFIX = ".enc"
MANIFEST_SUFFIX = ".manifest.json"

# Never back up the backups, and never the scratch that quarantine holds.
_EXCLUDED_DIRS = {"backup", "__pycache__"}


@dataclass
class BackupResult:
    path: Path | None = None
    files: int = 0
    plaintext_bytes: int = 0
    encrypted_bytes: int = 0
    sha256: str = ""
    gaps: list[str] = field(default_factory=list)

    @property
    def written(self) -> bool:
        return self.path is not None


# ---- destination -----------------------------------------------------

def resolve_destination(config: dict | None, env: dict | None = None) -> Path | None:
    """Where backups go, or None if nowhere is configured.

    Returns None rather than inventing a path. A backup written to a
    guessed location is a backup nobody will find when it matters.
    """
    data = (config or {}).get("destination") or {}
    env = os.environ if env is None else env

    explicit = data.get("path")
    if explicit:
        base = Path(str(explicit))
    elif str(data.get("auto_detect") or "").lower() == "onedrive":
        found = env.get("OneDriveCommercial") or env.get("OneDrive")
        if not found:
            return None
        base = Path(found)
    else:
        return None

    subfolder = data.get("subfolder")
    return base / str(subfolder) if subfolder else base


# ---- the key ---------------------------------------------------------

def _load_key(config: dict | None, env: dict | None = None) -> bytes:
    """Fetch the encryption key, or halt.

    There is deliberately no path here that returns None and lets the
    caller write plaintext instead.
    """
    encryption = (config or {}).get("encryption") or {}
    env = os.environ if env is None else env

    var = encryption.get("env_var")
    if var and env.get(var):
        return env[var].encode()

    service = encryption.get("keyring_service")
    if service:
        try:
            import keyring

            stored = keyring.get_password(service, "control")
            if stored:
                return stored.encode()
        except Exception:
            pass

    raise HaltError(
        "backup encryption key not available. Expected it in the "
        f"credential store under {service!r}, or in the environment "
        f"variable {var!r}. Control does not write an unencrypted "
        "backup of CONTROL_ROOT to a synced folder (§5.2). Run "
        "'python -m control backup --init-key' to create one."
    )


def create_key(config: dict) -> str:
    """Generate and store a new key. Returns it once, for escrow.

    The caller must record it somewhere outside this machine — a key
    that exists only on the laptop the backup protects against is not a
    key, it is a coin flip.
    """
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    service = ((config or {}).get("encryption") or {}).get("keyring_service")
    if not service:
        raise HaltError("backup.yaml: encryption.keyring_service is not set")
    import keyring

    keyring.set_password(service, "control", key)
    return key


# ---- writing ---------------------------------------------------------

def _collect(control_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(control_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(control_root)
        if any(part in _EXCLUDED_DIRS for part in relative.parts):
            continue
        files.append(path)
    return files


def create_backup(control_root: Path, config: dict, *, on_date: date,
                  env: dict | None = None) -> BackupResult:
    """Write one encrypted archive of the whole of CONTROL_ROOT."""
    from cryptography.fernet import Fernet

    control_root = Path(control_root)
    result = BackupResult()

    destination = resolve_destination(config, env)
    if destination is None:
        result.gaps.append(
            "backup destination NOT CONFIGURED — set destination.path in "
            "backup.yaml, or run on a machine where OneDrive is signed in. "
            "Nothing was written (§1.1: a visible gap, not a silent one)."
        )
        return result

    key = _load_key(config, env)          # halts rather than degrading
    files = _collect(control_root)
    if not files:
        result.gaps.append(f"CONTROL_ROOT holds no files to back up: {control_root}")
        return result

    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(control_root).as_posix())
    plaintext = buffer.getvalue()

    result.files = len(files)
    result.plaintext_bytes = len(plaintext)
    result.sha256 = hashlib.sha256(plaintext).hexdigest()

    token = Fernet(key).encrypt(plaintext)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"{ARCHIVE_PREFIX}{on_date.isoformat()}{ARCHIVE_SUFFIX}"
    target.write_bytes(token)

    # The manifest travels beside the archive so verification does not
    # need the key to detect a truncated or swapped file.
    (destination / f"{target.name}{MANIFEST_SUFFIX}").write_text(
        json.dumps({
            "created": on_date.isoformat(),
            "files": result.files,
            "plaintext_bytes": result.plaintext_bytes,
            "encrypted_bytes": len(token),
            "sha256": result.sha256,
            "control_root": str(control_root),
        }, indent=2),
        encoding="utf-8",
    )

    result.path = target
    result.encrypted_bytes = len(token)
    return result


def prune(config: dict, *, on_date: date, env: dict | None = None) -> list[str]:
    """Delete archives past retention, never below the minimum count."""
    destination = resolve_destination(config, env)
    if destination is None or not destination.is_dir():
        return []
    retention = (config or {}).get("retention") or {}
    keep_days = int(retention.get("keep_days") or 0)
    keep_minimum = int(retention.get("keep_minimum") or 0)
    if not keep_days:
        return []

    archives = sorted(destination.glob(f"{ARCHIVE_PREFIX}*{ARCHIVE_SUFFIX}"))
    cutoff = on_date - timedelta(days=keep_days)
    removed: list[str] = []
    # Oldest first; stop as soon as removing another would breach the floor.
    for path in archives:
        if len(archives) - len(removed) <= keep_minimum:
            break
        stamp = path.name[len(ARCHIVE_PREFIX):-len(ARCHIVE_SUFFIX)]
        try:
            created = date.fromisoformat(stamp)
        except ValueError:
            continue          # unparseable name: leave it alone, never guess
        if created < cutoff:
            path.unlink()
            manifest = path.with_name(f"{path.name}{MANIFEST_SUFFIX}")
            if manifest.exists():
                manifest.unlink()
            removed.append(path.name)
    return removed


# ---- reading back ----------------------------------------------------

def latest_backup(config: dict, env: dict | None = None) -> Path | None:
    destination = resolve_destination(config, env)
    if destination is None or not destination.is_dir():
        return None
    archives = sorted(destination.glob(f"{ARCHIVE_PREFIX}*{ARCHIVE_SUFFIX}"))
    return archives[-1] if archives else None


def backup_age_days(config: dict, *, on_date: date,
                    env: dict | None = None) -> int | None:
    """Age of the most recent backup, or None if there is none.

    None means "no backup", which the self-audit must report as a
    finding. It must never be rendered as age zero.
    """
    latest = latest_backup(config, env)
    if latest is None:
        return None
    stamp = latest.name[len(ARCHIVE_PREFIX):-len(ARCHIVE_SUFFIX)]
    try:
        return (on_date - date.fromisoformat(stamp)).days
    except ValueError:
        return None


def restore(archive: Path, target: Path, config: dict,
            env: dict | None = None) -> Path:
    """Decrypt and unpack an archive into target. Verifies the digest."""
    from cryptography.fernet import Fernet, InvalidToken

    archive, target = Path(archive), Path(target)
    key = _load_key(config, env)
    try:
        plaintext = Fernet(key).decrypt(archive.read_bytes())
    except InvalidToken as e:
        raise HaltError(
            f"cannot decrypt {archive.name}: wrong key, or the archive has "
            "been altered. Either is a continuity incident (§13.3)."
        ) from e

    manifest_path = archive.with_name(f"{archive.name}{MANIFEST_SUFFIX}")
    if manifest_path.is_file():
        expected = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual = hashlib.sha256(plaintext).hexdigest()
        if expected.get("sha256") and expected["sha256"] != actual:
            raise HaltError(
                f"{archive.name} decrypts but does not match its manifest "
                f"digest. Expected {expected['sha256'][:16]}…, got "
                f"{actual[:16]}…. Treat as a continuity incident (§13.3)."
            )

    import io

    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(plaintext)) as unpacked:
        unpacked.extractall(target)
    return target


def restore_test(config: dict, target: Path,
                 env: dict | None = None) -> dict:
    """§13.3: restore the latest backup and check what came back.

    Existence is not the test. This unpacks a real archive, runs the
    database integrity check and re-verifies the audit hash chain, so
    "last successful restore test" means something was actually
    restored and was actually sound.
    """
    from .audit import AuditLog
    from .db import connect, integrity_check

    outcome = {"archive": None, "files": 0, "db": "NOT PRESENT",
               "chain": "NOT PRESENT", "ok": False}

    archive = latest_backup(config, env)
    if archive is None:
        outcome["error"] = "no backup to test"
        return outcome
    outcome["archive"] = archive.name

    root = restore(archive, Path(target), config, env)
    outcome["files"] = sum(1 for p in root.rglob("*") if p.is_file())

    db_path = root / "data" / "control.db"
    if db_path.exists():
        conn = connect(db_path)
        try:
            integrity_check(conn)
            outcome["db"] = "OK"
        except HaltError as e:
            outcome["db"] = f"FAILED — {e}"
        finally:
            conn.close()

    logs = root / "logs"
    if logs.is_dir() and any(logs.glob("*.jsonl")):
        ok, detail = AuditLog(logs).verify()
        outcome["chain"] = ("OK — " + detail) if ok else ("BROKEN — " + detail)

    outcome["ok"] = (outcome["db"] in ("OK", "NOT PRESENT")
                     and not outcome["chain"].startswith("BROKEN"))
    return outcome


# ---- the daily guard -------------------------------------------------

def ensure_daily_backup(control_root: Path, config: dict, *, on_date: date,
                        env: dict | None = None) -> BackupResult:
    """Make today's backup if it is missing (§5.2, before first write).

    Returns a result carrying gaps rather than raising when the
    destination is unconfigured: an unconfigured destination is a
    finding for the report, not a reason to stop a discovery run. A
    *configured* destination that then fails to write does raise —
    at that point something is wrong that silence would hide.
    """
    if not ((config or {}).get("schedule") or {}).get("daily"):
        return BackupResult()

    destination = resolve_destination(config, env)
    if destination is not None:
        existing = destination / f"{ARCHIVE_PREFIX}{on_date.isoformat()}{ARCHIVE_SUFFIX}"
        if existing.exists():
            return BackupResult(path=existing)

    result = create_backup(control_root, config, on_date=on_date, env=env)
    if result.written:
        prune(config, on_date=on_date, env=env)
    return result


def continuity_lines(config: dict, *, on_date: date,
                     env: dict | None = None) -> list[str]:
    """The §13.3 continuity line: backup age and last restore test."""
    lines: list[str] = []
    destination = resolve_destination(config, env)
    if destination is None:
        return ["CONTINUITY: backup destination NOT CONFIGURED. CONTROL_ROOT "
                "is not backed up, so the audit chain could be truncated "
                "undetectably by a hardware failure (§5.2, D-11)."]

    age = backup_age_days(config, on_date=on_date, env=env)
    if age is None:
        lines.append(f"CONTINUITY: no backup found in {destination}. "
                     "CONTROL_ROOT is not protected (§5.2).")
    elif age > 1:
        lines.append(f"CONTINUITY: most recent backup is {age} days old; "
                     "the schedule is daily (§5.2).")

    test = (config or {}).get("restore_test") or {}
    last = test.get("last_tested")
    every = int(test.get("every_days") or 0)
    if not last:
        lines.append("CONTINUITY: no restore test on record. An untested "
                     "backup is a hope, not a control (§13.3).")
    elif every:
        try:
            tested = (last if isinstance(last, date)
                      else datetime.fromisoformat(str(last)).date())
            overdue = (on_date - tested).days - every
            if overdue > 0:
                lines.append(f"CONTINUITY: restore test is {overdue} day(s) "
                             f"overdue (last {tested:%d-%b-%Y}, every {every} "
                             "days) (§13.3).")
        except ValueError:
            lines.append("CONTINUITY: restore_test.last_tested is unreadable.")
    return lines
