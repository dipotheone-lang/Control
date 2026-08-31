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

    base, _ = _resolve_base(data, env)
    if base is None:
        return None
    subfolder = data.get("subfolder")
    return base / str(subfolder) if subfolder else base


def _onedrive_on_disk(env: dict) -> tuple[Path | None, str]:
    """Find the OneDrive folder without trusting the environment.

    `OneDriveCommercial` and `OneDrive` are set for the interactive
    session that signed in. A scheduled task, a service, or a shell
    opened before sign-in does not inherit them — so a check that reads
    only the environment reports "not configured" on the same machine
    where the folder is sitting there. The same defect the OCR language
    path had, one variable over.
    """
    profile = env.get("USERPROFILE")
    if not profile:
        return None, "no USERPROFILE, so no user folder to look in"
    home = Path(profile)
    if not home.is_dir():
        return None, f"USERPROFILE {home} is not a directory"

    commercial = sorted(p for p in home.glob("OneDrive - *") if p.is_dir())
    if len(commercial) == 1:
        return commercial[0], f"found on disk at {commercial[0]}"
    if len(commercial) > 1:
        # Two tenants synced to one profile. Picking one would put the
        # company's records in whichever sorted first (§1.1).
        names = ", ".join(p.name for p in commercial)
        return None, (f"{len(commercial)} OneDrive folders under {home} "
                      f"({names}) — set destination.path to say which")
    personal = home / "OneDrive"
    if personal.is_dir():
        return personal, f"found on disk at {personal}"
    return None, (f"no OneDrive folder under {home} and neither "
                  "OneDriveCommercial nor OneDrive is set in this process")


def _resolve_base(data: dict, env: dict) -> tuple[Path | None, str]:
    """(base path, how it was resolved or why it was not)."""
    explicit = data.get("path")
    if explicit:
        return Path(str(explicit)), "destination.path in backup.yaml"

    mode = str(data.get("auto_detect") or "").lower()
    if mode != "onedrive":
        return None, (
            "destination.path is not set and destination.auto_detect is "
            f"{data.get('auto_detect')!r} — nothing was asked to look "
            "anywhere")

    found = env.get("OneDriveCommercial") or env.get("OneDrive")
    if found:
        return Path(found), "OneDrive environment variable"
    return _onedrive_on_disk(env)


def describe_destination(config: dict | None, env: dict | None = None) -> str:
    """Why there is no destination — naming what was tried.

    "NOT CONFIGURED" is true of a config that never asked, of a machine
    where OneDrive is absent, and of one where two tenants are synced.
    Those need three different fixes, and a single message sent the
    reader to the wrong one.
    """
    data = (config or {}).get("destination") or {}
    return _resolve_base(data, os.environ if env is None else env)[1]


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


def key_is_stored(config: dict | None, env: dict | None = None) -> bool:
    """Whether a key can already be found. Never returns the key."""
    try:
        _load_key(config, env)
    except HaltError:
        return False
    return True


def create_key(config: dict, *, rotate: bool = False,
               env: dict | None = None) -> str:
    """Generate and store a new key. Returns it once, for escrow.

    The caller must record it somewhere outside this machine — a key
    that exists only on the laptop the backup protects against is not a
    key, it is a coin flip.

    Storing a second key over a first one is not a neutral act: every
    archive already written was encrypted with the old key and becomes
    unreadable the moment it is overwritten, by anyone, permanently.
    So this refuses when a key is already stored unless the caller
    says `rotate` — the refusal is the control, because the damage is
    silent and irreversible and the command looks like setup.
    """
    from cryptography.fernet import Fernet

    service = ((config or {}).get("encryption") or {}).get("keyring_service")
    if not service:
        raise HaltError("backup.yaml: encryption.keyring_service is not set")

    if key_is_stored(config, env) and not rotate:
        archives = existing_archives(config, env)
        raise HaltError(
            "a backup key is already stored. Creating another one "
            "overwrites it, and "
            + (f"the {len(archives)} archive(s) already written "
               f"({', '.join(a.name for a in archives[:3])}"
               f"{', …' if len(archives) > 3 else ''}) were encrypted "
               "with the current key — they would become permanently "
               "unreadable."
               if archives else
               "any archive written with the current key would become "
               "permanently unreadable.")
            + " If you mean to rotate it, pass --rotate."
        )

    key = Fernet.generate_key().decode()
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
            "backup destination NOT CONFIGURED: "
            f"{describe_destination(config, env)}. Set destination.path in "
            "backup.yaml to fix it outright. Nothing was written "
            "(§1.1: a visible gap, not a silent one)."
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

