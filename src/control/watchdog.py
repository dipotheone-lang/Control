"""External watchdog — charter §8.5, v4.3 findings V7.

Tracks external threads against per-category SLAs. Three closure paths:
an observed outbound UBCSIS reply, the owner declaring CLOSED (logged
with declarant), or the thread breaching and staying open.

v4.3 rules built in:
- Under §3.1a Option A, Control sees only what is copied to control@ —
  every notice is worded as an observation, "no reply visible to
  Control", never "no reply sent".
- CC-compliance is itself a tracked metric: threads closed by observed
  reply vs. CLOSED declaration vs. breached — standing watchdog metric
  and live evidence for decision O-05.
- Notices go only to the internal owner, and their manager after the
  first breach. Never to the external party.

Thread state lives in the append-only external_threads table: each
transition inserts a new row; the latest row per thread is current.
"""

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .calendar import WorkingCalendar
from .enforce import Action

_STATES = ("OPEN", "CLOSED_OBSERVED_REPLY", "CLOSED_DECLARED", "BREACHED")


@dataclass
class SlaRule:
    category: str
    first: str          # e.g. "2h", "1d", "same-day"
    final: str
    owner: str
    backup: str


def parse_sla_config(external_sla: dict | None) -> dict[str, SlaRule]:
    rules = {}
    for category, entry in (external_sla or {}).items():
        rules[category] = SlaRule(
            category=category,
            first=str(entry["first"]),
            final=str(entry["final"]),
            owner=entry["owner"],
            backup=entry["backup"],
        )
    return rules


def _deadline(received: datetime, rule_text: str, cal: WorkingCalendar) -> datetime:
    """SLA text -> absolute deadline. Hours are clock hours; days are
    working days at the same time of day; same-day is end of the
    received (working) day."""
    text = rule_text.strip().lower()
    if text == "same-day":
        d = cal.next_working_day(received.date())
        return datetime.combine(d, time(23, 59))
    m = re.fullmatch(r"(\d+)h", text)
    if m:
        return received + timedelta(hours=int(m.group(1)))
    m = re.fullmatch(r"(\d+)d", text)
    if m:
        d = cal.add_working_days(received.date() + timedelta(days=1), int(m.group(1)) - 1)
        return datetime.combine(d, received.time())
    raise ValueError(f"unparseable SLA {rule_text!r}")


class Watchdog:
    def __init__(self, conn, rules: dict[str, SlaRule], cal: WorkingCalendar,
                 managers: dict[str, str]):
        self.conn = conn
        self.rules = rules
        self.cal = cal
        self.managers = managers   # owner email -> manager email

    # -- state transitions (append-only) -----------------------------------

    def _insert(self, thread_id: str, category: str, state: str,
                at: datetime, declarant: str | None = None) -> None:
        rule = self.rules[category]
        self.conn.execute(
            "INSERT INTO external_threads (thread_id, category, owner, sla_first,"
            " sla_final, state, declarant, source, submitted_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'LIVE', ?)",
            (thread_id, category, rule.owner, rule.first, rule.final, state,
             declarant, at.isoformat()),
        )
        self.conn.commit()

    def register_inbound(self, thread_id: str, category: str, received_at: datetime) -> None:
        if category not in self.rules:
            category = "unclassified"
        self._insert(thread_id, category, "OPEN", received_at)

    def observe_reply(self, thread_id: str, at: datetime) -> None:
        current = self._current(thread_id)
        if current and current["state"] in ("OPEN", "BREACHED"):
            self._insert(thread_id, current["category"], "CLOSED_OBSERVED_REPLY", at)

    def declare_closed(self, thread_id: str, declarant: str, at: datetime) -> None:
        current = self._current(thread_id)
        if current and current["state"] in ("OPEN", "BREACHED"):
            self._insert(thread_id, current["category"], "CLOSED_DECLARED", at,
                         declarant=declarant)

    def mark_breached(self, thread_id: str, at: datetime) -> None:
        current = self._current(thread_id)
        if current and current["state"] == "OPEN":
            self._insert(thread_id, current["category"], "BREACHED", at)

    # -- queries ------------------------------------------------------------

    def _current(self, thread_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT category, state, submitted_at FROM external_threads"
            " WHERE thread_id = ? ORDER BY id DESC LIMIT 1", (thread_id,)
        ).fetchone()
        if row is None:
            return None
        return {"category": row[0], "state": row[1], "at": row[2]}

    def _opened_at(self, thread_id: str) -> datetime:
        row = self.conn.execute(
            "SELECT submitted_at FROM external_threads WHERE thread_id = ?"
            " AND state = 'OPEN' ORDER BY id ASC LIMIT 1", (thread_id,)
        ).fetchone()
        return datetime.fromisoformat(row[0])

    def open_threads(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT thread_id, MAX(id) FROM external_threads GROUP BY thread_id"
        ).fetchall()
        result = []
        for thread_id, max_id in rows:
            state = self.conn.execute(
                "SELECT state FROM external_threads WHERE id = ?", (max_id,)
            ).fetchone()[0]
            if state in ("OPEN", "BREACHED"):
                result.append(thread_id)
        return result

    # -- breach notices (§8.5, worded per V7) --------------------------------

    def check(self, now: datetime) -> list[Action]:
        """Plan watchdog notices for threads past SLA. Dedupe keys make the
        caller idempotent (§1.10): FIRST fires once, FINAL fires once."""
        actions: list[Action] = []
        for thread_id in self.open_threads():
            current = self._current(thread_id)
            rule = self.rules[current["category"]]
            opened = self._opened_at(thread_id)
            first_due = _deadline(opened, rule.first, self.cal)
            final_due = _deadline(opened, rule.final, self.cal)

            note = (
                f"External thread {thread_id} ({rule.category}): no reply visible "
                f"to Control since {opened:%d-%b-%Y %H:%M}. Under CC discipline "
                "Control sees only what is copied to control@ — if a reply was "
                "sent without CC, reply CLOSED to record it."
            )
            if now > final_due:
                manager = self.managers.get(rule.owner)
                recipients = [rule.owner] + ([manager] if manager else [])
                actions.append(Action(
                    kind="WATCHDOG_NOTICE", item_id=thread_id,
                    recipients=recipients,
                    dedupe_key=f"WD:{thread_id}:FINAL",
                    note=note + f" Final SLA ({rule.final}) exceeded.",
                ))
                self.mark_breached(thread_id, now)
            elif now > first_due:
                actions.append(Action(
                    kind="WATCHDOG_NOTICE", item_id=thread_id,
                    recipients=[rule.owner],
                    dedupe_key=f"WD:{thread_id}:FIRST",
                    note=note + f" First-response SLA ({rule.first}) exceeded.",
                ))
        return actions

    # -- CC-compliance metric (standing, O-05 evidence) ----------------------

    def cc_compliance(self) -> dict:
        counts = {"CLOSED_OBSERVED_REPLY": 0, "CLOSED_DECLARED": 0,
                  "BREACHED": 0, "OPEN": 0}
        rows = self.conn.execute(
            "SELECT thread_id, MAX(id) FROM external_threads GROUP BY thread_id"
        ).fetchall()
        for _, max_id in rows:
            state = self.conn.execute(
                "SELECT state FROM external_threads WHERE id = ?", (max_id,)
            ).fetchone()[0]
            counts[state] = counts.get(state, 0) + 1
        total_closed = counts["CLOSED_OBSERVED_REPLY"] + counts["CLOSED_DECLARED"]
        counts["observed_share"] = (
            round(counts["CLOSED_OBSERVED_REPLY"] / total_closed, 3)
            if total_closed else None
        )
        return counts
