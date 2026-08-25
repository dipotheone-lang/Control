"""The extraction brief — execution order 18-Aug-2026, step 2.

Four class 1 deadlines currently alert on dates the CEO stated from
memory. The company's own filing archive is evidence about those same
rules, and it is evidence nobody has looked at. This module looks.

**It reports disagreements first and does not resolve them.** The order
is explicit about that, and so is §14.2: anything touching a statutory
deadline is Tier C — raised with evidence for a human decision, never
applied by the system. Nothing here changes a rule. It produces a brief.

**Observed is not due.** The archive shows when filings actually
happened, which is a different fact from when they were due. A company
that files on the 20th every month has a habit, not a rule; the
deadline may be the 25th and it may be the 15th and they have been late
every time. So this module reports cadence and count, and refuses to
turn either into a date.

What it can do honestly is count. Payroll tax is recorded as quarterly
(D-23, D-24). If the archive holds twelve remittances in a year rather
than four, that rule is wrong and eleven obligations are missing from
the register. That count is the highest-value output here, and it is
the reason the module dedupes by period rather than by document — the
same return exists as a draft, a signed copy and a scan, and counting
documents would manufacture the very finding it is looking for.

**Matching is on path and filename only.** Metadata, not content: it
runs over thirteen thousand documents in seconds, it cannot leak
anything it never opens, and a filing whose name does not identify it
is a document-control finding in its own right.
"""

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Periods, most specific first. A path naming both a month and a year
# is monthly evidence; one naming only a year is annual evidence and
# cannot answer a question about monthly cadence.
_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
    # Arabic, with the spelling variants that actually occur in the
    # archive — hamza written and unwritten, and the Egyptian forms of
    # June and July.
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "مايو": 5,
    "يونيو": 6, "يونيه": 6, "يوليو": 7, "يوليه": 7,
    "أغسطس": 8, "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10,
    "نوفمبر": 11, "ديسمبر": 12,
}

_YEAR = r"(20[12][0-9])"
_ISO_MONTH = re.compile(_YEAR + r"[-_.\s]?(0[1-9]|1[0-2])(?![0-9])")
_MONTH_ISO = re.compile(r"(?<![0-9])(0[1-9]|1[0-2])[-_.\s]" + _YEAR)
_QUARTER = re.compile(r"(?i)q([1-4])[-_.\s]*" + _YEAR
                      + r"|" + _YEAR + r"[-_.\s]*q([1-4])")
_NAMED_MONTH = re.compile(
    r"(?i)(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")")
_BARE_YEAR = re.compile(r"(?<![0-9])" + _YEAR + r"(?![0-9])")

MONTHLY, QUARTERLY, ANNUAL = "month", "quarter", "year"


@dataclass(frozen=True)
class Period:
    kind: str            # MONTHLY | QUARTERLY | ANNUAL
    year: int
    index: int = 0       # month 1-12, quarter 1-4, or 0 for a year

    def __str__(self) -> str:
        if self.kind == MONTHLY:
            return f"{self.year}-{self.index:02d}"
        if self.kind == QUARTERLY:
            return f"{self.year}-Q{self.index}"
        return str(self.year)


def read_period(text: str) -> Period | None:
    """The most specific period the path names, or None.

    None is a real answer and is reported as one: a filing whose path
    does not say which period it covers cannot be counted, and that is
    a document-control finding rather than a reason to guess.
    """
    match = _ISO_MONTH.search(text)
    if match:
        return Period(MONTHLY, int(match.group(1)), int(match.group(2)))
    match = _MONTH_ISO.search(text)
    if match:
        return Period(MONTHLY, int(match.group(2)), int(match.group(1)))

    match = _QUARTER.search(text)
    if match:
        quarter = match.group(1) or match.group(4)
        year = match.group(2) or match.group(3)
        return Period(QUARTERLY, int(year), int(quarter))

    year_match = _BARE_YEAR.search(text)
    named = _NAMED_MONTH.search(text)
    if named and year_match:
        return Period(MONTHLY, int(year_match.group(1)),
                      _MONTHS[named.group(1).lower()])
    if year_match:
        return Period(ANNUAL, int(year_match.group(1)))
    return None


