"""Manual entry for documents no machine could read — §2.2, §5.5.

OCR raises the ceiling; it does not remove the floor. A below-floor
reading is a document the engine looked at and could not be trusted on,
and §5.5 is explicit that nothing is guessed from those. Sealed
documents outside D-05's contract scope are closed by decision. Both
leave real guarantee expiries and claim windows outside the register.

Without a path back in, `UNREADABLE` is a dead end. With one it is a
work queue — which is the difference between a register that is honest
about its holes and a register that has holes nobody is filling.

The shape follows the domain worksheet, because that shape worked: a
CSV carrying the evidence needed to do the job, blank columns for the
answer, and an apply step that refuses to interpret. What is typed here
lands in the class 2 registers marked `source: MANUAL` with who entered
it and when — never mixed in with machine-read values, because a human
reading a photograph and a parser reading a text layer are different
kinds of evidence and the register should say which it holds.
"""

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

# What a person can usefully type from a contract, matching the §2.2
# registers. Free text is not offered: a kind outside this list has
# nowhere to go, and inventing a column for it would produce a row no
# register can hold.
TERM_KINDS = (
    "GUARANTEE_EXPIRY",
    "BOND_EXPIRY",
    "RETENTION_RELEASE",
    "CONTRACT_END",
    "DEFECTS_LIABILITY_END",
    "ACCREDITATION_EXPIRY",
    "NOTICE_PERIOD_DAYS",
    "LD_RATE",
    "LD_CAP",
    "RETENTION_PERCENT",
    "PAYMENT_TERMS",
)

# MILESTONE is deliberately absent. §2.2 lists milestones in the
# contract register, but `registers_contracts` has no column for them,
# and squeezing a milestone date into `end_date` would put a wrong date
# where an alert reads a real one. The missing column is a gap to close
# deliberately, not one to route around (§1.1).

_DATE_KINDS = {
    "GUARANTEE_EXPIRY", "BOND_EXPIRY", "RETENTION_RELEASE", "CONTRACT_END",
    "DEFECTS_LIABILITY_END", "ACCREDITATION_EXPIRY",
}

# These land in numeric columns. LD_RATE, LD_CAP and PAYMENT_TERMS are
# free text in the schema because contracts phrase them in prose.
_NUMERIC_KINDS = {"NOTICE_PERIOD_DAYS", "RETENTION_PERCENT"}

# Worksheet kind -> the instrument_type the schema will accept.
_INSTRUMENT_TYPE = {
    "GUARANTEE_EXPIRY": "LETTER_OF_GUARANTEE",
    "BOND_EXPIRY": "PERFORMANCE_BOND",
    "RETENTION_RELEASE": "RETENTION",
}

HEADERS = (
    "document", "why_unread", "confidential", "ocr_confidence",
    "TERM_KIND", "DATE_yyyy_mm_dd", "VALUE", "COUNTERPARTY", "NOTES",
)


@dataclass
class Pending:
    document: str
    why: str
    confidential: bool = False
    ocr_confidence: float | None = None


def pending_from_result(result) -> list[Pending]:
    """Every document that produced no usable terms, with the reason.

    The reason is carried through rather than flattened to "unreadable",
    because it tells the person what to expect when they open the file:
    a below-floor scan is legible to a human, a sealed document may need
    permission first, and an engine failure may just need the engine.
    """
    confidences = {r.path: r.confidence for r in getattr(result, "ocr_results", [])}
    pending: list[Pending] = []

    for record in getattr(result, "unreadable", []):
        confidence = None
        for path, value in confidences.items():
            if str(path).endswith(record.path.replace("\\", "/").split("/")[-1]):
                confidence = value
                break
        pending.append(Pending(
            document=record.path,
            why=record.note or "no extractable text",
            confidential=bool(record.confidential),
            ocr_confidence=confidence,
        ))

    for record in getattr(result, "blocked", []):
        pending.append(Pending(
            document=record.path,
            why=record.note or "confidential — not opened (D-01)",
            confidential=True,
        ))
    return pending


