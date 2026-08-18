"""Config to engine — the bridge Phase 1 runs on.

`run_cycle` takes obligations, a roster, a calendar and tracked items.
Until now only tests built those by hand, so nothing could actually run
a cycle. This module builds them from `config/*.yaml`.

Three rules govern every function here, and they are the reason this is
a separate module rather than a few lines in the CLI:

**Nothing unapproved is tracked.** §6 ends Phase 0 when the CEO
approves the obligation register. An obligation without
`approved_by_ceo` is a Stage D proposal, and acting on a proposal is
acting on an inference (§1.1). It is skipped and reported.

**Nothing unparseable is guessed.** A due expression this module does
not understand produces a gap, never a date. A wrong deadline is worse
than a missing one: it alerts confidently on the wrong day and teaches
people the system is wrong.

**No config is executed.** C6 manual rules are declared in a small
fixed vocabulary and compiled here. Config is data, never code —
§13.2's rule about email applies with more force to files that decide
what the engine checks.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .calendar import WorkingCalendar
from .cycle import Class3State, SubmissionSpec
from .enforce import Absence, Person, TrackedItem
from .evaluate import ManualRule, ObligationSpec, OpeningRule, TotalRule

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}

_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_FORM = re.compile(r"(?i)^(?P<code>[^\s]+?)(?:\s+(?:rev|revision)\.?\s*"
                   r"(?P<rev>[\w.]+))?$")

# The complete C6 rule vocabulary. Anything else is a gap, not an
# improvisation — see the module docstring on not executing config.
_MANUAL_FORMS = ("field_present", "field_equals", "field_at_least",
                 "field_at_most")


@dataclass
class LoadResult:
    specs: dict = field(default_factory=dict)
    tracked: list = field(default_factory=list)
    roster: dict = field(default_factory=dict)
    calendar: WorkingCalendar = field(default_factory=WorkingCalendar)
    class3_state: dict = field(default_factory=dict)
    gaps: list = field(default_factory=list)

    @property
    def approved(self) -> int:
        return len(self.specs)


# ---- roster and calendar ---------------------------------------------

def build_roster(people_config: dict | None) -> dict[str, Person]:
    roster: dict[str, Person] = {}
    for entry in (people_config or {}).get("people") or []:
        email = str(entry.get("email") or "").lower()
        if not email:
            continue
        # A leaver owns nothing and is escalated to by nobody (§3.3).
        if entry.get("active") is False:
            continue
        roster[email] = Person(
            email=email,
            manager=(str(entry["reports_to"]).lower()
                     if entry.get("reports_to") else None),
            tier=int(entry.get("tier") or 1),
            also_manager=(str(entry["also_reports_to"]).lower()
                          if entry.get("also_reports_to") else None),
            also_domain=entry.get("also_reports_to_domain"),
        )
    return roster


def build_calendar(sla_config: dict | None) -> tuple[WorkingCalendar, list[str]]:
    calendar = ((sla_config or {}).get("working_calendar") or {})
    holidays: list[date] = []
    gaps: list[str] = []
    for raw in calendar.get("holidays") or []:
        if isinstance(raw, date):
            holidays.append(raw)
            continue
        try:
            holidays.append(datetime.fromisoformat(str(raw)).date())
        except ValueError:
            gaps.append(f"sla.yaml: holiday {raw!r} is not a date — ignored, "
                        "and this day will be treated as a working day (§8.3)")
    if not holidays:
        gaps.append(
            "sla.yaml: no public holidays on file. Deadlines will not shift "
            "and class 3 reminders will not suppress for them (§8.3). "
            "Owner: HR."
        )
    return WorkingCalendar(holidays), gaps


# ---- due dates --------------------------------------------------------

def _due_time(expression: str) -> time:
    match = _TIME.search(expression)
    if not match:
        return time(17, 0)
    return time(int(match.group(1)), int(match.group(2)))


# The phrase that marks a refusal as event-driven rather than unreadable.
# Named once because build_statutory counts the two kinds separately —
# they are both silence, but they have different remedies, and a count
# that merged them would tell the CEO to chase the wrong person.
EVENT_WINDOW_MARKER = "is an event-driven window"

# An event-driven window is not a recurring deadline and must never be
# read as one. "7 days from rejection" is the ETA clearance window: it
# starts when ETA rejects an invoice, and the execution order of
# 18-Aug-2026 calls it the tightest statutory window in the system.
# Before this guard the day-of-month branch matched the leading "7" and
# produced day 7 of the month — a confidently wrong statutory date,
# which §2.1 rates worse than no date at all.
_EVENT_WINDOW = re.compile(
    r"\b\d{1,3}\s*(?:calendar\s+|working\s+|business\s+)?days?\s+"
    r"(?:from|after|of)\b")

_MONTHS_BY_NAME = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}
_MONTH_END = re.compile(
    r"end of (?:the )?(following|next|current|same) month|month[- ]end")
_ANNUAL_DATE = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(_MONTHS_BY_NAME) + r")\b"
    r"|\b(" + "|".join(_MONTHS_BY_NAME) + r")\s+(\d{1,2})\b")
_LEAD_DAYS = re.compile(r"[-−]\s*(\d{1,2})\s*working days?")


def _last_day(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def parse_due(expression: str, cadence: str, today: date) -> tuple[datetime | None, str]:
    """The next due datetime for this obligation, or a reason it is unknown.

    Returns (due, problem). Exactly one is set. A cadence this function
    cannot turn into a date must not become a date.
    """
    text = str(expression or "").strip().lower()
    cadence = str(cadence or "").strip().lower()
    if not text:
        return None, "no due expression"

    at = _due_time(text)

    # Event-driven windows are refused before anything else, because
    # every later branch would find a number in them and turn it into a
    # calendar date. They are tracked by the event register, not here.
    if _EVENT_WINDOW.search(text):
        return None, (
            f"{expression!r} {EVENT_WINDOW_MARKER}, not a recurring "
            "deadline — its clock starts on an event, so it is tracked from "
            "the event register rather than from a cadence")

    # Explicit date wins over any cadence.
    explicit = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if explicit:
        try:
            day = datetime.fromisoformat(explicit.group(1)).date()
        except ValueError:
            return None, f"unparseable date {explicit.group(1)!r}"
        return datetime.combine(day, at), ""

    weekday = next((name for name in _WEEKDAYS if name in text), None)
    if weekday is not None:
        if cadence not in ("weekly", "fortnightly", ""):
            return None, (f"cadence {cadence!r} with a weekday due expression — "
                          "ambiguous, not guessed")
        target = _WEEKDAYS[weekday]
        ahead = (target - today.weekday()) % 7
        if cadence == "fortnightly" and ahead == 0:
            ahead = 14
        return datetime.combine(today + timedelta(days=ahead), at), ""

    # "31 March" / "March 31" — a specific day in a named month, which is
    # unambiguous in a way that a bare day-of-month is not.
    annual = _ANNUAL_DATE.search(text)
    if annual:
        day = int(annual.group(1) or annual.group(4))
        name = (annual.group(2) or annual.group(3))
        month = _MONTHS_BY_NAME[name]
        if cadence and cadence not in ("annual", "annually", "yearly", ""):
            return None, (f"cadence {cadence!r} with a fixed calendar date "
                          f"{expression!r} — ambiguous, not guessed")
        try:
            target = date(today.year, month, day)
        except ValueError:
            return None, (f"{day} {name.title()} is not a real date")
        if target < today:
            target = date(today.year + 1, month, day)
        return _apply_lead(datetime.combine(target, at), text)

    # "end of the following month" and its variants. Month-end is a real
    # statutory shape — several Egyptian filings land on it — and it
    # cannot be written as a day-of-month at all, because the day it
    # falls on changes with the month.
    month_end = _MONTH_END.search(text)
    if month_end:
        which = month_end.group(1) or "current"
        year, month = today.year, today.month
        if which in ("following", "next"):
            month += 1
            if month > 12:
                month, year = 1, year + 1
        due = _last_day(year, month)
        if due < today:
            month += 1
            if month > 12:
                month, year = 1, year + 1
            due = _last_day(year, month)
        return _apply_lead(datetime.combine(due, at), text)

    day_of_month = re.search(r"\bday\s*(\d{1,2})\b|^(\d{1,2})\b", text)
    if day_of_month:
        number = int(day_of_month.group(1) or day_of_month.group(2))
        if not 1 <= number <= 28:
            return None, (f"day-of-month {number} — only 1..28 is unambiguous "
                          "across every month")
        if cadence not in ("monthly", "quarterly", "annual", "annually", ""):
            return None, f"cadence {cadence!r} with a day-of-month expression"
        year, month = today.year, today.month
        if today.day > number:
            month += 1
            if month > 12:
                month, year = 1, year + 1
        return datetime.combine(date(year, month, number), at), ""

    return None, f"due expression {expression!r} not understood"


def _apply_lead(due: datetime, text: str) -> tuple[datetime, str]:
    """Shift a statutory date earlier by an operative lead.

    The execution order sets VAT's operative date at five working days
    before the statutory one. The statutory date stays the anchor — the
    lead is when Control acts, not when the law falls due — so the
    subtraction happens here rather than by editing the rule, and a
    lead that is missing simply leaves the statutory date standing.
    """
    lead = _LEAD_DAYS.search(text)
    if not lead:
        return due, ""
    remaining, moved = int(lead.group(1)), due
    while remaining:
        moved -= timedelta(days=1)
        if moved.weekday() not in (4, 5):      # Fri, Sat — §8.3 Sun-Thu week
            remaining -= 1
    return moved, ""


def _period_for(cadence: str, due: datetime) -> str:
    cadence = str(cadence or "").lower()
    if cadence in ("weekly", "fortnightly"):
        iso = due.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if cadence == "quarterly":
        return f"{due.year}-Q{(due.month - 1) // 3 + 1}"
    if cadence in ("annual", "annually", "yearly"):
        return str(due.year)
    return f"{due:%Y-%m}"


# ---- C6 rules, compiled rather than executed -------------------------

def _compile_manual_rule(raw: dict) -> tuple[ManualRule | None, str]:
    kind = str(raw.get("check") or "").strip().lower()
    field_name = raw.get("field")
    clause = str(raw.get("clause") or "")
    requirement = str(raw.get("requirement") or "")

    if kind not in _MANUAL_FORMS:
        return None, (f"manual rule check {kind!r} is not one of "
                      f"{', '.join(_MANUAL_FORMS)} — C6 will not run for it")
    if not field_name:
        return None, f"manual rule {clause!r} names no field"
    if not clause or not requirement:
        return None, ("manual rule needs both clause and requirement — §1.2 "
                      "requires the clause quoted in the finding")

    expected = raw.get("value")

    def predicate(fields: dict, _kind=kind, _f=field_name, _v=expected) -> bool:
        value = fields.get(_f)
        if _kind == "field_present":
            return value not in (None, "")
        if value in (None, ""):
            return False
        if _kind == "field_equals":
            return str(value).strip().lower() == str(_v).strip().lower()
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        return number >= float(_v) if _kind == "field_at_least" else number <= float(_v)

    return ManualRule(clause=clause, requirement=requirement,
                      predicate=predicate), ""


# ---- obligations ------------------------------------------------------

def _surname(roster_names: dict, email: str) -> str:
    name = roster_names.get(email, "")
    return name.split()[-1] if name else (email.split("@")[0] or email)


def build_obligations(obligations_config: dict | None, people_config: dict | None,
                      today: date) -> tuple[dict, list, list[str]]:
    """(specs, tracked class 3/4 items, gaps) from obligations.yaml."""
    specs: dict[str, SubmissionSpec] = {}
    tracked: list[TrackedItem] = []
    gaps: list[str] = []

    names = {str(p.get("email", "")).lower(): str(p.get("name", ""))
             for p in (people_config or {}).get("people") or []}
    rows = (obligations_config or {}).get("obligations") or []
    if not rows:
        gaps.append(
            "obligations.yaml is empty. The register is populated from Phase 0 "
            "Stage D and approved by the CEO — that approval is what ends "
            "Phase 0 (§6). Until then no class 3 obligation is tracked, and "
            "an empty horizon means an empty register, not a clear week."
        )
        return specs, tracked, gaps

    for row in rows:
        obligation_id = str(row.get("id") or "").strip()
        if not obligation_id:
            gaps.append("obligations.yaml: an entry has no id — skipped")
            continue

        if not row.get("approved_by_ceo"):
            gaps.append(
                f"{obligation_id}: not approved by the CEO — a Stage D "
                "proposal, not an obligation. Not tracked (§6)."
            )
            continue

        owner = str(row.get("owner") or "").lower()
        if not owner:
            gaps.append(f"{obligation_id}: no owner — not tracked")
            continue

        obligation_class = int(row.get("class") or 3)
        cadence = str(row.get("cadence") or "")
        due, problem = parse_due(row.get("due", ""), cadence, today)
        if due is None:
            gaps.append(f"{obligation_id}: {problem} — no deadline computed, "
                        "so nothing is alerted for it (§1.1)")
            continue

        form = str(row.get("form") or "").strip()
        match = _FORM.match(form) if form else None
        form_code = match.group("code") if match else ""
        revision = (match.group("rev") or "") if match else ""
        if not form_code:
            gaps.append(f"{obligation_id}: no form code — C2 form control "
                        "cannot be checked")
        elif not revision:
            gaps.append(f"{obligation_id}: form {form_code} has no revision — "
                        "C2 cannot detect a superseded revision")

        rules: list[ManualRule] = []
        for raw in row.get("manual_rules") or []:
            rule, why = _compile_manual_rule(raw)
            if rule is None:
                gaps.append(f"{obligation_id}: {why}")
            else:
                rules.append(rule)
        if not rules and row.get("governing_clause"):
            gaps.append(
                f"{obligation_id}: governing clause "
                f"{row['governing_clause']!r} recorded but no checkable manual "
                "rule — C6 reports NOT ASSESSED rather than CONFORMS"
            )

        spec = ObligationSpec(
            obligation_id=obligation_id,
            name=str(row.get("name") or obligation_id),
            form_code=form_code,
            current_revision=revision,
            due=due,
            mandatory_fields=[str(f) for f in row.get("mandatory_fields") or []],
            totals=[TotalRule(stated_field=str(t["stated"]),
                              component_fields=[str(c) for c in t["components"]])
                    for t in row.get("totals") or [] if t.get("stated")],
            openings=[OpeningRule(opening_field=str(o["opening"]),
                                  prior_closing_field=str(o["prior_closing"]))
                      for o in row.get("openings") or [] if o.get("opening")],
            manual_rules=rules,
        )
        specs[obligation_id] = SubmissionSpec(
            spec=spec,
            mapping={str(k): str(v) for k, v in (row.get("mapping") or {}).items()},
            surname=_surname(names, owner),
            period=_period_for(cadence, due),
        )
        if obligation_class in (3, 4):
            tracked.append(TrackedItem(
                item_id=obligation_id,
                obligation_class=obligation_class,
                name=spec.name,
                owner=owner,
                due=due.date(),
                financial=bool(row.get("financial")),
                monthly=cadence in ("monthly", "quarterly", "annual", "annually"),
                domain=row.get("domain"),
            ))
    return specs, tracked, gaps


# ---- class 1 ----------------------------------------------------------

def build_statutory(statutory_config: dict | None, today: date
                    ) -> tuple[list, list[str]]:
    """Class 1 tracked items, and the reason most of them are missing.

    §2.1 says unverified rules still alert, erring early. That is only
    possible where a date exists. A rule reading
    `UNVERIFIED — CONFIRM WITH ADVISOR` has no date at all, so it
    produces no alert — and the gap must be loud, because a silent class
    1 register is the most expensive silence in this system.
    """
    tracked: list[TrackedItem] = []
    gaps: list[str] = []
    config = statutory_config or {}
    awaiting_date = 0
    awaiting_event = 0

    for row in config.get("obligations") or []:
        obligation_id = str(row.get("id") or "")
        due, problem = parse_due(row.get("rule", ""), "", today)
        if due is None:
            if EVENT_WINDOW_MARKER in problem:
                awaiting_event += 1
            else:
                awaiting_date += 1
            gaps.append(f"{obligation_id}: {problem} — no class 1 alert "
                        "can fire (O-03)")
            continue
        tracked.append(TrackedItem(
            item_id=obligation_id, obligation_class=1,
            name=str(row.get("name") or obligation_id),
            owner=str(row.get("owner") or "accounts@ubcsis.com").lower(),
            due=due.date(),
        ))

    # Coverage before provenance. Once some rows carry dates, a reader
    # sees alerts and can take the register for coverage — so the share
    # that is dark is stated as a share, not left implicit in a list of
    # per-row lines. Two-thirds silent is a different fact from a rule
    # nobody has verified, and the report has to carry both.
    silent = awaiting_date + awaiting_event
    if silent and tracked:
        detail = f"{awaiting_date} await a date"
        if awaiting_event:
            detail += (f", {awaiting_event} are event-driven and await the "
                       "event register")
        gaps.append(
            f"statutory-calendar.yaml: {len(tracked)} of {len(tracked) + silent}"
            f" class 1 obligations have a usable date. The other {silent} fire "
            f"no alert at all ({detail}) — and class 1 is the only class "
            "carrying fines, so that share is the highest-priority gap in the "
            "system (O-03).")

    # The provenance line goes LAST so it reads as a qualification on
    # what was found rather than a preamble to it — and it says which
    # of the two situations this is. "Tracking nothing" and "tracking
    # four dates nobody qualified has checked" are different states
    # with different remedies, and one message for both would have been
    # false in whichever case it did not fit.
    if not config.get("verified_by_advisor"):
        if not tracked:
            gaps.append(
                "statutory-calendar.yaml: no statutory deadline has a usable "
                "date, so class 1 — the only class carrying fines — is "
                "tracking nothing. This is the highest-priority gap in the "
                "system (O-03).")
        elif config.get("ceo_stated"):
            gaps.append(
                f"statutory-calendar.yaml: {len(tracked)} class 1 deadline(s) "
                "are alerting on CEO-STATED dates, not advisor-verified ones "
                f"({config.get('source', 'source not recorded')}). They alert "
                "early and erring early is the chartered behaviour (§2.1) — "
                "but nobody qualified has confirmed them, and time passing "
                "does not confirm them. O-03 stays open until a named "
                "advisor does.")
        else:
            gaps.append(
                f"statutory-calendar.yaml: {len(tracked)} class 1 deadline(s) "
                "are alerting on dates with no recorded provenance at all — "
                "neither advisor-verified nor CEO-stated (O-03).")
    return tracked, gaps


# ---- absences ---------------------------------------------------------

def build_class3_state(conn, tracked: list, today: date,
                       periods: dict | None = None) -> dict:
    """Submission, absence and dispute state per tracked item.

    An item already submitted for its period stops the ladder (§8.2);
    a registered absence routes to the delegate rather than escalating
    (§3.3); a pending dispute suspends the clock (§8.4).
    """
    periods = periods or {}
    state: dict[str, Class3State] = {}
    for item in tracked:
        row = conn.execute(
            "SELECT delegate FROM absence WHERE email = ? AND from_date <= ?"
            " AND to_date >= ? ORDER BY id DESC LIMIT 1",
            (item.owner, today.isoformat(), today.isoformat()),
        ).fetchone()
        # A dispute suspends the clock on ITS item (§8.4), so the link
        # runs through the disputed submission's obligation rather than
        # matching a text id against an integer key.
        disputed = conn.execute(
            "SELECT 1 FROM disputes d JOIN submissions s"
            " ON s.id = d.submission_id"
            " WHERE d.state = 'PENDING' AND s.obligation_id = ? LIMIT 1",
            (item.item_id,),
        ).fetchone()
        submitted = conn.execute(
            "SELECT 1 FROM submissions WHERE obligation_id = ? AND period = ?"
            " AND verdict IN ('ACCEPTED','ACCEPTED_WITH_OBSERVATIONS',"
            " 'RECEIVED_ON_TIME','RECEIVED_LATE') LIMIT 1",
            (item.item_id, periods.get(item.item_id, "")),
        ).fetchone()
        state[item.item_id] = Class3State(
            submitted=bool(submitted),
            absence=Absence(delegate=row[0]) if row else None,
            dispute_active=bool(disputed),
        )
    return state


# ---- the whole thing --------------------------------------------------

def load_for_cycle(config, conn, today: date, logs_dir=None) -> LoadResult:
    result = LoadResult()
    calendar, calendar_gaps = build_calendar(config["sla"])
    result.calendar = calendar
    result.roster = build_roster(config["people"])
    result.gaps += calendar_gaps

    specs, class3, obligation_gaps = build_obligations(
        config["obligations"], config["people"], today)
    result.specs = specs
    result.gaps += obligation_gaps

    statutory, statutory_gaps = build_statutory(
        config["statutory-calendar"], today)
    result.gaps += statutory_gaps

    # Event-driven class 1 windows. `build_statutory` refuses these on
    # purpose — their clock starts on an event, so there is no cadence
    # to compute from — and this is where the recorded events become
    # deadlines (execution order B1, B4).
    from .events import build_event_items, observed_cadence_gaps

    events, event_gaps = build_event_items(
        conn, config["statutory-calendar"], today)
    result.gaps += event_gaps

    # B1: Control cannot schedule itself, so the only enforcement of
    # "checked daily" available to it is to observe the cadence it
    # actually ran at and report the misses. The evidence is its own
    # audit log, so this needs the log directory.
    if logs_dir is not None:
        result.gaps += observed_cadence_gaps(
            logs_dir, config["statutory-calendar"], conn, today)

    result.tracked = class3 + statutory + events
    result.class3_state = build_class3_state(
        conn, class3, today,
        {oid: s.period for oid, s in specs.items()})
    return result


def load_class2(conn) -> list:
    """Class 2 deadlines from the §2.2 registers."""
    from . import registers as reg

    return [deadline.item for deadline in reg.all_deadlines(conn)]