@dataclass(frozen=True)
class Evidence:
    obligation_id: str
    path: str
    period: Period | None
    matched_on: str


@dataclass
class Observed:
    """What the archive shows for one obligation."""

    obligation_id: str
    documents: int = 0
    periods: set = field(default_factory=set)
    undated: list = field(default_factory=list)
    paths_by_period: dict = field(default_factory=lambda: defaultdict(list))

    @property
    def years(self) -> set:
        return {p.year for p in self.periods}

    def per_year(self, kind: str) -> dict[int, int]:
        counts: dict[int, int] = defaultdict(int)
        for period in self.periods:
            if period.kind == kind:
                counts[period.year] += 1
        return dict(counts)

    @property
    def granularity(self) -> str | None:
        """How this archive names its periods — month, quarter or year.

        The comparison used to look at monthly periods only, which made
        it blind in a way that produced a confident wrong answer: an
        obligation whose filings are named "Q1 2025" or "2025" had no
        monthly periods at all, so nothing could contradict its stated
        cadence and the brief reported no disagreement. That is a fact
        about the naming convention, not about the company.
        """
        counted = {kind: sum(len(y) for y in [self.per_year(kind)])
                   for kind in (MONTHLY, QUARTERLY, ANNUAL)}
        best = max(counted, key=lambda k: counted[k])
        return best if counted[best] else None

    def interior_years(self, kind: str) -> dict[int, int]:
        """Period counts for years the archive plausibly covers in full.

        A year is only evidence about cadence if the archive holds the
        span. The first and last years of any collection are usually
        partial, so they are reported but never used to contradict a
        stated rule on their own.

        **A year inside the span with nothing in it counts as zero, not
        as absent.** `per_year` only knows about years that have
        periods, so an annual obligation with filings in 2024 and 2026
        and nothing in 2025 read as "1, 1 — matching the annual
        cadence". The missing year was invisible, which is absence
        looking like compliance — the failure this whole module exists
        to avoid.
        """
        counts = self.per_year(kind)
        if len(counts) <= 2:
            return counts
        span = sorted(counts)
        return {year: counts.get(year, 0)
                for year in range(span[0] + 1, span[-1])}

    @property
    def complete_years(self) -> dict[int, int]:
        """Interior years at whatever granularity the archive uses."""
        kind = self.granularity
        return self.interior_years(kind) if kind else {}


def compile_marker(marker: str):
    """A marker matcher that will not fire inside a longer word.

    This is not a refinement. `vat` is a substring of "excavation" and
    `eta` is a substring of "metal" and "detail" — in a contracting
    company's archive those two markers alone would have matched
    thousands of drawings, given most of them a month from their
    filename, and produced a confident monthly VAT cadence out of
    excavation drawings. The brief's whole value is a count, and a
    count built from that is worse than no brief.

    Latin markers get word boundaries. Arabic ones keep substring
    matching, because Arabic attaches its article and prepositions
    directly to the word — `تأمينات` has to match `والتأمينات` — and
    the Latin failure mode does not arise there.

    The boundary means a Latin marker matches the word and not its
    inflections, so `filing-evidence.yaml` enumerates the variants that
    occur — "licence" and "licences", "e-invoice" and "e-invoicing".
    That is deliberately dull: a wildcard syntax in a config file is a
    small language, and §13.2's rule about config being data rather
    than code applies to the matcher as much as to the checks.
    """
    lowered = marker.lower()
    if lowered.isascii():
        # Digits may follow — "VAT2026-01.pdf" is a real filename — but
        # letters may not, or `eta` matches "ETABS", the structural
        # software whose model files fill a technical office.
        return re.compile(
            r"(?<![a-z0-9])" + re.escape(lowered) + r"(?![a-z])").search
    return lambda text, needle=lowered: needle in text


