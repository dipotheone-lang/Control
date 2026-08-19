"""The gap register — execution order 18-Aug-2026, step 3.

*"Build the gap register from every open item: the 7 missing data
points, 40 unverified answers, all `TO BE CONFIRMED` fields, every
unmatched reference in mail. Type each one."*

The point of typing is §6 of the same order: legal coverage *"will read
0% and must stay visible at 0%. That is D-52 working, not failing."*
A single "open items: 47" would hide that — the six factual gaps close
when a named person looks something up, and the legal ones do not close
until counsel is engaged, and averaging the two produces a number that
is comfortable and meaningless. So the register never totals across
types, and B10's "coverage index split three ways, never averaged" says
the same thing about the index built on it.

**Two types are the order's; the third is Control's and is flagged as
such.** §6 names FACTUAL and LEGAL. Neither fits "the ETA exception
detector is not built" — that is not a fact anyone can look up and not
a position counsel can take. Calling it FACTUAL would put it on
Hadeer's list, which is worse than a third label. So BUILD exists,
every report says the order names only two, and the CEO is asked to
confirm it (§1.3 — ambiguous, escalate, never invent a rule silently).

**This is not B8.** B8 is the gap register *and closure engine* under
§18, and §18 does not exist in the charter. What is built here is the
register: collect, type, own, and count. Nothing closes itself.
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

FACTUAL = "FACTUAL"
LEGAL = "LEGAL"
BUILD = "BUILD"

# Ordered by who can close it, most closable first.
TYPES = (FACTUAL, BUILD, LEGAL)

TYPE_NOTE = {
    FACTUAL: "closable by a named person looking something up",
    BUILD: "closable by Control being built further — a type the "
           "execution order does not name, raised for confirmation",
    LEGAL: "never closable by the system (execution order §6)",
}


@dataclass(frozen=True)
class Gap:
    gap_id: str
    text: str
    kind: str
    owner: str
    source: str


def _clean(text: str) -> str:
    return " ".join(str(text).replace("**", "").split())


def _short(text: str, limit: int) -> str:
    """Truncate visibly. A sentence that stops mid-word with no mark
    reads as the whole item, and the reader acts on half a finding."""
    flat = _clean(text)
    return flat if len(flat) <= limit else flat[:limit - 1].rstrip() + "…"


# ---- the order's own list ---------------------------------------------

_ORDER_ROW = re.compile(r"^\|\s*(?!Item\b)(?!-)(.+?)\s*\|\s*(.+?)\s*\|\s*"
                        r"(.+?)\s*\|\s*$")


def from_execution_order(text: str) -> list[Gap]:
    """§6's table — the seven the CEO already knows about."""
    section = text.split("## 6. WHAT REMAINS OPEN")
    if len(section) < 2:
        return []
    # Stop at a horizontal rule, which is a line that is ONLY dashes.
    # Splitting on the substring "---" ended the table at its own
    # separator row and silently returned nothing — the register then
    # reported seven factual gaps from a different source and looked
    # entirely plausible, which is why the reconciliation against the
    # order's own count is not decoration.
    body = []
    for line in section[1].splitlines():
        if line.strip() and set(line.strip()) <= set("-"):
            break
        body.append(line)
    gaps = []
    for line in body:
        match = _ORDER_ROW.match(line.strip())
        if not match or set(line.strip()) <= set("|- "):
            continue
        item, owner, kind = (_clean(g) for g in match.groups())
        if item.lower() == "item":
            continue
        gaps.append(Gap(
            gap_id=f"G-ORDER-{len(gaps) + 1:02d}", text=item,
            kind=LEGAL if kind.upper().startswith("LEGAL") else FACTUAL,
            owner=owner, source="execution order §6"))
    return gaps


# ---- the charter's open decisions -------------------------------------

_OPEN_DECISION = re.compile(r"^\|\s*(O-\d+)\s*\|\s*(.+?)\s*\|")


def from_charter(text: str) -> list[Gap]:
    """Appendix B's open decisions, excluding the closed ones.

    A closed row is struck through (`~~O-01~~`), so the regex requiring
    a bare id at the start of the cell skips them without needing to
    understand why each was closed.
    """
    gaps = []
    for line in text.splitlines():
        match = _OPEN_DECISION.match(line.strip())
        if not match:
            continue
        gap_id, description = match.group(1), _clean(match.group(2))
        # O-03 is the tax advisor; O-06 to O-10 are counsel. Both are
        # answered by a qualified outsider, which is what LEGAL means
        # here — not that the question is about law.
        kind = LEGAL if gap_id in ("O-03", "O-06", "O-07", "O-08",
                                   "O-10") else FACTUAL
        gaps.append(Gap(gap_id=gap_id, text=description, kind=kind,
                        owner="CEO", source="charter Appendix B"))
    return gaps


# ---- unanswered fields in the governance drafts -----------------------

_MARKERS = ("TO BE CONFIRMED", "UNVERIFIED")