def write_worksheet(pending: list[Pending], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for item in pending:
            writer.writerow([
                item.document, item.why,
                "yes" if item.confidential else "",
                (f"{item.ocr_confidence:.1f}"
                 if item.ocr_confidence is not None else ""),
                "", "", "", "", "",
            ])
    return path


def read_worksheet(path: Path) -> tuple[list[dict], list[str]]:
    """Return (rows, problems). A row with no TERM_KIND is not an entry.

    Every rejection names its line. A guessed interpretation of what
    somebody meant to type would put a wrong date in a class 2 register,
    which is the failure this whole worksheet exists to avoid.
    """
    rows: list[dict] = []
    problems: list[str] = []

    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        for number, record in enumerate(csv.DictReader(f), 2):
            kind = (record.get("TERM_KIND") or "").strip().upper()
            document = (record.get("document") or "").strip()
            if not kind:
                continue                      # not filled in — not an error
            if kind not in TERM_KINDS:
                problems.append(
                    f"line {number}: TERM_KIND {kind!r} is not one of "
                    + ", ".join(TERM_KINDS))
                continue

            raw_date = (record.get("DATE_yyyy_mm_dd") or "").strip()
            value = (record.get("VALUE") or "").strip()

            if kind in _DATE_KINDS:
                if not raw_date:
                    problems.append(
                        f"line {number}: {kind} needs a date, and a term "
                        "without one alerts on nothing")
                    continue
                try:
                    parsed = datetime.fromisoformat(raw_date).date()
                except ValueError:
                    problems.append(
                        f"line {number}: {raw_date!r} is not a date in "
                        "YYYY-MM-DD form — not interpreted")
                    continue
            else:
                parsed = None
                if not value:
                    problems.append(
                        f"line {number}: {kind} needs a value in the VALUE "
                        "column")
                    continue
                if kind in _NUMERIC_KINDS and _as_float(value) is None:
                    # Silently storing NULL here would drop a term the
                    # person believed they had entered — the same class
                    # of failure as guessing at it (§1.1).
                    problems.append(
                        f"line {number}: {kind} needs a number, not "
                        f"{value!r} — nothing was stored for it")
                    continue

            rows.append({
                "document": document,
                "kind": kind,
                "date": parsed.isoformat() if parsed else "",
                "value": value,
                "counterparty": (record.get("COUNTERPARTY") or "").strip(),
                "notes": (record.get("NOTES") or "").strip(),
                "line": number,
            })
    return rows, problems


_REGISTER_FOR = {
    "GUARANTEE_EXPIRY": "instruments",
    "BOND_EXPIRY": "instruments",
    "RETENTION_RELEASE": "instruments",
    "ACCREDITATION_EXPIRY": "accreditations",
}


def apply_rows(conn, rows: list[dict], *, entered_by: str,
               on_date: date) -> dict:
    """Write entered terms into the §2.2 registers.

    §5.2 fixes the provenance vocabulary at LIVE | BACKFILL, so a
    hand-entered term is a BACKFILL — historical data read off a
    document rather than received in a message. There is deliberately no
    third value invented for it: extending the charter's vocabulary for
    convenience is how a schema stops meaning what the charter says.

    What marks it as hand-read is `submitted_by` carrying the person's
    address, and the `MAN-` reference prefix. Both are greppable, so if
    one entry later turns out wrong, every row from the same pass can be
    found and corrected together.
    """
    from .. import registers as reg

    counts = {"instruments": 0, "accreditations": 0, "contracts": 0}
    for row in rows:
        provenance = {
            "source": "BACKFILL",          # §5.2 allows LIVE | BACKFILL only
            "submitted_by": entered_by,
            "submitted_at": on_date.isoformat(),
            "period": str(on_date.year),
        }
        register = _REGISTER_FOR.get(row["kind"], "contracts")

        if register == "instruments":
            extra = {}
            if row["kind"] == "RETENTION_RELEASE":
                # For a retention, release and expiry are the same event.
                # Recorded on both columns rather than leaving the NOT
                # NULL expiry to be filled with something invented.
                extra["release_date"] = row["date"]
            reg.add_instrument(
                conn,
                instrument_ref=f"MAN-{row['kind']}-{row['document'][-40:]}",
                instrument_type=_INSTRUMENT_TYPE[row["kind"]],
                beneficiary=row["counterparty"] or "NOT PROVIDED",
                expiry_date=row["date"],
                status="OPEN",
                owner="accounts@ubcsis.com",
                **extra, **provenance)
        elif register == "accreditations":
            reg.add_accreditation(
                conn,
                client=row["counterparty"] or "NOT PROVIDED",
                status="ACTIVE",
                expiry_date=row["date"],
                renewal_owner="donia@ubcsis.com",
                documents_required=f"from {row['document']}",
                **provenance)
        else:
            reg.add_contract(
                conn,
                contract_ref=row["document"][-60:],
                client=row["counterparty"] or "NOT PROVIDED",
                owner="ghareeb@ubcsis.com",
                **_contract_field(row),
                **provenance)
        counts[register] += 1
    return counts


def _contract_field(row: dict) -> dict:
    """Map a term kind onto the contract register's own column."""
    kind, value, when = row["kind"], row["value"], row["date"]
    if kind == "CONTRACT_END":
        return {"end_date": when}
    if kind == "DEFECTS_LIABILITY_END":
        return {"dlp_end_date": when}
    if kind == "NOTICE_PERIOD_DAYS":
        return {"notice_period_days": _as_int(value)}
    if kind == "LD_RATE":
        return {"ld_rate": value}
    if kind == "LD_CAP":
        return {"ld_cap": value}
    if kind == "RETENTION_PERCENT":
        return {"retention_pct": _as_float(value)}
    if kind == "PAYMENT_TERMS":
        return {"payment_terms": value}
    return {}


def _as_int(value: str):
    try:
        return int(float(str(value).strip().rstrip("%")))
    except (TypeError, ValueError):
        return None


def _as_float(value: str):
    try:
        return float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None
