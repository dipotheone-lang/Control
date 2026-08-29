"""Class 2 registers — charter §2.2.

The charter is blunt about these: tender submission and clarification
deadlines are "the highest-value items in the system", a claim not
noticed within its window is generally forfeited, and a lapsed
prequalification produces silent revenue decline — you stop being
invited rather than being rejected.

This module holds the five registers and, more importantly, turns their
dates into TrackedItems the §8.1 deadline engine already knows how to
alert on. A register nobody alerts from is a spreadsheet.

Alert schedules come from §2.2 and are not negotiable per item:
- tender submission / clarification: T-14, 7, 3, 2, 1 and morning-of
- financial instruments: 60 / 30 / 14 / 7 days, and release dates
- accreditations: 90 / 60 / 30 days
- quotation validity: before expiry on open opportunities
- contract notice periods: derived per contract, never assumed
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .enforce import (
    ACCREDITATION_SCHEDULE,
    CLASS2_SCHEDULE,
    INSTRUMENT_SCHEDULE,
    TENDER_SCHEDULE,
    TrackedItem,
)


def _as_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _row_to_dict(cursor, row) -> dict:
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


# ---------------------------------------------------------------------------
# Insertion
# ---------------------------------------------------------------------------

def _insert(conn, table: str, values: dict) -> int:
    values = {k: v for k, v in values.items() if v is not None}
    values.setdefault("source", "LIVE")
    columns = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    cursor = conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({marks})", list(values.values()))
    conn.commit()
    return cursor.lastrowid


def add_instrument(conn, **fields) -> int:
    """Guarantees, bonds, insurance, retention (§2.2)."""
    return _insert(conn, "registers_instruments", fields)


def add_accreditation(conn, **fields) -> int:
    return _insert(conn, "registers_accreditations", fields)


def add_quotation(conn, **fields) -> int:
    return _insert(conn, "registers_quotations", fields)


def add_tender(conn, **fields) -> int:
    return _insert(conn, "registers_tenders", fields)


def add_contract(conn, **fields) -> int:
    return _insert(conn, "registers_contracts", fields)


# ---------------------------------------------------------------------------
# Current state (append-only: latest row per reference wins)
# ---------------------------------------------------------------------------

_LATEST = """
SELECT t.* FROM {table} t
JOIN (SELECT {key} AS k, MAX(id) AS mid FROM {table} GROUP BY {key}) m
  ON t.id = m.mid