def _markers(config: dict | None) -> tuple[list[dict], list]:
    config = config or {}
    rules = []
    for row in config.get("obligations") or []:
        rules.append({
            "id": str(row.get("id") or ""),
            "markers": [(str(m).lower(), compile_marker(str(m)))
                        for m in (row.get("markers") or [])],
            "exclude": [compile_marker(str(m))
                        for m in (row.get("exclude") or [])],
        })
    excluded = [compile_marker(str(m))
                for m in (config.get("exclude_path_markers") or [])]
    return rules, excluded


def scan_paths(paths, config: dict | None) -> list[Evidence]:
    """Match paths to obligations. Read-only, metadata only."""
    rules, excluded_globally = _markers(config)
    found: list[Evidence] = []
    for raw in paths:
        text = str(raw).lower()
        if any(matches(text) for matches in excluded_globally):
            continue
        for rule in rules:
            if any(matches(text) for matches in rule["exclude"]):
                continue
            hit = next((name for name, matches in rule["markers"]
                        if matches(text)), None)
            if hit is None:
                continue
            found.append(Evidence(
                obligation_id=rule["id"], path=str(raw),
                period=read_period(str(raw)), matched_on=hit))
            break            # one obligation per document
    return found


def observe(evidence: list[Evidence]) -> dict[str, Observed]:
    by_obligation: dict[str, Observed] = {}
    for item in evidence:
        record = by_obligation.setdefault(
            item.obligation_id, Observed(item.obligation_id))
        record.documents += 1
        if item.period is None:
            record.undated.append(item.path)
            continue
        record.periods.add(item.period)
        record.paths_by_period[str(item.period)].append(item.path)
    return by_obligation


# ---- the disagreements, which come first ------------------------------

STATED_CADENCE_PERIODS = {"monthly": 12, "quarterly": 4, "annual": 1}

# The granularity each cadence implies.
CADENCE_GRANULARITY = {"monthly": MONTHLY, "quarterly": QUARTERLY,
                       "annual": ANNUAL}

# Fine to coarse. What matters is whether the OBSERVED naming is at
# least as fine as the cadence being tested, because then the count of
# distinct periods is comparable to the count the cadence expects.
#
# Four filings a year named "2025-03", "2025-06", "2025-09", "2025-12"
# are quarterly filings that happen to be named by month, and that is
# exactly what the live archive holds for payroll. An earlier version
# refused to compare them at all — "a monthly count cannot confirm a
# quarterly rule" — and threw away the answer to the order's own
# highest-value question. Monthly naming is finer than quarterly, so it
# can say four and it can say twelve.
#
# The reverse does not hold. One folder named "2025" against a monthly
# rule says nothing: twelve returns may be inside it.
FINENESS = {MONTHLY: 0, QUARTERLY: 1, ANNUAL: 2}


def can_speak_to(observed_kind: str | None, cadence: str) -> bool:
    """Whether a count at this granularity is comparable to this cadence."""
    wanted = CADENCE_GRANULARITY.get(cadence)
    if observed_kind is None or wanted is None:
        return False
    return FINENESS[observed_kind] <= FINENESS[wanted]


@dataclass(frozen=True)
class Disagreement:
    obligation_id: str
    stated: str
    observed: str
    consequence: str


