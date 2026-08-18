"""Event-driven statutory windows — §2.1, execution order B1 and B4.

Most class 1 obligations recur: VAT is due at the end of the following
month whether or not anything happened. Two do not. The ETA rejection
clearance window starts when ETA rejects an invoice, and the social
insurance headcount declaration starts when someone joins or leaves.
Until the event exists there is no date to compute, and inventing one
is the failure §2.1 rates worse than having none.

So these obligations are tracked from a register of events rather than
from a cadence. `parse_due` refuses their rules on purpose; this module
is where they become deadlines.

**The deadline is computed from the event date, never the registration
date (B4).** HR registering a joiner five working days after the fact
consumes five days of the thirty. Computing from registration would
report a comfortable thirty-day window that does not exist, and would
hide the erosion that is the whole reason B4 exists. The erosion is
computed here and reported as a finding on the process, never on the
person who registered it (§1.4, §1.6).

**Detection and tracking are different problems.** M1 keeps Control on
`control@` only, so ETA rejections — which arrive in `accounts@` — are
invisible to it. A human enters them. That is why `detection` is a
stored column rather than an assumption: an event register that cannot
say which of its rows a machine saw and which a human remembered is
reporting confidence it has not got.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .enforce import TrackedItem

# Event windows the charter measures in calendar days, not working
# days. §8.3's working calendar is explicitly overridden for class 1
# and 2 — "Class 1 and 2 ignore all of this" — so a seven-day window
# that lands on a Friday is due on that Friday.
_ISO = "%Y-%m-%d"


@dataclass(frozen=True)
class OpenEvent:
    """One event whose statutory clock is still running."""

    row_id: int
    obligation_id: str
    event_type: str
    event_date: date
    registered_at: date
    reference: str | None
    detection: str

    @property
    def registration_lag_days(self) -> int:
        """Days between the event and Control being told about it.

        Positive means the window was already running before Control
        could see it. This is the number B4 exists to keep visible.
        """
        return (self.registered_at - self.event_date).days


def _as_date(value: str) -> date:
    return datetime.strptime(str(value)[:10], _ISO).date()


def record_event(conn, obligation_id: str, event_type: str, event_date: date,
                 reference: str | None, detection: str,
                 submitted_by: str, registered_at: date | None = None,
                 source: str = "LIVE") -> int:
    """Register an event that starts a statutory clock.

    `registered_at` defaults to today rather than to `event_date`,
    because backdating the registration would erase the lag this table
    exists to record.
    """
    if detection not in ("MANUAL", "OBSERVED"):
        raise ValueError(f"detection must be MANUAL or OBSERVED, not {detection!r}")
    registered = registered_at or date.today()
    cursor = conn.execute(
        "INSERT INTO statutory_events (obligation_id, event_type, event_date,"
        " registered_at, reference, detection, submitted_by, submitted_at,"
        " source) VALUES (?,?,?,?,?,?,?,?,?)",
        (obligation_id, event_type, event_date.isoformat(),
         registered.isoformat(), reference, detection, submitted_by,
         registered.isoformat(), source),
    )
    conn.commit()
    return int(cursor.lastrowid)


def discharge_event(conn, event_id: int, discharged_on: date,
                    declared_by: str, reference: str | None = None,
                    source: str = "LIVE") -> int:
    """Record that the obligation started by an event has been met.

    The event row is untouched — it is append-only, and the event still
    happened. Closure is its own fact.
    """
    cursor = conn.execute(
        "INSERT INTO statutory_event_closures (event_id, discharged_on,"
        " declared_by, reference, submitted_by, submitted_at, source)"
        " VALUES (?,?,?,?,?,?,?)",
        (event_id, discharged_on.isoformat(), declared_by, reference,
         declared_by, discharged_on.isoformat(), source),
    )
    conn.commit()
    return int(cursor.lastrowid)


def open_events(conn) -> list[OpenEvent]:
    """Every event whose clock is still running, oldest first."""
    rows = conn.execute(
        "SELECT e.id, e.obligation_id, e.event_type, e.event_date,"
        "       e.registered_at, e.reference, e.detection"
        "  FROM statutory_events e"
        " WHERE NOT EXISTS (SELECT 1 FROM statutory_event_closures c"
        "                    WHERE c.event_id = e.id)"
        " ORDER BY e.event_date, e.id"
    ).fetchall()
    return [OpenEvent(
        row_id=int(r[0]), obligation_id=str(r[1]), event_type=str(r[2]),
        event_date=_as_date(r[3]), registered_at=_as_date(r[4]),
        reference=r[5], detection=str(r[6]),
    ) for r in rows]


def observed_cadence_gaps(logs_dir, statutory_config: dict | None, conn,
                          today: date) -> list[str]:
    """Did Control actually run often enough for these windows? — B1.

    B1 says the ETA rejection check runs daily, because a weekly check
    on a seven-day window burns six of the seven days. Control cannot
    schedule itself: it runs when a person or a task scheduler runs it.
    So the only enforcement available is to observe its own cadence and
    report it, which is what this does.

    The evidence is the audit log's daily files — one per day Control
    ran (§5.3). Their names are the record of when it was awake, and a
    missing day while a seven-day clock was running is a fact, not an
    inference.
    """
    from pathlib import Path

    rules = {oid: rule for oid, rule in _window_rules(statutory_config).items()
             if rule.get("check_frequency") == "daily"}
    if not rules:
        return []

    running = {e.obligation_id for e in open_events(conn)} & set(rules)
    if not running:
        return []

    ran = sorted(
        datetime.strptime(path.stem, _ISO).date()
        for path in Path(logs_dir).glob("????-??-??.jsonl")
        if _is_iso(path.stem)
    )
    shortest = min((rules[oid].get("window_days") or 0) for oid in running)
    prior = [day for day in ran if day < today]
    if not prior:
        return [
            "DAILY CHECK: an event window requiring a daily check is open ("
            + ", ".join(sorted(running)) + ") and there is no prior cycle on "
            "record. Control has no evidence it has been running daily, and "
            f"the shortest window open is {shortest} days (B1)."
        ]

    missed = (today - prior[-1]).days - 1
    if missed <= 0:
        return []
    return [
        f"DAILY CHECK: Control last ran on {prior[-1]:%d-%b-%Y}; "
        f"{missed} day(s) since then had no cycle, while an event "
        "window requiring a daily "
        "check was open (" + ", ".join(sorted(running)) + "). The shortest "
        f"window open is {shortest} days, so {missed} of those {shortest} "
        "passed with nothing alerted (B1)."
    ]


def _is_iso(stem: str) -> bool:
    try:
        datetime.strptime(stem, _ISO)
    except ValueError:
        return False
    return True


def _window_rules(statutory_config: dict | None) -> dict[str, dict]:
    """The obligations that are tracked from events rather than a cadence."""
    rules = {}
    for row in (statutory_config or {}).get("obligations") or []:
        if row.get("mechanism") == "event_window":
            rules[str(row.get("id") or "")] = row
    return rules


def build_event_items(conn, statutory_config: dict | None, today: date
                      ) -> tuple[list[TrackedItem], list[str]]:
    """Turn open events into class 1 tracked items, and name every refusal.

    Returns tracked items and gaps. A gap here is not the same kind of
    silence as a missing calendar rule: the obligation is configured and
    the machinery works, but either nobody has told Control the event
    happened, or the window length itself was never established.
    """
    rules = _window_rules(statutory_config)
    tracked: list[TrackedItem] = []
    gaps: list[str] = []

    events = open_events(conn)
    by_obligation: dict[str, int] = {}
    for event in events:
        by_obligation[event.obligation_id] = \
            by_obligation.get(event.obligation_id, 0) + 1

        rule = rules.get(event.obligation_id)
        if rule is None:
            gaps.append(
                f"statutory_events row {event.row_id}: obligation "
                f"{event.obligation_id!r} is not configured as an event "
                "window in statutory-calendar.yaml, so no deadline can be "
                "computed from it. The event is recorded and is not being "
                "tracked (§1.1).")
            continue

        window = rule.get("window_days")
        if not isinstance(window, int):
            gaps.append(
                f"{event.obligation_id}: an event is on record "
                f"({event.event_date:%d-%b-%Y}"
                + (f", ref {event.reference}" if event.reference else "")
                + ") but window_days is not set, so the deadline cannot be "
                "computed. The clock is running and Control is not counting "
                "it (O-03).")
            continue

        due = event.event_date + timedelta(days=window)
        label = f"{rule.get('name') or event.obligation_id}"
        if event.reference:
            label += f" — {event.reference}"
        tracked.append(TrackedItem(
            item_id=f"{event.obligation_id}#{event.row_id}",
            obligation_class=1,
            name=label,
            owner=str(rule.get("owner") or "accounts@ubcsis.com").lower(),
            due=due,
        ))

        # The erosion B4 exists to keep visible. Reported against the
        # process, with the target it missed, and never against whoever
        # sent the message (§1.4, §1.6).
        target = rule.get("hr_registration_target_working_days")
        lag = event.registration_lag_days
        if lag > 0:
            remaining = (due - today).days
            note = (
                f"{event.obligation_id} event of {event.event_date:%d-%b-%Y}"
                + (f" (ref {event.reference})" if event.reference else "")
                + f" was registered {lag} day(s) after it happened, so "
                f"{lag} of the {window} days were already spent before "
                f"Control could count them. {remaining} day(s) remain.")
            if isinstance(target, int) and lag > target:
                note += (f" The registration target is {target} working "
                         "day(s); this is a process finding, not a finding "
                         "about the sender.")
            gaps.append(note)

    # An event window with no events is the state that looks like
    # compliance and is not. Nothing is overdue because nothing is
    # recorded, and the reason nothing is recorded may be that Control
    # cannot see where the events arrive (M1).
    for obligation_id, rule in rules.items():
        if by_obligation.get(obligation_id):
            continue
        message = (
            f"{obligation_id}: no events on record, so nothing is being "
            "counted. An empty event register means no event has been "
            "entered — not that none occurred (§1.1).")
        if rule.get("manual_detection"):
            message += (
                " Detection of this event is MANUAL: "
                + " ".join(str(rule.get("manual_detection_reason") or "").split())
            ).rstrip()
        gaps.append(message)

    return tracked, gaps
