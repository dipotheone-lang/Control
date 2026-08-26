"""Stage D proposals to an approved obligation register — §6.

*"Phase 0 ends when the CEO approves the obligation register."*

That sentence had no mechanism behind it. Stage D inferred candidate
obligations from the archive and wrote them to a markdown report; the
engine read `config/obligations.yaml`, which was empty; and nothing
joined the two. So Control tracked zero class 3 obligations, had
nothing to remind anyone about, and had no submissions to build a
golden set from — with the gate that ends Phase 0 unreachable by any
command.

This module is now the APPROVAL half only.

**Proposing moved to `discovery/register_proposal.py`**, which builds
from the drive rather than from the mailboxes — and that difference is
not a preference. Stage D against `control@` finds almost nothing: the
recurring senders are the tax portal and the e-invoicing gateway,
because the company's internal reporting was never sent there. It is in
`1. Invoices/2022 In/Progress Reports - 2022 In/` and folders like it.
A register built from the mail alone proposes an empty class 3 with a
clean conscience, which is the exact failure this system exists to
prevent. The mailbox-based proposer that used to live here was
superseded rather than kept alongside — two register builders is the
competing-revisions defect the charter flags in Stage B.

**Approving is a decision and only the CEO makes it.** Nothing reaches
`obligations.yaml` without `approved_by_ceo`, because §6 makes that
approval the thing that ends Phase 0, and `loader.build_obligations`
already refuses any row that lacks it: acting on a Stage D proposal is
acting on an inference (§1.1).

**What is deliberately NOT proposed.** A bulk send is not an
obligation — hundreds of messages on one day is a mailshot with a
median gap of zero. A conversation is not an obligation either: a
thread with a high reply ratio is people talking. Both are excluded by
`pattern_kind` and both are counted in the summary, so the register
says what it declined to propose as well as what it did.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

# What the observed cadence has to look like before a due expression can
# be written at all. Anything else is proposed with the due blank and a
# named reason — a wrong deadline alerts confidently on the wrong day,
# which §2.1 rates worse than no deadline.
_WEEKLY = (5, 10)
_FORTNIGHTLY = (11, 20)
_MONTHLY = (21, 45)
_QUARTERLY = (75, 110)


@dataclass
class Proposal:
    obligation_id: str
    name: str
    owner: str
    cadence: str
    due: str
    evidence: str
    confidence: str
    problem: str = ""          # why `due` is blank, when it is

    @property
    def usable(self) -> bool:
        return bool(self.due)


def _identifier(index: int, sender: str) -> str:
    local = sender.split("@")[0].upper().replace(".", "")[:6] or "OBL"
    return f"OPS-{local}-{index:03d}"


def _due_from(candidate) -> tuple[str, str, str]:
    """(cadence, due expression, problem). Exactly one of the last two."""
    gap = candidate.median_gap_days
    hour = candidate.modal_hour or 17

    if gap is None:
        return "", "", "no median gap could be measured from the timestamps"

    if _WEEKLY[0] <= gap <= _WEEKLY[1]:
        if not candidate.modal_weekday:
            return "weekly", "", ("arrives weekly but on no consistent day — "
                                  "the weekday is a tie in the timestamps")
        return "weekly", f"{candidate.modal_weekday} {hour:02d}:00", ""

    if _FORTNIGHTLY[0] <= gap <= _FORTNIGHTLY[1]:
        return "fortnightly", "", (
            f"arrives about every {gap:.0f} days — between weekly and "
            "monthly, so the cadence is a judgement rather than a reading")

    if _MONTHLY[0] <= gap <= _MONTHLY[1]:
        day = candidate.modal_day_of_month
        if not day:
            return "monthly", "", ("arrives monthly but on no consistent "
                                   "day of the month")
        if day > 28:
            return "monthly", "", (
                f"arrives around day {day}, and not every month has one — "
                "the day has to be chosen rather than observed")
        return "monthly", f"day {day} {hour:02d}:00", ""

    if _QUARTERLY[0] <= gap <= _QUARTERLY[1]:
        return "quarterly", "", (
            "arrives about quarterly; the register has no quarterly due "
            "expression yet, so the dates must be stated")

    return "", "", (f"median gap of {gap:.0f} days matches no cadence the "
                    "engine understands")


def propose(candidates, roster: set | None = None,
            min_confidence: str = "MEDIUM") -> tuple[list[Proposal], dict]:
    """Turn Stage D candidates into proposed obligations.

    `roster` filters to senders Control recognises: an obligation owned
    by an address that is not a person is not an obligation, it is a
    system sending mail.
    """
    order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    floor = order.get(min_confidence.upper(), 2)
    roster = {r.lower() for r in (roster or set())}

    proposals: list[Proposal] = []
    declined = {"bulk send": 0, "conversation": 0, "below confidence": 0,
                "sender not on the roster": 0, "no attachment": 0}

    for candidate in candidates:
        if candidate.pattern_kind == "BULK":
            declined["bulk send"] += 1
            continue
        if candidate.pattern_kind == "THREAD":
            declined["conversation"] += 1
            continue
        if order.get(candidate.confidence, 0) < floor:
            declined["below confidence"] += 1
            continue
        if roster and candidate.sender.lower() not in roster:
            declined["sender not on the roster"] += 1
            continue
        # An obligation is a controlled document arriving. A recurring
        # subject with nothing attached is a notification.
        if candidate.attachment_rate < 0.5:
            declined["no attachment"] += 1
            continue

        cadence, due, problem = _due_from(candidate)
        proposals.append(Proposal(
            obligation_id=_identifier(len(proposals) + 1, candidate.sender),
            name=candidate.subject_template[:70],
            owner=candidate.sender.lower(),
            cadence=cadence,
            due=due,
            problem=problem,
            confidence=candidate.confidence,
            evidence=(f"{candidate.occurrences} occurrence(s), "
                      f"{candidate.first_seen} to {candidate.last_seen}, "
                      f"{candidate.cadence}, "
                      f"{candidate.attachment_rate:.0%} with attachments"),
        ))
    return proposals, declined


def to_rows(proposals: list[Proposal], approved_by: str = "") -> list[dict]:
    """Obligation rows for `obligations.yaml`.

    `approved_by` is empty until a human sets it, and `build_obligations`
    refuses every row without it — so a proposal file written by mistake
    tracks nothing rather than tracking everything.
    """
    rows = []
    for item in proposals:
        row = {
            "id": item.obligation_id,
            "class": 3,
            "name": item.name,
            "owner": item.owner,
            "cadence": item.cadence,
            "due": item.due,
            "form": "",
            "approved_by_ceo": approved_by or None,
            "provenance": "stage_d_observed",
            "evidence": item.evidence,
            "confidence": item.confidence,
        }
        if item.problem:
            row["open_question"] = item.problem
        rows.append(row)
    return rows


def render_worksheet(proposals: list[Proposal], declined: dict,
                     today: date) -> str:
    usable = [p for p in proposals if p.usable]
    blocked = [p for p in proposals if not p.usable]

    lines = [
        f"# PROPOSED OBLIGATION REGISTER — {today:%d-%b-%Y}",
        "",
        "Stage D, §6. **These are inferences, not obligations.** Nothing "
        "below is tracked until it carries `approved_by_ceo`, because §6 "
        "makes that approval the thing that ends Phase 0 and acting on a "
        "proposal is acting on an inference (§1.1).",
        "",
        f"- **{len(usable)}** proposal(s) with a due date the engine can "
        "compute, ready to approve",
        f"- **{len(blocked)}** recur, but on no day anything could read — "
        "listed second, and each says why",
        "",
        "To approve every proposal that has a usable due date:",
        "",
        "    python -m control register --approve --by ahmed@ubcsis.com",
        "",
        "To approve a subset, name them: `--approve OPS-HSE-001 OPS-HR-002`.",
        "",
        "---",
        "",
        f"## Ready to approve — {len(usable)}",
        "",
    ]
    if not usable:
        lines += ["None. Nothing in the archive recurs on a day the engine "
                  "can turn into a deadline.", ""]
    else:
        lines += ["| id | what arrives | from | cadence | due | evidence |",
                  "|---|---|---|---|---|---|"]
        for item in usable:
            lines.append(f"| {item.obligation_id} | {item.name} | "
                         f"{item.owner} | {item.cadence} | {item.due} | "
                         f"{item.evidence} |")
        lines.append("")

    lines += [f"## Recurring, but no computable deadline — {len(blocked)}", ""]
    if not blocked:
        lines += ["None.", ""]
    else:
        lines += [
            "These arrive regularly enough to look like obligations and "
            "cannot be given a date without choosing one. They are listed "
            "rather than guessed at: a deadline that alerts confidently on "
            "the wrong day teaches people the system is wrong (§2.1).",
            "",
            "| id | what arrives | from | why there is no date |",
            "|---|---|---|---|",
        ]
        for item in blocked:
            lines.append(f"| {item.obligation_id} | {item.name} | "
                         f"{item.owner} | {item.problem} |")
        lines.append("")

    lines += ["## What was not proposed, and why", ""]
    if not any(declined.values()):
        lines += ["Nothing was declined.", ""]
    else:
        for reason, count in sorted(declined.items()):
            if count:
                lines.append(f"- **{count}** — {reason}")
        lines += [
            "",
            "A bulk send is a mailshot, not an obligation: hundreds of "
            "messages on one day has a median gap of zero. A conversation "
            "is people talking. A recurring subject with nothing attached "
            "is a notification. Each is counted rather than silently "
            "dropped, so the register says what it declined as well as "
            "what it proposed.",
            "",
        ]
    return "\n".join(lines)


# ---- approval ----------------------------------------------------------

def load_proposals(path: Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return list(data.get("obligations") or [])


def _approvable(row: dict) -> tuple[bool, str]:
    """(can this row be tracked, why not). Shared by both approval paths.

    The due expression is validated, not merely checked for emptiness.
    `register_proposal` writes "NOT ESTABLISHED" rather than a blank,
    which is truthy — so a presence check would approve every row that
    has no deadline at all, and an approved row that tracks nothing is
    worse than an unapproved one because it looks like coverage.
    """
    from .loader import parse_due

    due, problem = parse_due(str(row.get("due") or ""),
                             str(row.get("cadence") or ""), date.today())
    if due is not None:
        return True, ""
    # The row's own recorded reason first: "arrives weekly but on no
    # consistent day" tells the reader what to do about it, where "no due
    # expression" only tells them it is missing.
    return False, (row.get("open_question") or problem or "reason not recorded")


def approve_in_place(obligations_path: Path, by: str,
                     only: set | None = None) -> tuple[list[str], list[str]]:
    """Stamp unapproved rows that are already in `obligations.yaml`.

    `approve()` moves rows from a Stage D proposals file. This is the
    other shape of the same decision: a register written straight into
    `obligations.yaml` — the starter register assigned from the archive
    on 26-Aug-2026 — sits there with `approved_by_ceo: null`, tracked by
    nothing, until a human puts a name on it. Without this path the CEO
    would have to hand-edit six rows to end Phase 0, which is the
    homework this register exists to remove.

    **The file is edited line by line rather than re-serialised**, and
    that is deliberate. `obligations.yaml` carries the header that says
    which of these dates were observed and which were assigned by
    Control — `yaml.safe_dump` would silently drop every comment in it,
    and a register that loses the record of its own provenance the first
    time it is approved is exactly the failure §1.1 is about.
    """
    import re

    path = Path(obligations_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = list(data.get("obligations") or [])

    wanted, skipped = set(), []
    for row in rows:
        obligation_id = str(row.get("id") or "")
        if only and obligation_id not in only:
            continue
        if row.get("approved_by_ceo"):
            skipped.append(f"{obligation_id}: already approved by "
                           f"{row['approved_by_ceo']}")
            continue
        ok, why = _approvable(row)
        if not ok:
            skipped.append(f"{obligation_id}: no computable due date — {why}")
            continue
        wanted.add(obligation_id)

    if not wanted:
        return [], skipped

    identifier = re.compile(r"^\s*-\s+id:\s*(\S+)\s*$")
    pending = re.compile(r"^(\s*)approved_by_ceo:\s*(null|~|)\s*$")

    lines = path.read_text(encoding="utf-8").splitlines()
    current, approved = "", []
    for index, line in enumerate(lines):
        found = identifier.match(line)
        if found:
            current = found.group(1).strip("\"'")
            continue
        stamp = pending.match(line)
        if stamp and current in wanted:
            lines[index] = f"{stamp.group(1)}approved_by_ceo: {by}"
            approved.append(current)
            wanted.discard(current)

    for missed in sorted(wanted):
        skipped.append(f"{missed}: no `approved_by_ceo:` line to stamp — "
                       "the row was not written by Control, so it is left "
                       "alone rather than rewritten")

    if approved:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return approved, skipped


def approve(proposals_path: Path, obligations_path: Path, by: str,
            only: set | None = None) -> tuple[list[str], list[str]]:
    """Move approved proposals into the live register. Never removes.

    Returns (approved ids, skipped ids with a reason). A proposal with
    no due expression is never approved — `build_obligations` would
    refuse it anyway and report it as a gap, and an approved row that
    tracks nothing is worse than an unapproved one, because it looks
    like coverage.
    """
    proposals = load_proposals(proposals_path)
    live = yaml.safe_load(
        Path(obligations_path).read_text(encoding="utf-8")) or {}
    rows = list(live.get("obligations") or [])
    existing = {str(r.get("id")) for r in rows}

    approved, skipped = [], []
    for row in proposals:
        obligation_id = str(row.get("id") or "")
        if only and obligation_id not in only:
            continue
        if obligation_id in existing:
            skipped.append(f"{obligation_id}: already in the register")
            continue
        ok, why = _approvable(row)
        if not ok:
            skipped.append(f"{obligation_id}: no computable due date — {why}")
            continue
        rows.append({**row, "approved_by_ceo": by})
        approved.append(obligation_id)

    live["obligations"] = rows
    Path(obligations_path).write_text(
        yaml.safe_dump(live, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    return approved, skipped
