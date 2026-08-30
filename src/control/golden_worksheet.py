"""The golden set's human half — §13.1, decision D-03, findings V2/V3/V12.

`goldenset.py` runs the engine against cases whose expected verdict is
already known. Nothing produced those verdicts. The charter's protocol
is a round trip — Control presents historical submissions, the CEO
judges them without seeing Control's answer, and the answers come back
as the expected outcomes — and the middle of that trip did not exist.

This module is the middle. The shape follows the two worksheets the CEO
has already worked through (O-04 domains, manual contract terms): a CSV
carrying the evidence needed to judge, blank columns for the answer, and
an apply step that refuses to interpret. What is typed here becomes a
permanent test case; a guessed reading of a half-filled row would bake a
wrong expected verdict into the gate that decides whether Control may
send anything at all.

Three things the charter asks for that a plain answer sheet would miss:

**The engine's verdict never appears** (D-03). Anchoring the human to
the machine's answer produces a test the machine cannot fail. The
worksheet carries the document, the form and the clause — never a
proposal.

**A clause-mapping subsample** (V3). Control selecting the governing
clause frames the judgement, so on at least ten items the clause column
is left blank and the CEO names their own. Agreement is reported as its
own error rate rather than assumed away.

**A batch ledger.** §13.1 delivers in batches of ten so the work fits
into short sessions, and warns that Phase 1 cannot complete without the
CEO's time. A batch issued and never returned is a deployment blocker,
and it only becomes one if somebody is counting the days.
"""

import csv
from dataclasses import dataclass
from dataclasses import field as dcfield
from datetime import date, datetime
from pathlib import Path

import yaml

from .goldenset import ACCEPT_VERDICTS, CHECKS, RETURN_VERDICTS

# §7.4's full verdict set. UNREADABLE is offered because a document the
# CEO cannot read either is a real answer, and the engine has a matching
# verdict for it — leaving it off the sheet would push those items into
# a wrong bucket rather than out of the set.
VALID_VERDICTS = tuple(sorted(ACCEPT_VERDICTS | RETURN_VERDICTS)) + ("UNREADABLE",)

# §13.1: "Delivered in batches of 10, so the work fits into short
# sessions and Phase 1 is never blocked waiting on a single long sitting."
BATCH_SIZE = 10

# §13.1: the clause-mapping check runs on "a subsample of at least 10
# items". Fewer than that and the error rate it produces would be noise
# reported as a measurement.
CLAUSE_SUBSAMPLE_MIN = 10

# §13.1: "If a batch stalls beyond two weeks, Control raises it as a
# deployment blocker rather than quietly waiting."
STALL_DAYS = 14

HEADERS = (
    "case_id", "document", "received", "obligation", "due",
    "governing_form", "governing_clause",
    "VERDICT", "FAILED_CHECKS", "CLAUSE_YOU_USED", "NOTES",
)

# What the blank clause cell says on a clause-mapping row, so the reason
# for the blank is on the sheet rather than in a covering email.
CLAUSE_WITHHELD = "(withheld — name the clause you used)"


@dataclass
class Batch:
    number: int
    case_ids: list[str]
    issued: date
    returned: date | None = None
    path: str = ""
    # Which of this batch's items were judged without a pre-selected
    # clause (V3). Recorded per batch so the subsample accumulates
    # across batches instead of restarting at ten every week.
    clause_withheld: list[str] = dcfield(default_factory=list)

    @property
    def outstanding(self) -> bool:
        return self.returned is None

    def days_out(self, as_of: date) -> int:
        return (as_of - self.issued).days


# ---- pending cases ----------------------------------------------------

