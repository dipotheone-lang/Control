"""Retention — charter §12.5, execution order B11.

*"Deletion mechanism — does not exist; build before first retention
falls due. Retention schedule is a document without it."*

Two things stop this from being a straightforward sweep, and both are
in the charter.

**§5.2 makes the record tables append-only, enforced by triggers.**
`submissions`, `findings`, `anomalies`, `disputes` and
`external_threads` refuse DELETE at the database level — which is most
of the personal data the schedule covers. §12.5 requires deletion.
Both are load-bearing and for those tables they cannot both hold. This
module does not resolve that: it reports every row past its period that
cannot be removed, so the size of the problem is visible now rather
than at a data-subject request.

**O-10 is open**, so no period here is confirmed by counsel. The engine
refuses to delete on an unconfirmed schedule, and refuses any period
below the statutory floor even when confirmed. Deleting a commercial
book early may breach a five-year minimum, and deletion is the one
operation this system cannot undo — so the asymmetry runs the other
way from everywhere else: when in doubt, keep.

Reporting costs nothing and runs regardless. A schedule nobody measures
against is the document B11 is complaining about.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from .db import APPEND_ONLY

# Deliberately not `relativedelta`: an approximate month here would
# shift a deletion date by days, and the direction of the error decides
# whether a record is removed before its statutory minimum.
_DAYS_PER_MONTH = 30.436875


def cutoff(months: int, today: date) -> date:
    return today - timedelta(days=round(months * _DAYS_PER_MONTH))


@dataclass
class Due:
    """One class of record, and what is past its period."""

    class_id: str
    name: str
    months: int
    rows: int = 0
    files: int = 0
    bytes_on_disk: int = 0
    blocked: list = field(default_factory=list)   # (what, why)
    deletable_paths: list = field(default_factory=list)

    @property
    def anything(self) -> bool:
        return bool(self.rows or self.files)


def _row_count(conn, table: str, before: date) -> int:
    try:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE posted_at < ?",
            (before.isoformat(),)).fetchone()
    except Exception:
        return 0
    return int(row[0]) if row else 0


def survey(conn, control_root: Path, config: dict | None,
           today: date) -> list[Due]:
    """What is past its retention period, and what can be done about it."""
    config = config or {}
    control_root = Path(control_root)
    out: list[Due] = []

    for entry in config.get("classes") or []:
        months = int(entry.get("months") or 0)
        if not months:
            continue
        due = Due(class_id=str(entry.get("id") or ""),
                  name=str(entry.get("name") or entry.get("id") or ""),
                  months=months)
        before = cutoff(months, today)

        if entry.get("never_delete"):
            due.blocked.append((
                due.name,
                "never swept at any age — deletion is a chain break and a "
                "chain break is a critical incident (§13.3)"))

        for table in entry.get("tables") or []:
            count = _row_count(conn, table, before)
            if not count:
                continue
            due.rows += count
            if table in APPEND_ONLY:
                due.blocked.append((
                    f"{count} row(s) in {table}",
                    "§5.2 append-only — DELETE is blocked by a trigger, not "
                    "by convention. §12.5 requires deletion and the two "
                    "cannot both hold here"))
            elif entry.get("never_delete"):
                pass
            else:
                due.blocked.append((
                    f"{count} row(s) in {table}",
                    "deletable, but held: the schedule is not confirmed "
                    "by counsel (O-10)"))

        for relative in entry.get("paths") or []:
            folder = control_root / relative
            if not folder.is_dir():
                continue
            for path in folder.rglob("*"):
                try:
                    if not path.is_file():
                        continue
                    modified = date.fromtimestamp(path.stat().st_mtime)
                    if modified >= before:
                        continue
                    due.files += 1
                    due.bytes_on_disk += path.stat().st_size
                    if entry.get("never_delete"):
                        continue
                    due.deletable_paths.append(path)
                except OSError:
                    continue

        if due.anything or due.blocked:
            out.append(due)
    return out


def blockers(config: dict | None) -> list[str]:
    """Why nothing is deleted today, in the order that matters."""
    config = config or {}
    reasons = []
    if not config:
        reasons.append(
            "retention.yaml is missing. Nothing is measured and nothing is "
            "deleted — §12.5's schedule does not exist on this machine.")
        return reasons
    if not config.get("confirmed_by_counsel"):
        reasons.append(
            "The schedule is not confirmed by counsel (O-10). Deleting a "
            "commercial book before its statutory minimum is not "
            "recoverable, and Egyptian commercial and tax law impose "
            "minimums this schedule has not been checked against — so the "
            "engine reports and does not act.")
    floor = int(config.get("statutory_floor_months") or 0)
    if floor:
        # Per class, and only where the class carries commercial or
        # supporting financial records. Applying the floor to everything
        # would hold an anomaly flag for five years because a rule about
        # ledgers says so — personal data kept longer than needed, which
        # is the same failure pointed the other way.
        under = [str(c.get("id")) for c in config.get("classes") or []
                 if c.get("statutory_floor_applies")
                 and int(c.get("months") or 0) < floor
                 and not c.get("never_delete")]
        if under:
            reasons.append(
                f"{len(under)} class(es) carrying commercial or supporting "
                f"records have a period below the {floor}-month statutory "
                f"floor ({', '.join(under)}). A schedule cannot authorise "
                "less than the law requires, so these stay refused even "
                "once counsel confirms the rest.")
    return reasons


def render(survey_result: list[Due], why_blocked: list[str],
           config: dict | None, today: date) -> str:
    config = config or {}
    lines = [
        f"# RETENTION — {today:%d-%b-%Y}",
        "",
        "§12.5, execution order B11. What is past its period, and what "
        "can be done about it.",
        "",
        "## Nothing was deleted",
        "",
    ]
    if not why_blocked:
        lines.append("No blocker recorded — see the classes below for what "
                     "would be swept.")
    for reason in why_blocked:
        lines.append(f"- {reason}")
    lines += ["", "---", "", "## Past its period", ""]

    if not survey_result:
        lines += [
            "Nothing. That is a young system rather than a clean one — the "
            "shortest period here is 3 months and the database was created "
            "recently, so this section reads empty until the first class "
            "ages out (§1.1).",
            "",
        ]
    for due in survey_result:
        lines += [f"### {due.class_id} — {due.name} ({due.months} months)", ""]
        if due.rows:
            lines.append(f"- {due.rows} database row(s)")
        if due.files:
            lines.append(f"- {due.files} file(s), "
                         f"{due.bytes_on_disk / 1_048_576:.1f} MB")
        for what, why in due.blocked:
            lines.append(f"- **{what}** — {why}")
        lines.append("")

    unbuilt = config.get("unbuilt") or []
    if unbuilt:
        lines += ["---", "", "## What cannot be built without a decision", ""]
        for item in unbuilt:
            lines += [
                f"### {item.get('id')} — {item.get('what')}",
                "",
                " ".join(str(item.get("needs") or "").split()),
                "",
            ]
    return "\n".join(lines)