def from_documents(paths) -> list[Gap]:
    """Every `TO BE CONFIRMED` and `UNVERIFIED` left in the drafts.

    These are deliberate: the drafts say so rather than supplying a
    plausible figure. Deliberate is not the same as closed, and a marker
    that nobody counts is a marker that survives into the signed
    version.
    """
    gaps = []
    for path in sorted(Path(p) for p in paths):
        if not path.is_file():
            continue
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            if not any(marker in line for marker in _MARKERS):
                continue
            gaps.append(Gap(
                gap_id=f"G-{path.stem}-{number}",
                text=_short(line, 180),
                # A governance draft's unanswered field is answered by
                # counsel or by the advisor, not by looking it up.
                kind=LEGAL,
                owner="counsel" if "ADVISOR" not in path.stem.upper()
                      else "tax advisor",
                source=f"{path.name}:{number}"))
    return gaps


# ---- what Control knows is not running --------------------------------

def from_loader(loader_gaps) -> list[Gap]:
    """The gaps the running system already reports.

    These are the only ones with live evidence behind them: they are
    recomputed every cycle from configuration and the database rather
    than transcribed from a document, so a stale one disappears by
    itself.
    """
    gaps = []
    for index, text in enumerate(loader_gaps, start=1):
        clean = _clean(text)
        kind = BUILD if any(cue in clean for cue in (
            "is not built", "await the event register", "no events on record",
            "mechanism", "detector")) else FACTUAL
        owner = "Control" if kind is BUILD else "CEO"
        if "O-03" in clean:
            kind, owner = LEGAL, "tax advisor"
        gaps.append(Gap(gap_id=f"G-LIVE-{index:02d}", text=_short(clean, 240),
                        kind=kind, owner=owner, source="live cycle"))
    return gaps


# ---- assembly ---------------------------------------------------------

def collect(order_text: str, charter_text: str, document_paths,
            loader_gaps) -> list[Gap]:
    return (from_execution_order(order_text)
            + from_charter(charter_text)
            + from_documents(document_paths)
            + from_loader(loader_gaps))


def counts(gaps: list[Gap]) -> dict[str, int]:
    return {kind: sum(1 for g in gaps if g.kind == kind) for kind in TYPES}


def render(gaps: list[Gap], today: date) -> str:
    by_kind = counts(gaps)
    lines = [
        f"# GAP REGISTER — {today:%d-%b-%Y}",
        "",
        "Execution order 18-Aug-2026, step 3. Every open item, typed by "
        "who can close it.",
        "",
        f"**Counted per type and never totalled.** The {by_kind[FACTUAL]} "
        "factual gaps close when a named person looks something up; the "
        f"{by_kind[LEGAL]} legal ones do not close until counsel is "
        "engaged. A single number across both would be comfortable and "
        "meaningless, and §6 of the order is explicit that legal coverage "
        "*must stay visible at 0%* — which an average is precisely a way "
        "of not doing.",
        "",
    ]
    for kind in TYPES:
        lines.append(f"- **{kind}: {by_kind[kind]}** — {TYPE_NOTE[kind]}")
    lines += [
        "",
        "**BUILD is Control's type, not the order's.** §6 names FACTUAL "
        "and LEGAL. Neither fits \"the ETA exception detector is not "
        "built\" — it is not a fact anyone can look up and not a position "
        "counsel can take, and calling it FACTUAL would put it on "
        "Hadeer's list. The CEO is asked to confirm the third type "
        "rather than it being adopted quietly (§1.3).",
        "",
        "**Nothing here closes itself.** B8 is the gap register *and "
        "closure engine* under §18, and §18 does not exist in the "
        "charter. This is the register.",
        "",
        "---",
        "",
    ]

    for kind in TYPES:
        subset = [g for g in gaps if g.kind == kind]
        lines += [f"## {kind} — {len(subset)}", "",
                  f"*{TYPE_NOTE[kind]}*", ""]
        if not subset:
            lines += ["None on record.", ""]
            continue
        lines += ["| id | item | owner | source |", "|---|---|---|---|"]
        for gap in subset:
            lines.append(
                f"| {gap.gap_id} | {gap.text} | {gap.owner} | {gap.source} |")
        lines.append("")

    return "\n".join(lines)


def reconcile(gaps: list[Gap], order_text: str) -> list[str]:
    """The order's own numbers against what was actually found.

    Step 3 names "the 7 missing data points, 40 unverified answers".
    Control cannot confirm either number and does not pretend to — it
    counts what it found and reports the difference, which is a
    disagreement to be resolved by a human and not by adjusting the
    count until it matches (§1.1).
    """
    notes = []
    from_order = len(from_execution_order(order_text))
    if from_order != 7:
        notes.append(
            f"Step 3 names 7 missing data points; §6's table holds "
            f"{from_order} row(s). Control read the table rather than the "
            "sentence, and reports the difference rather than reconciling "
            "it (§1.1).")
    unverified = len([g for g in gaps if ".md:" in g.source])
    if unverified != 40:
        notes.append(
            f"Step 3 names 40 unverified answers; {unverified} "
            "`TO BE CONFIRMED` / `UNVERIFIED` marker(s) were found in the "
            "governance drafts. The two are probably counting different "
            "things — the drafts are one place those answers live, and "
            "the CEO's own list may be another. Reported, not "
            "reconciled.")
    return notes