def existing_archives(config: dict | None,
                      env: dict | None = None) -> list[Path]:
    """Every archive at the destination, oldest first."""
    destination = resolve_destination(config, env)
    if destination is None or not destination.is_dir():
        return []
    return sorted(destination.glob(f"{ARCHIVE_PREFIX}*{ARCHIVE_SUFFIX}"))


def latest_backup(config: dict, env: dict | None = None) -> Path | None:
    archives = existing_archives(config, env)
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
                        env: dict | None = None,
                        must_succeed: bool = True) -> BackupResult:
    """Make today's backup if it is missing (§5.2, before first write).

    Returns a result carrying gaps rather than raising when the
    destination is unconfigured: an unconfigured destination is a
    finding for the report, not a reason to stop a discovery run. A
    *configured* destination that then fails to write does raise —
    at that point something is wrong that silence would hide.

    `must_succeed=False` turns that raise into a loud gap. It is set by
    the caller for a scope whose whole output is class 1 alerts: a
    missing encryption key or an unplugged backup drive is a real
    finding, and losing a day of the record is bad — but it is not as
    bad as a missed statutory filing, which is what stopping the run
    would cost. The gap says exactly what failed either way.
    """
    if not ((config or {}).get("schedule") or {}).get("daily"):
        return BackupResult()

    destination = resolve_destination(config, env)
    if destination is not None:
        existing = destination / f"{ARCHIVE_PREFIX}{on_date.isoformat()}{ARCHIVE_SUFFIX}"
        if existing.exists():
            return BackupResult(path=existing)

    try:
        result = create_backup(control_root, config, on_date=on_date, env=env)
    except Exception as e:                              # noqa: BLE001
        if must_succeed:
            raise
        failed = BackupResult()
        failed.gaps.append(
            f"BACKUP DID NOT RUN: {str(e)[:300]} — the run continued because "
            "this scope's output is class 1 alerts and stopping would cost a "
            "statutory deadline. Today's record is not backed up.")
        return failed
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


def record_restore_test(control_root: Path, *, on_date: date,
                        passed: bool) -> str:
    """Write the restore-test outcome into the live backup.yaml.

    §13.3 wants backup age AND last successful restore, and until now
    the command printed "record this in backup.yaml" and left a human to
    do it. That is the friction this codebase has already watched lose
    two decisions, and the test is meant to repeat every 30 days — so
    the one step nobody would keep doing by hand is the one that decides
    whether the control keeps working.

    **Edited line by line rather than re-serialised.** `yaml.safe_dump`
    drops every comment, and this file now carries the whole reasoning
    for D-11, D-59 and D-60 — including why the destination is not what
    D-11 asked for. Losing that to record a date would be a bad trade.

    Recording a FAILURE matters as much as recording a pass: a stale
    `last_tested` with no `last_result` reads as "never tried", and
    those are different facts (§1.1).
    """
    path = Path(control_root) / "config" / "backup.yaml"
    if not path.is_file():
        raise HaltError(f"no backup.yaml at {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    section = None
    written = []
    for index, line in enumerate(lines):
        if not line.startswith((" ", "\t")) and line.rstrip().endswith(":"):
            section = line.split(":", 1)[0].strip()
            continue
        if section != "restore_test":
            continue
        stripped = line.strip()
        if stripped.startswith("last_tested:"):
            lines[index] = f"  last_tested: {on_date.isoformat()}"
            written.append("last_tested")
        elif stripped.startswith("last_result:"):
            lines[index] = f"  last_result: {'PASS' if passed else 'FAIL'}"
            written.append("last_result")

    if len(written) != 2:
        raise HaltError(
            "backup.yaml has no restore_test.last_tested / last_result to "
            f"write (found: {', '.join(written) or 'neither'}). Not guessing "
            "where to put them.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"recorded in {path.name}: last_tested {on_date:%d-%b-%Y}, " \
           f"last_result {'PASS' if passed else 'FAIL'}"