def load_pending(directory: Path) -> list[dict]:
    """Cases awaiting a verdict: spec and document, no expected outcome.

    Kept in their own directory rather than as judged cases with an
    empty verdict, so nothing can run the harness against a case whose
    expected answer is a blank waiting to be filled.
    """
    out = []
    for path in sorted(Path(directory).glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw["_path"] = path
        out.append(raw)
    return out


def _form_of(spec: dict) -> str:
    """What the CEO reads in the governing-form column.

    An obligation with no controlled form rendered as " rev " — which
    looks like a rendering fault rather than the fact it is. Stage D
    found LIVE 0: no series on this drive is on a controlled form, so
    this column is empty for most of the set and has to say so.
    """
    code = str(spec.get("form_code") or "").strip()
    revision = str(spec.get("current_revision") or "").strip()
    if not code:
        return "NONE — this obligation has no controlled form"
    return f"{code} rev {revision}" if revision else f"{code} — revision NOT RECORDED"


def _clause_of(raw: dict) -> str:
    rules = (raw.get("spec") or {}).get("manual_rules") or []
    clauses = [str(r.get("clause")) for r in rules if r.get("clause")]
    return "; ".join(clauses)


def _received(raw: dict) -> str:
    stamp = (raw.get("doc") or {}).get("received_at")
    try:
        return f"{datetime.fromisoformat(str(stamp)):%d-%b-%Y %H:%M}"
    except (TypeError, ValueError):
        return "NOT PROVIDED"


def _due(raw: dict) -> str:
    stamp = (raw.get("spec") or {}).get("due")
    try:
        return f"{datetime.fromisoformat(str(stamp)):%d-%b-%Y %H:%M}"
    except (TypeError, ValueError):
        return "NOT PROVIDED"


# ---- writing the worksheet -------------------------------------------

def write_batch(pending: list[dict], path: Path, *, clause_blank: set[str]
                ) -> tuple[Path, list[str]]:
    """One batch as a CSV. Returns the path and the case ids written.

    Only the evidence goes on the sheet: what was received, when, under
    which obligation, against which form. No proposed verdict, no hint
    of one (D-03).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for raw in pending:
            case_id = str(raw.get("case_id") or "")
            spec, doc = raw.get("spec") or {}, raw.get("doc") or {}
            clause = (CLAUSE_WITHHELD if case_id in clause_blank
                      else _clause_of(raw) or "NOT PROVIDED")
            writer.writerow([
                case_id,
                doc.get("attachment_name") or "(no attachment)",
                _received(raw),
                f"{spec.get('name', '')} ({spec.get('obligation_id', '')})",
                _due(raw),
                _form_of(spec),
                clause,
                "", "", "", "",
            ])
            written.append(case_id)
    return path, written


def choose_clause_subsample(pending: list[dict], *, already: set[str],
                            target: int = CLAUSE_SUBSAMPLE_MIN) -> set[str]:
    """Which cases get their clause withheld (V3).

    Only cases that actually have a clause to compare against are
    eligible — withholding a clause that was never recorded measures
    nothing. Selection is by position, not at random, so re-running the
    command produces the same sheet rather than a different one.
    """
    eligible = [str(r.get("case_id")) for r in pending if _clause_of(r)]
    need = max(0, target - len(already))
    return set(eligible[:need])


# ---- reading it back --------------------------------------------------

def read_batch(path: Path) -> tuple[list[dict], list[str]]:
    """Return (answers, problems). Every rejection names its line.

    A row with no VERDICT is not an error — it is an item the CEO has
    not reached yet, and a half-finished sheet should be applicable for
    the part that is finished.
    """
    answers: list[dict] = []
    problems: list[str] = []

    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        for number, record in enumerate(csv.DictReader(f), 2):
            case_id = (record.get("case_id") or "").strip()
            verdict = (record.get("VERDICT") or "").strip().upper()
            if not verdict:
                continue
            if not case_id:
                problems.append(
                    f"line {number}: a verdict with no case_id — nothing to "
                    "attach it to")
                continue
            if verdict not in VALID_VERDICTS:
                problems.append(
                    f"line {number} ({case_id}): verdict {verdict!r} is not one "
                    "of " + ", ".join(VALID_VERDICTS))
                continue

            checks, bad = _parse_checks(record.get("FAILED_CHECKS") or "")
            if bad:
                problems.append(
                    f"line {number} ({case_id}): {', '.join(bad)} not among "
                    + ", ".join(CHECKS))
                continue
            if verdict in RETURN_VERDICTS and not checks:
                # §7.4 maps verdicts onto checks. A return with no check
                # named cannot become a test case: there would be nothing
                # for the engine to agree or disagree with.
                problems.append(
                    f"line {number} ({case_id}): {verdict} needs at least one "
                    "of C1–C7 in FAILED_CHECKS")
                continue
            if verdict in ACCEPT_VERDICTS and checks:
                problems.append(
                    f"line {number} ({case_id}): {verdict} with failed checks "
                    f"{', '.join(checks)} — one of the two is a slip")
                continue

            answers.append({
                "case_id": case_id,
                "verdict": verdict,
                "failed_checks": checks,
                "clause_used": (record.get("CLAUSE_YOU_USED") or "").strip(),
                "notes": (record.get("NOTES") or "").strip(),
                "line": number,
            })
    return answers, problems


def _parse_checks(raw: str) -> tuple[list[str], list[str]]:
    tokens = [t.strip().upper() for t in raw.replace(";", ",").split(",")
              if t.strip()]
    good = [t for t in tokens if t in CHECKS]
    bad = [t for t in tokens if t not in CHECKS]
    return good, bad


# ---- applying ---------------------------------------------------------

def apply_batch(answers: list[dict], pending_dir: Path, golden_dir: Path
                ) -> tuple[list[str], list[str], list[dict]]:
    """Move judged cases from pending into the set.

    Returns (applied ids, problems, clause comparisons). Cases are never
    overwritten: an answer for a case already in the set is refused, not
    silently replaced, because the set is the record of what the CEO
    ruled and a rerun should not be able to rewrite that.
    """
    pending_dir, golden_dir = Path(pending_dir), Path(golden_dir)
    golden_dir.mkdir(parents=True, exist_ok=True)

    applied: list[str] = []
    problems: list[str] = []
    clause_results: list[dict] = []

    for answer in answers:
        case_id = answer["case_id"]
        source = pending_dir / f"{case_id}.yaml"
        target = golden_dir / f"{case_id}.yaml"

        if target.exists():
            problems.append(
                f"line {answer['line']}: {case_id} is already in the set — "
                "cases are never overwritten (§13.1)")
            continue
        if not source.is_file():
            problems.append(
                f"line {answer['line']}: no pending case {case_id} — the "
                "worksheet does not match this golden set")
            continue

        raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        raw["expected"] = {"verdict": answer["verdict"],
                           "failed_checks": answer["failed_checks"]}
        raw["ceo_notes"] = answer["notes"]
        raw.setdefault("source", "initial")

        if answer["clause_used"]:
            control_clause = _clause_of(raw)
            clause_results.append({
                "case_id": case_id,
                "ceo": answer["clause_used"],
                "control": control_clause,
                "agrees": clause_matches(answer["clause_used"], control_clause),
            })
            raw["clause_mapping"] = {"ceo": answer["clause_used"],
                                     "control": control_clause}

        target.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        source.unlink()
        applied.append(case_id)

    return applied, problems, clause_results


def clause_matches(ceo: str, control: str) -> bool:
    """Same clause, allowing for how people write clause numbers.

    "clause 7.2", "7.2" and "§7.2" are the same answer. Anything looser
    than that is left to disagree: an over-generous match would report
    an agreement rate the test never earned.
    """
    def norm(value: str) -> set[str]:
        cleaned = (value.lower().replace("§", " ").replace("clause", " ")
                   .replace("،", ",").replace(";", ","))
        return {p.strip(" .") for p in cleaned.replace(",", " ").split()
                if p.strip(" .")}

    ceo_parts, control_parts = norm(ceo), norm(control)
    return bool(ceo_parts & control_parts)


def clause_mapping_report(results: list[dict]) -> list[str]:
    """The clause-mapping error rate, as its own number (V3)."""
    if not results:
        return ["clause mapping: no items judged without a pre-selected clause "
                f"— §13.1 asks for at least {CLAUSE_SUBSAMPLE_MIN}"]
    agreed = sum(1 for r in results if r["agrees"])
    lines = [
        f"clause mapping: {agreed}/{len(results)} agreed "
        f"({agreed / len(results):.0%})"
    ]
    if len(results) < CLAUSE_SUBSAMPLE_MIN:
        lines.append(
            f"  below the §13.1 subsample of {CLAUSE_SUBSAMPLE_MIN} — this "
            "rate is not yet a measurement")
    for result in results:
        if not result["agrees"]:
            lines.append(
                f"  {result['case_id']}: CEO chose {result['ceo']!r}, "
                f"Control had {result['control'] or 'none recorded'!r}")
    return lines


# ---- the batch ledger -------------------------------------------------

def load_ledger(path: Path) -> list[Batch]:
    path = Path(path)
    if not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    batches = []
    for item in raw.get("batches") or []:
        batches.append(Batch(
            number=int(item["number"]),
            case_ids=list(item.get("case_ids") or []),
            issued=_as_date(item.get("issued")),
            returned=_as_date(item.get("returned")) if item.get("returned") else None,
            path=str(item.get("path") or ""),
            clause_withheld=list(item.get("clause_withheld") or []),
        ))
    return batches


def save_ledger(batches: list[Batch], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"batches": [
        {"number": b.number, "issued": b.issued, "returned": b.returned,
         "path": b.path, "case_ids": b.case_ids,
         "clause_withheld": b.clause_withheld}
        for b in batches]}, allow_unicode=True, sort_keys=False),
        encoding="utf-8")


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def stalled_batches(batches: list[Batch], as_of: date) -> list[Batch]:
    """§13.1's single-point dependency, made visible.

    Phase 1 cannot complete without the CEO's time, and the charter asks
    for that to be raised rather than waited out. Counting the days is
    the whole mechanism.
    """
    return [b for b in batches
            if b.outstanding and b.days_out(as_of) > STALL_DAYS]


def ledger_lines(batches: list[Batch], as_of: date) -> list[str]:
    """Report lines for the weekly pack. Silent when nothing is out."""
    outstanding = [b for b in batches if b.outstanding]
    if not outstanding:
        return []
    lines = []
    for batch in sorted(outstanding, key=lambda b: b.issued):
        days = batch.days_out(as_of)
        blocker = " — DEPLOYMENT BLOCKER (§13.1)" if days > STALL_DAYS else ""
        lines.append(
            f"Golden-set batch {batch.number} ({len(batch.case_ids)} items) "
            f"issued {batch.issued:%d-%b-%Y}, {days} days outstanding{blocker}"
        )
    if any(b.days_out(as_of) > STALL_DAYS for b in outstanding):
        lines.append(
            "   Phase 1 cannot complete without these verdicts, and D-03 "
            "keeps them with the CEO — they cannot be delegated.")
    return lines
