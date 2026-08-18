"""Dispute adjudication — §8.4, §3.3, §8.6, and the §13.1 feedback loop.

A dispute was detectable, loggable, and clock-suspending, and had no way
to end. `DISPUTE` on the first line suspended the escalation clock on
that item and listed it for CEO adjudication — but nothing could record
an adjudication, so the clock stayed suspended and the weekly report
counted the same pending dispute forever.

That is the stall lever finding V4 named: the appeal path is also the
route to stopping enforcement indefinitely, and it only closes if
somebody can actually rule.

Three rules shape what this does:

**Append-only** (§5.2). An adjudication inserts a new dispute row
carrying `correction_of` and the ruling, and never touches the row it
resolves. The report already reads the latest row per disputed item, so
the history stays complete and the current state stays unambiguous.

**Authority comes from the register, not the claim** (§3.3, D-12). The
CEO adjudicates. The COO deputises only while the CEO's absence is
registered — read from the absence table, never from a flag the deputy
could set — and every deputised ruling is logged as such.

**An upheld dispute is training signal** (§13.1). Every one becomes a
permanent golden case with the CEO's ruling as the expected answer, so
the same error cannot recur silently. Control cannot build that case
from the database alone — the original document is not in it — so what
is recorded here is the requirement and its evidence, listed for the
machine holding the archive. A case fabricated from partial data would
certify the engine against a document nobody looked at (§1.1).
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

OUTCOMES = ("UPHELD", "REJECTED")

# §8.4: "Disputes unresolved after 5 working days appear as a standing
# line in the weekly report ... until adjudicated."
VISIBILITY_DAYS = 5


class AuthorityError(Exception):
    """Adjudication attempted by someone the register does not permit."""


@dataclass
class Pending:
    dispute_id: int
    raised_by: str
    raised_at: date
    submission_id: int | None
    obligation_id: str | None
    verdict: str | None
    days_open: int = 0

    @property
    def linked(self) -> bool:
        """Whether the dispute is tied to the submission it contests.

        A dispute arrives as a reply, and matching it back to a
        submission is not always possible. An unlinked dispute still
        suspends nothing and still needs a ruling — it is reported as
        unlinked rather than quietly treated as if it named its target.
        """
        return self.submission_id is not None


def pending(conn, as_of: date | None = None) -> list[Pending]:
    """Every dispute awaiting a ruling, with the evidence to make one."""
    as_of = as_of or date.today()
    rows = conn.execute(
        "SELECT d.id, d.raised_by, d.raised_at, d.submission_id,"
        "       s.obligation_id, s.verdict"
        "  FROM disputes d"
        "  JOIN (SELECT COALESCE(submission_id, id) k, MAX(id) mid"
        "          FROM disputes GROUP BY k) m ON d.id = m.mid"
        "  LEFT JOIN submissions s ON s.id = d.submission_id"
        " WHERE d.state = 'PENDING'"
        " ORDER BY d.raised_at"
    ).fetchall()

    out = []
    for row in rows:
        raised = _as_date(row[2])
        out.append(Pending(
            dispute_id=row[0], raised_by=row[1], raised_at=raised,
            submission_id=row[3], obligation_id=row[4], verdict=row[5],
            days_open=(as_of - raised).days,
        ))
    return out


def assert_may_adjudicate(conn, who: str, *, ceo: str, coo: str | None,
                          on: date) -> bool:
    """Return True when the ruling is deputised. Raise when it is barred.

    §8.4 puts adjudication with the CEO. §3.3 opens a deputy path during
    registered CEO absence — and opens it from the absence register, so
    an unregistered absence keeps disputes pending rather than letting
    the deputy declare their own authority.
    """
    who = (who or "").lower()
    if who == (ceo or "").lower():
        return False
    if coo and who == coo.lower():
        absent = conn.execute(
            "SELECT 1 FROM absence WHERE email = ? AND from_date <= ?"
            " AND to_date >= ? LIMIT 1",
            (ceo.lower(), on.isoformat(), on.isoformat()),
        ).fetchone()
        if absent:
            return True
        raise AuthorityError(
            f"{who} is the COO, but the CEO's absence is not registered for "
            f"{on:%d-%b-%Y}. §3.3 opens the deputy path from the absence "
            "register, never from the deputy."
        )
    raise AuthorityError(
        f"{who} may not adjudicate disputes. §8.4 puts adjudication with the "
        "CEO, and §3.3 allows only the COO to deputise during registered "
        "absence."
    )


def adjudicate(conn, dispute_id: int, *, outcome: str, by: str, reason: str,
               ceo: str, coo: str | None = None,
               on: date | None = None) -> dict:
    """Record a ruling as a new row. The disputed row is never altered."""
    on = on or date.today()
    outcome = (outcome or "").upper()
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}")
    if not (reason or "").strip():
        # §8.6 turns repeated dispute outcomes into systemic findings,
        # and a ruling with no reason carries nothing to find.
        raise ValueError(
            "a ruling needs a reason — it is the evidence §8.6 reads for "
            "systemic findings, and §13.1 keeps as the expected answer")

    row = conn.execute(
        "SELECT id, submission_id, raised_by, raised_at, state FROM disputes"
        " WHERE id = ?", (dispute_id,)).fetchone()
    if row is None:
        raise ValueError(f"no dispute {dispute_id}")
    if row[4] != "PENDING":
        raise ValueError(
            f"dispute {dispute_id} is already {row[4]} — rulings are appended, "
            "not revised. Raise a new dispute to contest the ruling.")

    # Append-only means the disputed row KEEPS saying PENDING after it is
    # ruled — the ruling is a separate row. So a second ruling has to be
    # caught by looking for one that already points here, or two
    # conflicting rulings could stand against the same dispute with
    # nothing saying which governs.
    ruled = conn.execute(
        "SELECT id, state FROM disputes WHERE correction_of = ? LIMIT 1",
        (dispute_id,)).fetchone()
    if ruled is not None:
        raise ValueError(
            f"dispute {dispute_id} is already ruled {ruled[1]} in row "
            f"{ruled[0]} — rulings are appended, not revised. Raise a new "
            "dispute to contest the ruling.")

    deputised = assert_may_adjudicate(conn, by, ceo=ceo, coo=coo, on=on)

    note = reason.strip()
    if deputised:
        note = f"[deputised for {ceo}] {note}"

    cursor = conn.execute(
        "INSERT INTO disputes (submission_id, raised_by, raised_at, state,"
        " adjudicated_by, adjudicated_at, source, correction_of,"
        " correction_reason)"
        " VALUES (?, ?, ?, ?, ?, ?, 'LIVE', ?, ?)",
        (row[1], row[2], row[3], outcome, by.lower(), on.isoformat(),
         dispute_id, note),
    )
    conn.commit()
    return {
        "dispute_id": dispute_id,
        "ruling_id": cursor.lastrowid,
        "outcome": outcome,
        "deputised": deputised,
        "submission_id": row[1],
    }


# ---- §13.1: an upheld dispute is a permanent test case ----------------

def record_golden_requirement(control_root: Path, ruling: dict, *,
                              reason: str, obligation_id: str | None,
                              verdict: str | None, on: date) -> Path:
    """Queue an upheld dispute as a golden case that must be built.

    §13.1 requires the case; it cannot be written from the database,
    which holds the verdict but not the document that produced it. So
    the requirement is recorded with its evidence and left visible,
    rather than filled with a plausible reconstruction — a fabricated
    case would certify the engine against a document nobody read (§1.1).
    """
    path = Path(control_root) / "tests" / "golden-set" / "FROM-DISPUTES.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        path.write_text(
            "# Golden cases owed to upheld disputes — §13.1\n\n"
            "Every dispute upheld becomes a permanent test case, with the\n"
            "CEO's ruling as the expected answer, so the same error cannot\n"
            "recur silently.\n\n"
            "Control cannot write these from the database: it holds the\n"
            "verdict but not the document. Each entry below needs the\n"
            "original submission, on the machine holding the archive, built\n"
            "into `tests/golden-set/pending/` and judged through\n"
            "`python -m control golden`.\n\n"
            "Nothing here is closed by deleting a line. It is closed by the\n"
            "case existing.\n",
            encoding="utf-8")

    with path.open("a", encoding="utf-8") as f:
        f.write(
            f"\n---\n\n## Dispute {ruling['dispute_id']} — upheld "
            f"{on:%d-%b-%Y}\n\n"
            f"- Submission: {ruling['submission_id'] or 'NOT LINKED'}\n"
            f"- Obligation: {obligation_id or 'NOT PROVIDED'}\n"
            f"- Verdict contested: {verdict or 'NOT PROVIDED'}\n"
            f"- Expected answer (the ruling): {reason.strip()}\n"
            f"- Ruling recorded as dispute row {ruling['ruling_id']}\n"
        )
    return path


# ---- §8.6: repeated outcomes are systemic, not individual -------------

def rejection_pattern(conn, *, minimum: int = 3) -> list[str]:
    """People whose disputes are repeatedly rejected (§8.4, §8.6).

    §8.4 is explicit that this is handled as a systemic finding and
    "never re-argued item by item". The line names the pattern and the
    count, and stops there: a conclusion about why somebody disputes
    repeatedly is a conclusion about a person, which §1.4 leaves to
    humans.
    """
    rows = conn.execute(
        "SELECT raised_by,"
        "       SUM(state = 'REJECTED') rejected,"
        "       SUM(state IN ('REJECTED','UPHELD')) ruled"
        "  FROM disputes WHERE adjudicated_by IS NOT NULL"
        " GROUP BY raised_by"
    ).fetchall()

    lines = []
    for raised_by, rejected, ruled in rows:
        if rejected >= minimum:
            lines.append(
                f"{raised_by}: {rejected} of {ruled} disputes rejected on "
                f"adjudication (§8.6 systemic finding — handled as a pattern, "
                "not re-argued item by item)")
    return lines


def _as_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value)
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return datetime.fromisoformat(text.split(" ")[0]).date()