def disagreements(statutory_config: dict | None,
                  observed: dict[str, Observed]) -> list[Disagreement]:
    """Where the archive contradicts the CEO-stated rule.

    Reported, never resolved (§14.2 Tier C). The consequence line says
    what would follow IF the archive is right — not that it is.
    """
    out: list[Disagreement] = []
    for row in (statutory_config or {}).get("obligations") or []:
        obligation_id = str(row.get("id") or "")
        record = observed.get(obligation_id)
        if record is None:
            continue
        cadence = str(row.get("cadence") or "").lower()
        expected = STATED_CADENCE_PERIODS.get(cadence)
        if expected is None:
            continue

        # Monthly periods per interior year, which is the only shape
        # that can contradict a cadence without the archive's ragged
        # edges doing the talking. ONE entry per obligation, listing
        # every year that contradicts: a paragraph repeated once per
        # year says nothing the first one did not, and a reader who
        # skims the second stops reading the section.
        kind = record.granularity
        if not can_speak_to(kind, cadence):
            continue
        offending = {year: count
                     for year, count in sorted(
                         record.interior_years(kind).items())
                     if count > expected}
        if not offending:
            continue
        missing = max(offending.values()) - expected
        years = ", ".join(f"{year}: {count}"
                          for year, count in sorted(offending.items()))
        out.append(Disagreement(
            obligation_id=obligation_id,
            stated=f"{cadence} — {expected} period(s) a year "
                   f"({row.get('decision') or 'no decision recorded'})",
            observed=(f"{len(offending)} full year(s) hold more "
                      f"{kind}ly periods than that — {years}".replace(
                          "yearly", "annual")),
            consequence=(
                f"the stated cadence is wrong and about {missing} "
                f"obligation(s) a year are missing from the register for "
                f"{obligation_id}. If the archive is wrong instead, some of "
                "those documents are not filings. Control cannot tell which "
                "from a filename, and does not guess (§14.2 Tier C — this "
                "is raised, not acted on)."),
        ))
    return out


# ---- provenance -------------------------------------------------------

def upgrade_candidates(statutory_config: dict | None,
                       observed: dict[str, Observed],
                       disagreeing: list[Disagreement],
                       minimum_periods: int = 6) -> list[dict]:
    """Rules the archive corroborates, offered for a human decision.

    `document_evidenced` is the rung step 2 names, and it is NOT
    `verified_by_advisor` — promoting anything to that without a named
    human is a §7 stop condition. Corroboration by the company's own
    filings says the rule matches what the company did. It does not say
    the rule matches the law, and only an advisor closes that gap
    (O-03).

    Nothing here is applied. §14.2 puts statutory deadlines in Tier C.
    """
    contested = {d.obligation_id for d in disagreeing}
    candidates = []
    for row in (statutory_config or {}).get("obligations") or []:
        obligation_id = str(row.get("id") or "")
        if obligation_id in contested:
            continue
        if row.get("provenance") != "ceo_stated":
            continue
        record = observed.get(obligation_id)
        if record is None or len(record.periods) < minimum_periods:
            continue
        cadence = str(row.get("cadence") or "").lower()
        expected = STATED_CADENCE_PERIODS.get(cadence)
        if expected is None:
            continue
        # The count must be comparable: at least as fine as the cadence.
        # An annual folder cannot corroborate a monthly rule, because
        # twelve returns may be inside it.
        wanted = record.granularity
        if not can_speak_to(wanted, cadence):
            continue
        counts = record.interior_years(wanted)
        # A zero year is a year with no filing at all, and it is the
        # reason corroboration is refused rather than the reason it is
        # granted.
        if not counts or any(c != expected for c in counts.values()):
            continue
        candidates.append({
            "id": obligation_id,
            "from": "ceo_stated",
            "to": "document_evidenced",
            "evidence": (
                f"{len(record.periods)} distinct {wanted}ly period(s) "
                f"across {len(record.years)} year(s); ".replace(
                    "yearly", "annual")
                + ", ".join(f"{year}: {count}" for year, count
                            in sorted(counts.items()))
                + f" — matching the stated {cadence} cadence"),
            "still_open": (
                "O-03 is unaffected. The archive shows what the company "
                "did, not what the law requires."),
        })
    return candidates


# ---- input ------------------------------------------------------------

def paths_from_inventory(inventory_csv: Path) -> list[str]:
    """Reuse Stage B's file inventory rather than re-walking UB_ROOT.

    The scan already walked thirteen thousand documents once. Walking
    them again to ask a different question is not free on a laptop, and
    the inventory is the same read.
    """
    rows = []
    with Path(inventory_csv).open("r", encoding="utf-8", newline="") as f:
        for record in csv.DictReader(f):
            path = record.get("path")
            if path:
                rows.append(path)
    return rows


