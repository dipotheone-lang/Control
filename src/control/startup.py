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
from .scope_statutory import MAILBOX_READ
from .scope_statutory import normalise as normalise_scope
from .scope_statutory import permits as scope_permits
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
    # What Control is permitted to do this run (D-15). FULL is
    # the charter as written; STATUTORY_ONLY refuses every capability
    # that would read a mailbox or evaluate a person's work.
    scope: str = "FULL"
    # Conditions startup would have halted on in a wider scope and
    # proceeded past in this one. Carried out rather than logged and
    # forgotten: a run that quietly tolerated a missing root looks
    # exactly like one where nothing was missing (§1.1).
    gaps: tuple = ()


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
    # Needed before the roots are checked: it decides whether an
    # unreachable UB_ROOT is a partial view or an irrelevance. An
    # unrecognised value still halts (§5.6).
    scope = normalise_scope(scope)
    root_gaps: list[str] = []

    # 5 (checked early — never operate on a partial view, §13.2)
    #
    # §13.2's reason is the partial view: half a drive read as a whole
    # one produces absences that are not absences. A scope that reads no
    # mailbox also reads no drive — no Stage B inventory, no submission
    # files, no contract scan — so there is no view to be partial, and
    # halting would stop a class 1 run because a USB disk is unplugged.
    # It is recorded as a gap instead of being assumed away.
    if not ub_root.is_dir():
        if scope_permits(scope, MAILBOX_READ):
            raise HaltError(f"UB_ROOT unreachable: {ub_root}")
        root_gaps.append(
            f"UB_ROOT unreachable ({ub_root}) — not used in this scope, "
            "which reads no drive and no mailbox (D-15). Nothing was read "
            "from it and nothing was inferred about it; a widened scope "
            "halts on this again.")
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

    # The operating scope, validated here with the run mode rather than
    # trusted at the point of use. An unrecognised value halts: the
    # default would be the wider scope, and a typo must not widen what
    # Control may read (§5.6).
    #
    # (The scope was normalised before the root checks, which needed it.)

    # An interim transport route is legal only in the phases it was
    # granted for (§5.1, D-08). Checked here, where the run mode is
    # known, rather than left to be remembered at Phase 2.
    #
    # Except where the scope reads no mailbox. D-08 refused Outlook in
    # SUPERVISED for two reasons, and D-58 separated them.
    #
    # The first — Outlook sees whatever the Windows profile sees, not the
    # set D-07 authorises — cannot happen under a scope that fetches
    # nothing. It is gone, not accepted.
    #
    # The second — a transport needing a powered laptop cannot hold a
    # class 1 schedule — is still true, and D-58 accepts it with the cost
    # stated: the alternative on this machine was no delivery at all
    # rather than Graph. An alert that cannot leave is written
    # UNDELIVERED and retried, never marked sent.
    #
    # The skip is conditional on the SCOPE, not the run mode, so FULL in
    # SUPERVISED still halts here exactly as D-08 wrote it. Without it
    # §16's own row for D-15 could not be entered at all: the charter
    # declared a state legal that the code refused.
    if scope_permits(scope, MAILBOX_READ):
        assert_route_permitted(config["transport"], run_mode)

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
            # §1.9. Proceeding past a condition a wider scope halts on
            # is a decision this run made, and an unlogged decision did
            # not happen.
            **({"proceeded_past": list(root_gaps)} if root_gaps else {}),
        },
    )
    return StartupReport(
        scope=scope,
        gaps=tuple(root_gaps),
        config=config,
        state=state,
        audit=audit,
        db_path=db_path,
        open_disputes=open_disputes,
        open_threads=open_threads,
        active_absences=active_absences,
        schema_added=schema_added,
    )
