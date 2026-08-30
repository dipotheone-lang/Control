"""Pending golden-set cases from the archive — §13.1, D-03.

The Phase 1 gate reported "golden set built and passing" as BLOCKED with
the reason *no judged cases and no pending cases*, and the owner named
as the CEO. That was wrong in the way that matters: the harness can
issue batches, read them back and run the gate, but **nothing ever put a
case into `pending/`**. The block was never his time. It was a missing
step, and naming him as its owner sent the bill to the wrong person.

This is that step. It matches documents on the drive to the approved
obligations and writes one pending case per document, for the CEO to
judge unanchored (D-03) — Control's verdict never appears.

WHAT THIS CANNOT DO, AND WHY IT SAYS SO

§13.1 tests a submission against its **controlled form and the manual
clause** behind it. Stage D found LIVE 0: not one document series on the
drive is both current and on a controlled form. The six approved
obligations name forms the management system registers and that no
document answers (GHOST); the series that do exist — the finance ledger,
the progress reports, the payroll files — are on no controlled form and
under no manual clause (ORPHAN, DEAD).

So a case built today can exercise C1 timeliness, and cannot exercise
C2 form control or C6 manual conformance, because there is no revision
to compare against and no clause to quote. C3, C4, C5 and C7 read fields
out of the document, which needs a field mapping per obligation, and
none of the approved rows has one.

Every case therefore records which checks it can actually exercise, and
the summary states what the set as a whole would prove. A golden set
that tests C1 alone and reports itself as "the golden set" would be the
§13.1 gate passing on a test the engine cannot fail — which the charter
names as the exact thing the unanchored method exists to prevent.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

# What each check needs before it can run at all.
_CHECK_REQUIREMENTS = {
    "C1": "the submission timestamp",
    "C2": "a form code and a current revision on the obligation",
    "C3": "a field mapping, to know which cells are mandatory",
    "C4": "a field mapping and a total rule",
    "C5": "a field mapping and the prior period's posted values",
    "C6": "a manual rule with a clause and a requirement",
    "C7": "a field mapping",
}


@dataclass
class Buildable:
    obligation_id: str
    name: str
    owner: str
    documents: list = field(default_factory=list)   # (path, modified)
    checks: list = field(default_factory=list)      # checks that can run
    missing: dict = field(default_factory=dict)     # check -> what it needs


def _checks_for(row: dict) -> tuple[list[str], dict]:
    """Which of C1–C7 a case under this obligation could exercise."""
    available, missing = ["C1"], {}

    form = str(row.get("form") or "").strip()
    if form and "rev" in form.lower():
        available.append("C2")
    else:
        missing["C2"] = _CHECK_REQUIREMENTS["C2"] + (
            f" — form {form!r} has no revision" if form
            else " — no form code on this obligation")

    mapping = row.get("mapping") or {}
    for check in ("C3", "C4", "C5", "C7"):
        if mapping:
            available.append(check)
        else:
            missing[check] = _CHECK_REQUIREMENTS[check]

    if row.get("manual_rules"):
        available.append("C6")
    else:
        missing["C6"] = _CHECK_REQUIREMENTS["C6"]
    return available, missing


def _matches(row: dict, path: Path, owner_folders: dict) -> bool:
    """Does this document belong to this obligation?

    Owner and folder, never filename similarity. A golden set assembled
    by fuzzy name matching would put the wrong document under the wrong
    obligation, and the CEO would then be judging a mismatch rather than
    the engine.
    """
    folders = owner_folders.get(str(row.get("owner") or "").lower()) or []
    text = str(path).replace("\\", "/").lower()
    return any(folder.lower() in text for folder in folders)


def build(obligations: list[dict], documents: list[tuple[Path, datetime]],
          owner_folders: dict, per_obligation: int = 12) -> list[Buildable]:
    """Candidate cases per approved obligation.

    Documents are spread across the series rather than taken from one
    end of it. §13.1 asks for "a realistic spread of good and defective
    work — not a curated sample of clean ones", and the most recent
    twelve files of a series are the ones most likely to be clean.
    """
    out: list[Buildable] = []
    for row in obligations:
        if not row.get("approved_by_ceo"):
            continue
        checks, missing = _checks_for(row)
        matched = [(p, m) for p, m in documents
                   if _matches(row, p, owner_folders)]
        matched.sort(key=lambda pair: pair[1])
        if len(matched) > per_obligation:
            step = len(matched) / per_obligation
            matched = [matched[int(i * step)] for i in range(per_obligation)]
        out.append(Buildable(
            obligation_id=str(row.get("id") or ""),
            name=str(row.get("name") or ""),
            owner=str(row.get("owner") or ""),
            documents=matched, checks=checks, missing=missing,
        ))
    return out


def due_for(row: dict, when: datetime) -> str:
    """The deadline for the period this document falls in.

    Not the next one. `parse_due` answers "when is this next due", which
    is the right question for a live cycle and the wrong one for a
    document filed in March 2025 — it would put every historical case
    against a deadline in the future and make C1 unjudgeable. The CEO
    would then be asked to rule on timeliness with no deadline on the
    sheet, which is ten rows of his time spent on nothing.
    """
    expression = str(row.get("due") or "").strip().lower()
    cadence = str(row.get("cadence") or "").strip().lower()

    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday",
                "saturday", "sunday")
    at = 17
    if ":" in expression:
        head = expression.split(":")[0]
        try:
            at = int(head.split()[-1])
        except (ValueError, IndexError):
            at = 17

    day = next((i for i, name in enumerate(weekdays) if name in expression),
               None)
    if day is not None:
        shift = (day - when.weekday()) % 7
        target = when.date() + timedelta(days=shift)
        return f"{target.isoformat()}T{at:02d}:00"

    number = re.search(r"\bday\s*(\d{1,2})\b", expression)
    if number and cadence in ("monthly", "quarterly", "annual", ""):
        try:
            target = when.date().replace(day=int(number.group(1)))
        except ValueError:
            return ""
        return f"{target.isoformat()}T{at:02d}:00"
    return ""


def to_cases(buildable: list[Buildable], obligations: dict) -> list[dict]:
    """Pending case files: spec and document, no expected outcome.

    `expected` is absent by construction, not blank — §13.1 and D-03 put
    the verdict with the CEO alone, and a case carrying an empty verdict
    is one edit away from being a case carrying Control's.
    """
    by_id = {str(r.get("id")): r for r in obligations}
    cases = []
    for item in buildable:
        row = by_id.get(item.obligation_id, {})
        form = str(row.get("form") or "")
        code, _, revision = form.partition(" rev ")
        for index, (path, modified) in enumerate(item.documents, start=1):
            cases.append({
                "case_id": f"{item.obligation_id}-{index:03d}",
                "source": "initial",
                "spec": {
                    "obligation_id": item.obligation_id,
                    "name": item.name,
                    "form_code": code.strip(),
                    "current_revision": revision.strip(),
                    "due": due_for(row, modified),
                    "manual_rules": row.get("manual_rules") or [],
                    "mandatory_fields": row.get("mandatory_fields") or [],
                },
                "doc": {
                    "attachment_name": path.name,
                    "received_at": modified.isoformat(timespec="minutes"),
                    "submitted_by": item.owner,
                    "source_path": str(path),
                    "fields": {},
                },
                # On the case, not in a summary that gets skimmed: the
                # CEO is being asked to judge a document, and which
                # checks the engine could even run against it changes
                # what his verdict means.
                "checks_available": item.checks,
                "checks_unavailable": item.missing,
            })
    return cases


def render(buildable: list[Buildable], cases: list[dict],
           today: date) -> list[str]:
    lines = [f"GOLDEN SET — candidate cases from the archive, {today:%d-%b-%Y}",
             ""]
    total = sum(len(b.documents) for b in buildable)
    for item in buildable:
        lines.append(f"  {item.obligation_id:14} {len(item.documents):>4} "
                     f"document(s)  {item.name[:44]}")
        if not item.documents:
            lines.append("                    no document on the drive is "
                         "filed under this obligation's owner and folder")
    lines += ["", f"  {total} candidate case(s) across "
              f"{len(buildable)} obligation(s)", ""]

    every = sorted({c for item in buildable for c in item.checks})
    never = sorted({c for item in buildable for c in item.missing})
    lines += [
        "WHAT THIS SET WOULD ACTUALLY TEST",
        f"  can run:    {', '.join(every) or 'nothing'}",
        f"  cannot run: {', '.join(never) or 'nothing'}",
        "",
    ]
    for check in never:
        reason = next((b.missing[check] for b in buildable
                       if check in b.missing), "")
        lines.append(f"    {check} — {reason}")

    if never:
        lines += [
            "",
            "  §13.1's gate is zero false RETURNED_FOR_REVISION or "
            "NOT_ACCEPTED",
            "  verdicts, counted per check. A check that cannot run cannot "
            "produce a",
            "  false positive, so a set built only on the checks above would "
            "pass the",
            "  gate without testing the thing the gate is for. That is a "
            "test the",
            "  engine cannot fail, which §13.1 names as the failure the "
            "unanchored",
            "  method exists to prevent — so it is stated here rather than "
            "reported",
            "  as a pass (§1.1).",
            "",
            "  The root cause is not this command. Stage D found LIVE 0: no "
            "document",
            "  series on the drive is both current and on a controlled form. "
            "C2 needs a",
            "  revision to compare against and C6 needs a clause to quote, "
            "and the",
            "  archive has neither. That is a decision for the CEO — register "
            "the",
            "  layouts actually in use as controlled forms, or build the "
            "golden set",
            "  from live submissions once Phase 1 reminders are running.",
        ]
    return lines