def walk_paths(ub_root: Path) -> list[str]:
    """Fallback when no inventory exists. Read-only (§1.13)."""
    out = []
    for path in Path(ub_root).rglob("*"):
        try:
            if path.is_file():
                out.append(str(path))
        except OSError:
            continue
    return out


# ---- the brief --------------------------------------------------------

def silent_obligations(statutory_config: dict | None,
                       observed: dict) -> list[str]:
    """Obligations the archive could not speak about, and why.

    "No disagreement" has two completely different causes: the archive
    agreed, or the archive could not be asked. A brief that printed the
    same sentence for both would be reporting a naming convention as
    evidence — which is the failure §1.1 exists to prevent, wearing the
    clothes of a clean result.
    """
    notes = []
    for row in (statutory_config or {}).get("obligations") or []:
        obligation_id = str(row.get("id") or "")
        cadence = str(row.get("cadence") or "").lower()
        expected = STATED_CADENCE_PERIODS.get(cadence)
        if expected is None:
            continue
        record = observed.get(obligation_id)
        if record is None:
            notes.append(f"{obligation_id}: no filing evidence matched at "
                         "all — nothing could be checked")
            continue
        kind = record.granularity
        if kind is None:
            notes.append(
                f"{obligation_id}: {record.documents} document(s), none "
                "naming a period — nothing could be counted")
            continue
        interior = record.interior_years(kind)
        if not interior:
            notes.append(
                f"{obligation_id}: {len(record.periods)} {kind}ly "
                f"period(s), but no year the archive covers in full — a "
                "partial year cannot contradict a cadence".replace(
                    "yearly", "annual"))
            continue
        if not can_speak_to(kind, cadence):
            notes.append(
                f"{obligation_id}: stated {cadence}, but the filings are "
                f"named by {kind}. One {kind} may contain several "
                f"filings, so the count cannot be compared — a coarser "
                "name hides how many returns are inside it.")
    return notes


