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
from .db import connect, ensure_schema, integrity_check
from .scope_statutory import normalise as normalise_scope
from .states import State, validate_state
from .transport import assert_route_permitted


@dataclass
class StartupReport:
    config: Config
    state: State
    audit: AuditLog
    db_path: Path
    open_disputes: int
    open_threads: int
    active_absences: int
    # Tables this startup had to create on an existing database. Empty
    # on a normal run; non-empty means the code was newer than the
    # database and the difference has just been applied (§5.2).
    schema_added: tuple = ()
    # What Control is permitted to do this run (proposed D-15). FULL is
    # the charter as written; STATUTORY_ONLY refuses every capability
    # that would read a mailbox or evaluate a person's work.
    scope: str = "FULL"


def run_startup(
    control_root: Path,
    ub_root: Path,
    run_mode: str,
    learning_mode: str,
    maturity_level: int,
    today: str,
    scope: str = "FULL",
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

    # An interim transport route is legal only in the phases it was
    # granted for (§5.1, D-08). Checked here, where the run mode is
    # known, rather than left to be remembered at Phase 2.
    assert_route_permitted(config["transport"], run_mode)

    # The operating scope, validated here with the run mode rather than
    # trusted at the point of use. An unrecognised value halts: the
    # default would be the wider scope, and a typo must not widen what
    # Control may read (§5.6).
    scope = normalise_scope(scope)

    # 2
    db_path = control_root / "data" / "control.db"
    conn = connect(db_path)
    try:
        integrity_check(conn)
        # Before the state is read, not after. `ensure_schema` used to
        # run only when the file was absent, so a table added after a
        # deployment never reached a database already in the field —
        # the code expected it and the first query failed at the point
        # of use. Every statement is IF NOT EXISTS, so this is a no-op
        # on a current database and is reported when it is not.
        schema_added = tuple(ensure_schema(conn))
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
            "scope": scope,
            "date": today,
            "chain": detail,
            **({"schema_added": list(schema_added)} if schema_added else {}),
        },
    )
    return StartupReport(
        scope=scope,
        config=config,
        state=state,
        audit=audit,
        db_path=db_path,
        open_disputes=open_disputes,
        open_threads=open_threads,
        active_absences=active_absences,
        schema_added=schema_added,
    )