"""


def current(conn, table: str, key: str) -> list[dict]:
    cursor = conn.execute(_LATEST.format(table=table, key=key))
    return [_row_to_dict(cursor, row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Deadlines -> TrackedItems for the §8.1 engine
# ---------------------------------------------------------------------------

@dataclass
class RegisterDeadline:
    item: TrackedItem
    register: str
    detail: str


def _item(item_id: str, name: str, owner: str, due: date, schedule) -> TrackedItem:
    """A class 2 deadline. The owner is whatever the register holds.

    It used to fall back to a hardcoded address when the column was
    empty, which put a named individual against every unowned guarantee
    and tender in the CEO's report — a fabricated fact in the one place
    §11 says every number must trace to a row (§1.1). §3.2 made it
    pointed: that address is the segregation-of-duties concentration, so
    the invented assignments landed on the person whose load the charter
    is trying to measure.

    An empty owner now stays empty and surfaces through `unowned` as
    what it is — a deadline nobody is chasing.
    """
    return TrackedItem(
        item_id=item_id, obligation_class=2, name=name,
        owner=owner or "", due=due, schedule=schedule,
    )


def tender_deadlines(conn) -> list[RegisterDeadline]:
    out: list[RegisterDeadline] = []
    for row in current(conn, "registers_tenders", "tender_ref"):
        if row.get("status") in ("CLOSED", "NO_BID"):
            continue
        ref, owner = row["tender_ref"], (row.get("owner") or "")
        client = row.get("client") or ""
        for field, label, schedule in (
            ("bid_decision_due", "bid/no-bid decision", CLASS2_SCHEDULE),
            ("clarification_deadline", "clarification deadline", TENDER_SCHEDULE),
            ("bid_bond_due", "bid bond arranged", CLASS2_SCHEDULE),
            ("submission_deadline", "SUBMISSION DEADLINE", TENDER_SCHEDULE),
            ("postmortem_due", "post-mortem due", CLASS2_SCHEDULE),
        ):
            due = _as_date(row.get(field))
            if not due:
                continue
            out.append(RegisterDeadline(
                item=_item(f"TND-{ref}-{field}",
                           f"{label} — {row.get('title') or ref} "
                           f"({client})", owner, due, schedule),
                register="tenders",
                detail=f"{ref}: {label}",
            ))
    return out


def instrument_deadlines(conn) -> list[RegisterDeadline]:
    out: list[RegisterDeadline] = []
    for row in current(conn, "registers_instruments", "instrument_ref"):
        if row.get("status") in ("RELEASED", "CANCELLED", "EXPIRED"):
            continue
        ref = row["instrument_ref"]
        expiry = _as_date(row.get("expiry_date"))
        if expiry:
            out.append(RegisterDeadline(
                item=_item(f"INS-{ref}-expiry",
                           f"{row['instrument_type']} expiry — {ref}"
                           + (f" ({row['beneficiary']})"
                              if row.get("beneficiary") else ""),
                           (row.get("owner") or ""), expiry, INSTRUMENT_SCHEDULE),
                register="instruments",
                detail=f"{ref}: expiry",
            ))
        release = _as_date(row.get("release_date"))
        if release:
            # Uncollected money: §2.2 names retention release explicitly.
            out.append(RegisterDeadline(
                item=_item(f"INS-{ref}-release",
                           f"{row['instrument_type']} release due — {ref}",
                           (row.get("owner") or ""), release, INSTRUMENT_SCHEDULE),
                register="instruments",
                detail=f"{ref}: release",
            ))
    return out


def accreditation_deadlines(conn) -> list[RegisterDeadline]:
    out: list[RegisterDeadline] = []
    for row in current(conn, "registers_accreditations", "client"):
        if row.get("status") == "WITHDRAWN":
            continue
        expiry = _as_date(row.get("expiry_date"))
        if not expiry:
            continue
        out.append(RegisterDeadline(
            item=_item(f"ACC-{row['client']}",
                       f"Accreditation expiry — {row['client']}",
                       (row.get("renewal_owner") or ""), expiry,
                       ACCREDITATION_SCHEDULE),
            register="accreditations",
            detail=f"{row['client']}: prequalification expiry",
        ))
    return out


def quotation_deadlines(conn) -> list[RegisterDeadline]:
    out: list[RegisterDeadline] = []
    for row in current(conn, "registers_quotations", "quote_ref"):
        if row.get("status") != "OPEN":
            continue
        valid_until = _as_date(row.get("valid_until"))
        if not valid_until:
            continue
        direction = row.get("direction") or "ISSUED"
        counterparty = row.get("counterparty") or ""
        out.append(RegisterDeadline(
            item=_item(f"QTE-{row['quote_ref']}",
                       f"Quotation validity expiry ({direction.lower()}) — "
                       f"{row['quote_ref']} {counterparty}".strip(),
                       (row.get("owner") or ""), valid_until, CLASS2_SCHEDULE),
            register="quotations",
            detail=f"{row['quote_ref']}: validity expiry",
        ))
    return out


def contract_deadlines(conn) -> list[RegisterDeadline]:
    """Contract dates that are themselves deadlines.

    Notice periods are deliberately NOT synthesised into dates here: a
    claim window runs from an event, and the event is not in the
    register. Inventing a date would be a filled gap (§1.1). They are
    reported as standing terms instead.
    """
    out: list[RegisterDeadline] = []
    for row in current(conn, "registers_contracts", "contract_ref"):
        ref, owner = row["contract_ref"], (row.get("owner") or "")
        client = row.get("client") or ""
        for field, label in (("end_date", "contract end"),
                             ("dlp_end_date", "defects liability period end")):
            due = _as_date(row.get(field))
            if not due:
                continue
            out.append(RegisterDeadline(
                item=_item(f"CTR-{ref}-{field}",
                           f"{label} — {ref} ({client})",
                           owner, due, CLASS2_SCHEDULE),
                register="contracts",
                detail=f"{ref}: {label}",
            ))
    return out


def all_deadlines(conn) -> list[RegisterDeadline]:
    return (tender_deadlines(conn) + instrument_deadlines(conn)
            + accreditation_deadlines(conn) + quotation_deadlines(conn)
            + contract_deadlines(conn))


def horizon(conn, today: date, days: int = 30) -> list[RegisterDeadline]:
    """Everything due within the window, plus anything already overdue —
    an expired guarantee does not stop mattering because its date passed."""
    limit = today + timedelta(days=days)
    upcoming = [d for d in all_deadlines(conn) if d.item.due <= limit]
    return sorted(upcoming, key=lambda d: d.item.due)


# Register, key column, and the date whose absence makes a row silent.
_UNDATED = (
    ("registers_accreditations", "client", "expiry_date", "accreditation"),
    # registers_instruments is deliberately absent: expiry_date is NOT
    # NULL there, so a guarantee cannot be registered without one. The
    # schema already forbids the silent case. The residual risk is a
    # guarantee never entered at all, which Stage C surfaces from the
    # documents rather than from the register.
    ("registers_tenders", "tender_ref", "submission_deadline", "tender"),
    ("registers_quotations", "quote_ref", "valid_until", "quotation"),
)


def undated(conn) -> list[dict]:
    """Register rows that exist but carry no date, so alert on nothing.

    These are the most dangerous rows in the system, and the least
    visible. A register holding twelve accreditations with unknown
    expiry produces exactly the same empty horizon as a register holding
    nothing — which would let "we have not found the dates yet" read as
    "there is nothing due". §1.1: the gap is the finding.
    """
    rows: list[dict] = []
    for table, key, date_column, kind in _UNDATED:
        for row in current(conn, table, key):
            if not row.get(date_column):
                rows.append({
                    "kind": kind,
                    "ref": row.get(key, ""),
                    "missing": date_column,
                    "status": (row.get("status") or ""),
                    "owner": row.get("renewal_owner") or row.get("owner") or "",
                })
    return rows


# Register, key column, owner column, and what the row is.
_UNOWNED = (
    ("registers_instruments", "instrument_ref", "owner", "instrument"),
    ("registers_accreditations", "client", "renewal_owner", "accreditation"),
    ("registers_tenders", "tender_ref", "owner", "tender"),
    ("registers_quotations", "quote_ref", "owner", "quotation"),
    ("registers_contracts", "contract_ref", "owner", "contract"),
)


def unowned(conn) -> list[dict]:
    """Register rows with a date and nobody against it.

    The companion to `undated`, and it exists because the alternative
    was worse than silence: an empty owner used to be filled with a
    hardcoded address, so a guarantee nobody was chasing appeared in the
    CEO's report assigned to a named person. A deadline with no owner
    alerts into nothing; that is a finding, and §1.1 says it has to look
    like one.
    """
    rows: list[dict] = []
    for table, key, owner_column, kind in _UNOWNED:
        for row in current(conn, table, key):
            if not row.get(owner_column):
                rows.append({"kind": kind, "ref": row.get(key) or "",
                             "missing": owner_column})
    return rows


def notice_periods(conn) -> list[dict]:
    """Standing claim/variation windows — §2.2: in Egyptian contracting
    practice a claim not noticed within its window is generally
    forfeited."""
    rows = []
    for row in current(conn, "registers_contracts", "contract_ref"):
        if row.get("notice_period_days"):
            rows.append({
                "contract_ref": row["contract_ref"],
                "client": (row.get("client") or ""),
                "notice_period_days": row["notice_period_days"],
                "owner": (row.get("owner") or ""),
            })
    return rows