def render_brief(statutory_config: dict | None,
                 observed: dict[str, Observed],
                 disagreeing: list[Disagreement],
                 candidates: list[dict],
                 source: str,
                 documents_considered: int,
                 today: date) -> str:
    names = {str(r.get("id")): str(r.get("name") or r.get("id"))
             for r in (statutory_config or {}).get("obligations") or []}
    lines = [
        f"# EXTRACTION BRIEF — {today:%d-%b-%Y}",
        "",
        "Execution order 18-Aug-2026, step 2. Read-only against the "
        "filing archive.",
        "",
        f"Source: {source} — {documents_considered} document path(s) "
        "considered, matched on filename and path only. No document was "
        "opened.",
        "",
        "**Nothing in this brief has been applied.** §14.2 puts statutory "
        "deadlines in Tier C: raised with evidence for a human decision, "
        "never changed by the system. Promoting any rule to "
        "`verified_by_advisor` without a named human is a §7 stop "
        "condition.",
        "",
        "**Observed is not due.** The archive shows when filings actually "
        "happened. That is a different fact from when they were due — a "
        "company that files on the 20th every month has a habit, not a "
        "rule, and may have been late every time.",
        "",
        "---",
        "",
        "## 1. DISAGREEMENTS — read these first",
        "",
    ]

    if not disagreeing:
        lines += [
            "None. No obligation shows more filed periods in a year than "
            "its stated cadence allows.",
            "",
            "**This is not a clean bill**, and the difference matters: "
            "\"the archive agreed\" and \"the archive could not be asked\" "
            "produce the same empty section. The list below says which "
            "obligations are which.",
            "",
        ]
        silent = silent_obligations(statutory_config, observed)
        if silent:
            lines += ["Could not be asked:", ""]
            lines += [f"- {note}" for note in silent]
            lines.append("")
    else:
        for item in disagreeing:
            lines += [
                f"### {item.obligation_id} — "
                f"{names.get(item.obligation_id, item.obligation_id)}",
                "",
                f"- **Stated:** {item.stated}",
                f"- **Observed:** {item.observed}",
                f"- **If the archive is right:** {item.consequence}",
                "",
            ]

    lines += ["---", "", "## 2. WHAT THE ARCHIVE HOLDS", ""]
    if not observed:
        lines += [
            "No filing evidence matched any obligation. That is a finding "
            "about this scan, not about the company: either the archive is "
            "not in the scanned tree, or filings are named in a way "
            "`filing-evidence.yaml` does not recognise. Both are worth "
            "checking before concluding anything.",
            "",
        ]
    for obligation_id in sorted(observed):
        record = observed[obligation_id]
        lines += [
            f"### {obligation_id} — {names.get(obligation_id, obligation_id)}",
            "",
            f"- {record.documents} document(s), "
            f"{len(record.periods)} distinct period(s)",
        ]
        monthly = record.per_year(MONTHLY)
        if monthly:
            lines.append(
                "- Monthly periods by year: "
                + ", ".join(f"{year}: {count}"
                            for year, count in sorted(monthly.items()))
                + "  \n  *(first and last years are usually partial and are "
                  "never used alone to contradict a stated rule)*")
        for kind, label in ((QUARTERLY, "Quarterly"), (ANNUAL, "Year-only")):
            counts = record.per_year(kind)
            if counts:
                lines.append(
                    f"- {label} periods by year: "
                    + ", ".join(f"{year}: {count}"
                                for year, count in sorted(counts.items())))
        if record.undated:
            lines.append(
                f"- {len(record.undated)} document(s) name no period and "
                "cannot be counted. A filing whose name does not say which "
                "period it covers is a document-control finding.")
        if record.documents > len(record.periods) * 2 and record.periods:
            lines.append(
                f"- {record.documents} documents across "
                f"{len(record.periods)} periods — roughly "
                f"{record.documents / len(record.periods):.1f} per period. "
                "Drafts, signed copies and scans of one filing are normal; "
                "counting documents rather than periods would have "
                "manufactured a cadence finding out of them.")
        lines.append("")

    lines += ["---", "", "## 3. PROPOSED PROVENANCE UPGRADES", ""]
    if not candidates:
        lines += [
            "None. No CEO-stated rule is corroborated by enough filed "
            "periods to be worth raising.",
            "",
            "The four rules currently alerting still rest entirely on the "
            "CEO's recollection (`ceo_stated`), and nothing in this scan "
            "changed that.",
            "",
        ]
    else:
        lines += [
            "Each of these is a rule the archive corroborates. "
            "`document_evidenced` says the rule matches what the company "
            "did; it does not say the rule matches the law. **O-03 stays "
            "open regardless** — only a named advisor closes that.",
            "",
        ]
        for candidate in candidates:
            lines += [
                f"- **{candidate['id']}**: {candidate['from']} → "
                f"{candidate['to']}",
                f"  - Evidence: {candidate['evidence']}",
                f"  - {candidate['still_open']}",
            ]
        lines.append("")

    lines += [
        "---",
        "",
        "## 4. WHAT THIS BRIEF CANNOT TELL YOU",
        "",
        "- **Whether a filing was on time.** The archive records that a "
        "return exists, not when it was submitted. File timestamps record "
        "when a copy was written, which is not the same thing and is "
        "destroyed by copying a folder.",
        "- **Whether a filing was correct.** Nothing was opened.",
        "- **Whether a filing is missing.** An absent period may mean a "
        "missed filing, a filing stored elsewhere, or a filing named in a "
        "way this scan does not recognise. Absence of evidence is reported "
        "as absence of evidence (§1.1).",
        "- **What the deadline is.** That is O-03, and it is answered by "
        "an advisor, not by a folder.",
        "",
    ]
    return "\n".join(lines)
