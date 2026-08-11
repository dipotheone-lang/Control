"""Cycle startup — charter §5.6, in order, halting on any failure.

1. Read config/*.yaml — configuration overrides assumptions
2. Verify control.db integrity and the audit-log hash chain
3. Load open obligations, reminders, threads, disputes, absences,
   active learning adaptations
4. Confirm date, period, RUN_MODE, LEARNING_MODE — and that the
   combination is a legal §16 state row
5. Verify UB_ROOT and CONTROL_ROOT reachable
6. Only then touch the mailbox

This module performs 1–5. Step 6 belongs to the mail layer, which must
require a StartupReport to construct — no report, no mailbox.
"""

from dataclasses import dataclass
from pathlib import Path

from . import HaltError
from .audit import AuditLog
from .config import Config, load_config
from .db import connect, init_db, integrity_check
from .states import State, validate_state


@dataclass
class StartupReport:
    config: Config
    state: State
    audit: AuditLog
    db_path: Path
    open_disputes: int
    open_threads: int
    active_absences: int


def run_startup(
    control_root: Path,
    ub_root: Path,
    run_mode: str,
    learning_mode: str,
    maturity_level: int,
    today: str,
) -> StartupReport:
    control_root, ub_root = Path(control_root), Path(ub_root)

    # 5 (checked early — never operate on a partial view, §13.2)
    if not ub_root.is_dir():
        raise HaltError(f"UB_ROOT unreachable: {ub_root}")
    if not control_root.is_dir():
        raise HaltError(f"CONTROL_ROOT unreachable: {control_root}")

    # 1
    config = load_config(control_root / "config")

    # 4 — legal state (v4.3: illegal combination halts, same as integrity)
    declared_mode = config["learning-policy"].get("learning_mode")
    if declared_mode != learning_mode:
        raise HaltError(
            f"LEARNING_MODE mismatch: environment says {learning_mode}, "
            f"learning-policy.yaml says {declared_mode}"
        )
    state = validate_state(maturity_level, run_mode, learning_mode)

    # 2
    db_path = control_root / "data" / "control.db"
    conn = init_db(db_path) if not db_path.exists() else connect(db_path)
    try:
        integrity_check(conn)
        # 3 — load open state
        open_disputes = conn.execute(
            "SELECT COUNT(*) FROM disputes WHERE state = 'PENDING'"
        ).fetchone()[0]
        open_threads = conn.execute(
            "SELECT COUNT(*) FROM external_threads WHERE state = 'OPEN'"
        ).fetchone()[0]
        active_absences = conn.execute(
            "SELECT COUNT(*) FROM absence WHERE from_date <= ? AND to_date >= ?",
            (today, today),
        ).fetchone()[0]
    finally:
        conn.close()

    audit = AuditLog(control_root / "logs")
    ok, detail = audit.verify()
    if not ok:
        raise HaltError(f"audit hash chain broken — critical incident (§13.3): {detail}")

    audit.append(
        "startup",
        {
            "run_mode": run_mode,
            "learning_mode": learning_mode,
            "level": maturity_level,
            "date": today,
            "chain": detail,
        },
    )
    return StartupReport(
        config=config,
        state=state,
        audit=audit,
        db_path=db_path,
        open_disputes=open_disputes,
        open_threads=open_threads,
        active_absences=active_absences,
    )
