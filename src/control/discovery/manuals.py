"""Manual discovery — charter §6 Stage C, §7.1 check C6.

C6 asks whether a submission conforms to the manual, and §1.2 requires
the clause to be quoted. Without the manuals indexed and their mandating
clauses extracted, C6 cannot honestly return `CONFORMS` — it can only
return "I have no manual to check against", which the charter renders as
`NOT ASSESSED` rather than a silent pass.

The charter says twelve manuals exist. This module does not assume it.
It finds candidates on the drive, scores why each looks like a manual,
and lists them for CEO confirmation — because a document that merely has
"manual" in its filename is a candidate, not an authority, and the
authority question is the one C6 depends on.

Clause extraction runs only after confirmation. Extracting mandating
clauses from a document nobody has confirmed as the governing manual
would produce obligations traceable to nothing.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Filename signals, weighted by how strongly each implies a governing
# document rather than a document that merely mentions one.
_NAME_SIGNALS = (
    (re.compile(r"(?i)\bmanual\b"), 5, "filename says manual"),
    (re.compile(r"(?i)\bدليل\b"), 5, "filename says دليل (manual)"),
    (re.compile(r"(?i)\bprocedure"), 3, "filename says procedure"),
    (re.compile(r"(?i)\bإجراء"), 3, "filename says إجراء (procedure)"),
    (re.compile(r"(?i)\bpolic(?:y|ies)\b"), 3, "filename says policy"),
    (re.compile(r"(?i)\b(?:QMS|ISO\s?9001|ISO\s?14001|ISO\s?45001)\b"), 4,
     "filename references a management system standard"),
    (re.compile(r"(?i)\b(?:rev|revision|issue)\s?\d"), 2,
     "filename carries a revision number"),
    (re.compile(r"(?i)\bsystem\b"), 1, "filename says system"),
    (re.compile(r"(?i)\bhandbook\b"), 3, "filename says handbook"),
)

# Content signals. A manual mandates; a report describes.
_CONTENT_SIGNALS = (
    (re.compile(r"(?i)\bshall\s+(?:be\s+)?(?:submit|prepare|record|report|"
                r"maintain|issue|complete)"), 4,
     "contains mandating language (shall submit/prepare/record)"),
    (re.compile(r"(?i)\bيجب\s"), 3, "contains mandating language (يجب)"),
    (re.compile(r"(?i)\btable of contents\b|\bفهرس\b"), 2,
     "has a table of contents"),
    (re.compile(r"(?i)\b(?:clause|section)\s+\d+(?:\.\d+)+"), 3,
     "uses numbered clauses"),
    (re.compile(r"(?i)\bdocument\s+(?:control|no\.?|reference)\b"), 2,
     "has document control"),
    (re.compile(r"(?i)\b(?:approved|issued)\s+by\b"), 1, "carries an approver"),
    (re.compile(r"(?i)\bform\s+(?:no\.?|code)?\s*[A-Z]{2,4}-\d"), 3,
     "references controlled form codes"),
)

# One sentence character: anything but a newline, and a full stop only
# when it sits inside a number. Without that exception "Clause 4.2.1"
# ends the sentence before it starts, and every extracted clause loses
# the reference §1.2 requires it to quote.
_S = r"(?:[^.\n]|\.(?=\d))"

# Clauses that create an obligation — the reason Stage C reads manuals.
_MANDATE = re.compile(
    r"(?i)(" + _S + r"{0,200}?\b(?:shall|must|is required to|يجب)\b"
    + _S + r"{0,200}?\b(?:submit|submitted|report|reported|record|recorded|"
    r"prepare|prepared|issue|issued|maintain|maintained|complete|completed|"
    r"تقديم|تقرير|سجل)\b" + _S + r"{0,200})"
)

_CADENCE = re.compile(
    r"(?i)\b(dail(?:y|ies)|weekly|fortnightly|monthly|quarterly|"
    r"semi-annual(?:ly)?|annual(?:ly)?|yearly|per shift|each shift|"
    r"يومي|أسبوعي|شهري|ربع سنوي|سنوي)\b"
)

# Loud enough to be worth a look, quiet enough not to list the drive.
CANDIDATE_THRESHOLD = 5


@dataclass
class ManualCandidate:
    path: str
    score: int = 0
    reasons: list = field(default_factory=list)
    confidential: bool = False
    readable: bool = True
    revision: str = ""
    mandate_count: int = 0

    @property
    def confidence(self) -> str:
        if self.score >= 12:
            return "HIGH"
        return "MEDIUM" if self.score >= 8 else "LOW"


@dataclass
class MandatingClause:
    manual: str
    text: str
    cadence: str = ""
    clause_ref: str = ""


_REVISION = re.compile(r"(?i)\b(?:rev|revision|issue)\.?\s*([0-9]+(?:\.[0-9]+)?)")


def score_candidate(relative_path: str, text: str | None) -> ManualCandidate:
    """Score one document. `text` is None when it could not be read."""
    candidate = ManualCandidate(path=relative_path, readable=text is not None)
    name = Path(relative_path).name

    for pattern, weight, reason in _NAME_SIGNALS:
        if pattern.search(relative_path):
            candidate.score += weight
            candidate.reasons.append(reason)

    match = _REVISION.search(name)
    if match:
        candidate.revision = match.group(1)

    if text:
        head = text[:60_000]
        for pattern, weight, reason in _CONTENT_SIGNALS:
            if pattern.search(head):
                candidate.score += weight
                candidate.reasons.append(reason)
        candidate.mandate_count = len(_MANDATE.findall(head))
        if candidate.mandate_count:
            candidate.score += min(candidate.mandate_count, 5)
            candidate.reasons.append(
                f"{candidate.mandate_count} mandating clause(s) found")
    else:
        # Unread documents are scored on the filename alone. That is a
        # weaker basis, and the note says so rather than letting a low
        # score read as "not a manual" (§1.1).
        candidate.reasons.append(
            "not read — scored on filename only, so this may be a manual "
            "whose contents could not be seen")
    return candidate


def extract_mandates(manual_path: str, text: str) -> list[MandatingClause]:
    """Clauses that mandate a report, record or submission (§6 Stage C).

    Run only against manuals the CEO has confirmed. A clause pulled from
    an unconfirmed document would create an obligation traceable to
    nothing, which is worse than a missing obligation because it looks
    like a finding.
    """
    clauses: list[MandatingClause] = []
    for raw in _MANDATE.findall(text):
        sentence = " ".join(str(raw).split())
        if len(sentence) < 25:
            continue
        cadence = _CADENCE.search(sentence)
        reference = re.search(r"(?i)\b(?:clause|section)\s+(\d+(?:\.\d+)*)",
                              sentence)
        clauses.append(MandatingClause(
            manual=manual_path,
            text=sentence[:400],
            cadence=(cadence.group(1).lower() if cadence else ""),
            clause_ref=(reference.group(1) if reference else ""),
        ))
    return clauses


def competing_revisions(candidates: list[ManualCandidate]) -> dict[str, list[str]]:
    """Documents that look like the same manual at different revisions.

    §6 Stage C: competing revisions are `AMBIGUOUS — CEO DECISION`, not
    a most-recent-wins guess. Evaluating a submission against the wrong
    revision of a form produces a confident, wrong verdict.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for candidate in candidates:
        stem = _REVISION.sub("", Path(candidate.path).stem)
        key = " ".join(
            "".join(c if c.isalnum() else " " for c in stem.lower()).split())
        if key:
            groups[key].append(candidate.path)
    return {key: sorted(paths) for key, paths in groups.items()
            if len(paths) > 1}


