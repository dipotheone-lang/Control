"""Enforcement engine — charter §8.1 (deadline alerts), §8.2 (ladder),
§8.3 (working calendar), §8.4 (dispute suspension), §3.3 (absence).

This module PLANS actions; it never sends. Every action carries a
dedupe_key so the caller can enforce idempotency against the register
before any send (§1.10) — emitting a stage twice is safe, sending it
twice is not. Planning is resumable: a crashed cycle re-plans from state
and the dedupe keys make re-sends impossible (§13.2).

Class rules:
- Class 1/2 ignore the working calendar entirely and are never
  suppressed — not for weekends, holidays, leave, or reminder limits.
- Class 3 walks the ladder on working days only; deadlines shift to the
  next working day (§8.3).
- Class 4 gets a single reminder, no escalation.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from .calendar import WorkingCalendar

# Alert schedules: working-calendar-independent day offsets before due.
CLASS1_SCHEDULE = (7, 3, 1, 0)
CLASS2_SCHEDULE = (14, 7, 3, 1, 0)
TENDER_SCHEDULE = (14, 7, 3, 2, 1, 0)          # §2.2 — morning-of on day 0
INSTRUMENT_SCHEDULE = (60, 30, 14, 7, 0)       # §2.2 financial instruments
ACCREDITATION_SCHEDULE = (90, 60, 30, 0)       # §2.2 accreditations


@dataclass
class Person:
    email: str
    manager: str | None
    tier: int
    # Matrix reporting: a second line that owns a specific domain. Hadeer
    # reports to the CFO, but to HR on HR matters — escalating an HR item
    # to the CFO would route a personnel question to the wrong manager.
    also_manager: str | None = None
    also_domain: str | None = None

    def manager_for(self, domain: str | None) -> str | None:
        if domain and self.also_domain and domain == self.also_domain:
            return self.also_manager
        return self.manager


@dataclass
class TrackedItem:
    item_id: str
    obligation_class: int          # 1..4
    name: str
    owner: str
    due: date
    financial: bool = False        # class 3: L2 adds CFO instead of COO
    monthly: bool = False          # class 3: pre-reminder at -48h instead of -24h
    schedule: tuple | None = None  # class 1/2 override (tender, instrument, …)
    domain: str | None = None      # selects a matrix manager (e.g. "hr")


@dataclass
class Absence:
    delegate: str | None           # None => delegation not registered (§3.3)


@dataclass
class Action:
    kind: str                      # ALERT | PRE_REMINDER | DEADLINE | L1 | L2 | L3 | PROCESS_FINDING
    item_id: str
    recipients: list[str]
    cc: list[str] = field(default_factory=list)
    dedupe_key: str = ""
    note: str = ""
    never_suppress: bool = False   # class 1/2: exempt from all limits


class Enforcer:
    def __init__(self, cal: WorkingCalendar, roster: dict[str, Person],
                 ceo: str, coo: str, cfo: str):
        self.cal = cal
        self.roster = roster
        self.ceo, self.coo, self.cfo = ceo, coo, cfo

    # -- class 1 & 2: the deadline engine (§8.1) ---------------------------

    def plan_class12(self, item: TrackedItem, today: date) -> list[Action]:
        """Fixed schedule, calendar-blind, never suppressed."""
        assert item.obligation_class in (1, 2)
        schedule = item.schedule or (
            CLASS1_SCHEDULE if item.obligation_class == 1 else CLASS2_SCHEDULE
        )
        days_until = (item.due - today).days
        actions: list[Action] = []
        if days_until in schedule and days_until > 0:
            actions.append(Action(
                kind="ALERT", item_id=item.item_id,
                recipients=[item.owner],
                dedupe_key=f"{item.item_id}:T-{days_until}",
                note=f"{item.name}: due in {days_until} days ({item.due:%d-%b-%Y})",
                never_suppress=True,
            ))
        elif days_until == 0 and 0 in schedule:
            # Day-of: class 1 -> CEO + CFO immediately; class 2 -> owner + CEO.
            recipients = (
                [self.ceo, self.cfo] if item.obligation_class == 1
                else [item.owner, self.ceo]
            )
            actions.append(Action(
                kind="ALERT", item_id=item.item_id,
                recipients=recipients,
                dedupe_key=f"{item.item_id}:DAY-OF",
                note=f"{item.name}: due TODAY ({item.due:%d-%b-%Y}) — unresolved",
                never_suppress=True,
            ))
        elif days_until < 0:
            # Past due and unresolved: stays in front of the CEO daily.
            recipients = (
                [self.ceo, self.cfo] if item.obligation_class == 1
                else [item.owner, self.ceo]
            )
            actions.append(Action(
                kind="ALERT", item_id=item.item_id,
                recipients=recipients,
                dedupe_key=f"{item.item_id}:OVERDUE:{today.isoformat()}",
                note=f"{item.name}: {-days_until} days past deadline — unresolved",
                never_suppress=True,
            ))
        return actions

    # -- class 3: the ladder (§8.2) ----------------------------------------

    def plan_class3(
        self,
        item: TrackedItem,
        today: date,
        *,
        submitted: bool = False,
        dispute_active: bool = False,
        absence: Absence | None = None,
        reliable: bool = False,
    ) -> list[Action]:
        assert item.obligation_class == 3
        if submitted:
            return []
        # §8.4: dispute suspends the escalation clock on the item.
        if dispute_active:
            return []
        # §8.3: no class 3 reminders on non-working days.
        if not self.cal.is_working_day(today):
            return []

        due = self.cal.shift_deadline(item.due)
        owner = self.roster.get(item.owner)
        manager = owner.manager_for(item.domain) if owner else None

        # §3.3: never escalate an item owned by someone on registered leave.
        if absence is not None:
            if today > due:
                return []  # escalation suspended during leave
            target, note = (absence.delegate, "") if absence.delegate else (
                manager, "delegation not registered — process finding (§3.3)"
            )
            actions = self._pre_and_deadline(item, today, due, target or item.owner,
                                             reliable=reliable)
            if not absence.delegate and actions:
                actions.append(Action(
                    kind="PROCESS_FINDING", item_id=item.item_id,
                    recipients=[manager] if manager else [],
                    dedupe_key=f"{item.item_id}:NO-DELEGATE",
                    note=note,
                ))
            return actions

        if today <= due:
            return self._pre_and_deadline(item, today, due, item.owner, reliable=reliable)

        days_late = self.cal.working_days_between(due, today)
        actions: list[Action] = []
        # Emit every stage whose threshold is reached; the caller's
        # idempotency check drops the already-sent ones (§1.10). A crashed
        # cycle therefore never skips a stage and never repeats one.
        if days_late >= 1:
            recipients = [item.owner]
            cc = [manager] if manager else []
            # §3.2 exception: a tier-3 owner reporting to the CEO reaches
            # the CEO at L1 — cc already IS the CEO; nothing special to do,
            # the ladder continues on schedule below.
            actions.append(Action("L1", item.item_id, recipients, cc,
                                  f"{item.item_id}:L1",
                                  f"{item.name}: 1+ working days past due"))
        if days_late >= 3:
            escalation = self.cfo if item.financial else self.coo
            recipients = [item.owner] + ([manager] if manager else []) + [escalation]
            actions.append(Action("L2", item.item_id, _dedup(recipients), [],
                                  f"{item.item_id}:L2",
                                  f"{item.name}: 3+ working days past due"))
        if days_late >= 5:
            escalation = self.cfo if item.financial else self.coo
            recipients = [item.owner] + ([manager] if manager else []) + [escalation, self.ceo]
            actions.append(Action("L3", item.item_id, _dedup(recipients), [],
                                  f"{item.item_id}:L3",
                                  f"{item.name}: 5+ working days past due — final escalation; "
                                  "stays open in every management report (§8.2)"))
        return actions

    def _pre_and_deadline(self, item: TrackedItem, today: date, due: date,
                          recipient: str, *, reliable: bool) -> list[Action]:
        actions: list[Action] = []
        lead_days = 2 if item.monthly else 1
        pre_date = due - timedelta(days=lead_days)
        # §8.2 reliability suppression: reward reliability with silence —
        # the pre-deadline reminder only; the deadline notice always fires.
        if today == pre_date and not reliable:
            actions.append(Action(
                "PRE_REMINDER", item.item_id, [recipient], [],
                f"{item.item_id}:PRE",
                f"{item.name}: due {due:%d-%b-%Y}",
            ))
        if today == due:
            actions.append(Action(
                "DEADLINE", item.item_id, [recipient], [],
                f"{item.item_id}:DEADLINE",
                f"{item.name}: due today",
            ))
        return actions

    # -- class 4: single reminder (§2) -------------------------------------

    def plan_class4(self, item: TrackedItem, today: date) -> list[Action]:
        assert item.obligation_class == 4
        if today == self.cal.shift_deadline(item.due):
            return [Action("DEADLINE", item.item_id, [item.owner], [],
                           f"{item.item_id}:DEADLINE", f"{item.name}: due today")]
        return []

    # -- consolidation (§8.2) ----------------------------------------------

    @staticmethod
    def consolidate(actions: list[Action]) -> dict[str, list[Action]]:
        """One consolidated email per person per day for class 3/4.
        Class 1/2 actions (never_suppress) bypass consolidation and are
        returned under a separate '!immediate' key per recipient."""
        buckets: dict[str, list[Action]] = {}
        for action in actions:
            for recipient in action.recipients + action.cc:
                key = f"!immediate:{recipient}" if action.never_suppress else recipient
                buckets.setdefault(key, []).append(action)
        return buckets


def _dedup(emails: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for e in emails:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out