def render_manual_inventory(candidates: list[ManualCandidate],
                            expected: int = 12) -> str:
    """The list the CEO confirms before any clause is extracted."""
    ranked = sorted(candidates, key=lambda c: (-c.score, c.path))
    high = [c for c in ranked if c.confidence == "HIGH"]
    medium = [c for c in ranked if c.confidence == "MEDIUM"]

    lines = [
        "# Manual inventory — Stage C, for CEO confirmation",
        "",
        "Charter §6 requires every clause mandating a report, record or",
        "submission to be extracted from the manuals. Check C6 quotes those",
        "clauses; without them C6 cannot return CONFORMS, only",
        "`NOT ASSESSED`.",
        "",
        "**Nothing below has been treated as authoritative.** These are",
        "candidates found on the drive, scored on filename and content. A",
        "document with \"manual\" in its name is a candidate, not an",
        "authority, and C6 depends on the difference.",
        "",
        f"Charter expects **{expected} manuals**. Found "
        f"**{len(high)} high-confidence**, {len(medium)} medium, "
        f"{len(ranked) - len(high) - len(medium)} low.",
        "",
    ]

    if len(high) < expected:
        lines += [
            f"> **Gap.** {expected - len(high)} of the {expected} manuals the",
            "> charter names are not accounted for at high confidence. They",
            "> may be under a name this scan did not recognise, unreadable",
            "> scans, or not written. Which of those it is changes what C6",
            "> can honestly claim, so it is a question rather than a",
            "> conclusion (§1.1).",
            "",
        ]

    conflicts = competing_revisions(ranked)
    if conflicts:
        lines += ["## AMBIGUOUS — CEO DECISION: competing revisions", "",
                  "Evaluating against the wrong revision produces a",
                  "confident, wrong verdict. Confirm which governs.", ""]
        for key, paths in sorted(conflicts.items()):
            lines.append(f"- **{key}**")
            lines += [f"    - `{p}`" for p in paths]
        lines.append("")

    lines += ["## Candidates", "",
              "| Confirm | Confidence | Score | Document | Rev | Mandating clauses |",
              "|---|---|---|---|---|---|"]
    for candidate in ranked:
        flag = " ⚠ not read" if not candidate.readable else ""
        lines.append(
            f"| ☐ | {candidate.confidence} | {candidate.score} | "
            f"`{candidate.path}`{flag} | {candidate.revision or '—'} | "
            f"{candidate.mandate_count or '—'} |")

    lines += ["", "## Why each scored what it did", ""]
    for candidate in ranked:
        lines.append(f"**`{candidate.path}`** — {candidate.score}")
        for reason in candidate.reasons:
            lines.append(f"  - {reason}")
        lines.append("")

    lines += [
        "## Next",
        "",
        "1. Tick the documents that are the governing manuals.",
        "2. Control extracts the mandating clauses from those only.",
        "3. Each extracted clause becomes a candidate obligation with the",
        "   manual and clause reference attached, so every C6 finding can",
        "   quote its authority (§1.2).",
        "",
        "Anything left unticked is not read for clauses. A manual missed",
        "here shows up as an obligation Control never tracks, which is a",
        "visible gap — unlike a clause extracted from the wrong document,",
        "which is a finding with no authority behind it.",
    ]
    return "\n".join(lines) + "\n"
