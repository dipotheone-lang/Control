"""Stage D and Stage H analysis over scan output — charter §6.

Offline: operates on the JSONL the Outlook scan writes, so it needs no
mailbox access and is fully testable.

Stage D — obligation inference. Recurring (sender, subject-template)
pairs are candidate obligations. Cadence is MEASURED from timestamps,
never assumed, and confidence follows the charter's own rule:
HIGH >=12 regular · MEDIUM 4-11 or irregular · LOW <4 or contradictory.

Stage H — response behaviour. External inbound matched against later
internal outbound in the same thread gives observed response times and,
more importantly, the unanswered set. This is Stage H item 2. Item 3
(commercial value) is not derivable from metadata and is reported as
absent rather than estimated (§1.1).
"""

import json
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

INTERNAL_DOMAIN = "ubcsis.com"

_PREFIXES = re.compile(r"(?i)^\s*((re|fw|fwd|رد|إعادة توجيه)\s*:\s*)+")
_DIGITS = re.compile(r"\d+")
_WS = re.compile(r"\s+")

# Cadence buckets by median gap in days.
_CADENCES = (
    (0.7, 1.6, "daily"),
    (5.0, 9.0, "weekly"),
    (11.0, 18.0, "fortnightly"),
    (25.0, 38.0, "monthly"),
    (80.0, 110.0, "quarterly"),
    (330.0, 400.0, "annual"),
)


def normalise_subject(subject: str) -> str:
    """Collapse a subject to its template: strip reply/forward prefixes
    and replace digits, so 'RE: Weekly Report - Week 32' and 'Weekly
    Report - Week 33' land on the same key."""
    text = _PREFIXES.sub("", subject or "")
    text = _DIGITS.sub("#", text)
    return _WS.sub(" ", text).strip().lower()


def is_internal(address: str) -> bool:
    return (address or "").strip().lower().endswith(f"@{INTERNAL_DOMAIN}")


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Stage D — obligation inference
# ---------------------------------------------------------------------------

@dataclass
class ObligationCandidate:
    sender: str
    subject_template: str
    occurrences: int
    first_seen: str
    last_seen: str
    median_gap_days: float | None
    cadence: str
    confidence: str
    regular: bool
    attachment_rate: float
    example_attachments: list[str] = field(default_factory=list)


def _cadence_for(gap: float | None) -> str:
    if gap is None:
        return "unknown"
    for low, high, name in _CADENCES:
        if low <= gap <= high:
            return name
    return f"irregular (~{gap:.0f}d)"


def infer_obligations(rows: list[dict], *, min_occurrences: int = 3
                      ) -> list[ObligationCandidate]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        subject = row.get("subject", "")
        if subject == "[REDACTED]":
            continue          # redacted mailboxes cannot be template-matched
        key = (row.get("sender", "").lower(), normalise_subject(subject))
        if not key[0] or not key[1]:
            continue
        groups[key].append(row)

    candidates: list[ObligationCandidate] = []
    for (sender, template), items in groups.items():
        if len(items) < min_occurrences:
            continue
        times = sorted(datetime.fromisoformat(i["received"]) for i in items)
        gaps = [(b - a).total_seconds() / 86400 for a, b in zip(times, times[1:])]
        median_gap = statistics.median(gaps) if gaps else None

        # "Regular" means the spread of gaps is small relative to the gap
        # itself - a series that arrives every 7±1 days, not 7±20.
        regular = False
        if len(gaps) >= 3 and median_gap:
            spread = statistics.pstdev(gaps)
            regular = spread <= max(2.0, median_gap * 0.5)

        if len(items) >= 12 and regular:
            confidence = "HIGH"
        elif len(items) >= 4:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        with_attachments = [i for i in items if i.get("attachments")]
        examples: list[str] = []
        for item in with_attachments[:3]:
            examples.extend(item["attachments"][:2])

        candidates.append(ObligationCandidate(
            sender=sender,
            subject_template=template,
            occurrences=len(items),
            first_seen=times[0].strftime("%d-%b-%Y"),
            last_seen=times[-1].strftime("%d-%b-%Y"),
            median_gap_days=round(median_gap, 1) if median_gap else None,
            cadence=_cadence_for(median_gap),
            confidence=confidence,
            regular=regular,
            attachment_rate=round(len(with_attachments) / len(items), 2),
            example_attachments=examples[:4],
        ))

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    candidates.sort(key=lambda c: (order[c.confidence], -c.occurrences))
    return candidates


# ---------------------------------------------------------------------------
# Stage H — response behaviour
# ---------------------------------------------------------------------------

@dataclass
class ThreadOutcome:
    template: str
    external_party: str
    inbound_at: str
    responded_at: str | None
    hours_to_respond: float | None
    answered: bool


@dataclass
class ResponseReport:
    threads: list[ThreadOutcome]
    answered: int
    unanswered: int
    median_hours: float | None
    slowest: list[ThreadOutcome]
    sent_items_present: bool


def analyse_responses(rows: list[dict], *, window_days: int = 30) -> ResponseReport:
    """Match external inbound to a later internal reply in the same thread."""
    sent_present = any(
        "sent" in str(row.get("folder", "")).lower() for row in rows
    )

    by_template: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        subject = row.get("subject", "")
        if subject == "[REDACTED]":
            continue
        by_template[normalise_subject(subject)].append(row)

    outcomes: list[ThreadOutcome] = []
    for template, items in by_template.items():
        items.sort(key=lambda r: r["received"])
        for index, row in enumerate(items):
            sender = row.get("sender", "").lower()
            if not sender or is_internal(sender):
                continue
            inbound_at = datetime.fromisoformat(row["received"])
            reply = None
            for later in items[index + 1:]:
                later_at = datetime.fromisoformat(later["received"])
                if later_at - inbound_at > timedelta(days=window_days):
                    break
                if is_internal(later.get("sender", "")):
                    reply = later_at
                    break
            hours = ((reply - inbound_at).total_seconds() / 3600) if reply else None
            outcomes.append(ThreadOutcome(
                template=template,
                external_party=sender,
                inbound_at=inbound_at.strftime("%d-%b-%Y %H:%M"),
                responded_at=reply.strftime("%d-%b-%Y %H:%M") if reply else None,
                hours_to_respond=round(hours, 1) if hours is not None else None,
                answered=reply is not None,
            ))

    answered = [o for o in outcomes if o.answered]
    unanswered = [o for o in outcomes if not o.answered]
    median = (round(statistics.median([o.hours_to_respond for o in answered]), 1)
              if answered else None)
    slowest = sorted(answered, key=lambda o: -(o.hours_to_respond or 0))[:10]

    return ResponseReport(
        threads=outcomes, answered=len(answered), unanswered=len(unanswered),
        median_hours=median, slowest=slowest, sent_items_present=sent_present,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def render_stage_d(candidates: list[ObligationCandidate], mailbox: str) -> str:
    lines = [
        f"# Stage D — candidate obligations from {mailbox}",
        "",
        "Cadence is measured from timestamps, not assumed. Confidence per §6:",
        "HIGH >=12 regular · MEDIUM 4-11 or irregular · LOW <4.",
        "",
        "**Nothing here is an obligation until the CEO approves the register (§6).**",
        "These are observations of what recurs, nothing more.",
        "",
        "| Confidence | Sender | Subject template | n | Cadence | First | Last | Attach % |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in candidates:
        template = c.subject_template[:60]
        lines.append(
            f"| {c.confidence} | {c.sender} | {template} | {c.occurrences} | "
            f"{c.cadence} | {c.first_seen} | {c.last_seen} | {c.attachment_rate:.0%} |"
        )
    if not candidates:
        lines.append("| — | — | no recurring pattern met the threshold | — | — | — | — | — |")
    lines += [
        "",
        "## Reading this",
        "",
        "- A HIGH-confidence weekly series with a high attachment rate is the "
        "shape of a controlled report; a LOW-confidence one may be ordinary "
        "correspondence that happens to repeat.",
        "- Absence of a pattern is not absence of an obligation: an obligation "
        "nobody has been meeting leaves no trace here. Those are found in the "
        "manuals (Stage C), not in the mailbox.",
        "",
    ]
    return "\n".join(lines)


def render_stage_h(report: ResponseReport, mailbox: str) -> str:
    total = report.answered + report.unanswered
    lines = [
        f"# Stage H — response behaviour, {mailbox}",
        "",
        f"- external messages examined: **{total}**",
        f"- answered within the window: **{report.answered}**",
        f"- no reply found: **{report.unanswered}**",
    ]
    if total:
        lines.append(f"- observed response rate: **{report.answered / total:.1%}**")
    if report.median_hours is not None:
        lines.append(f"- median time to first reply: **{report.median_hours} hours**")
    lines.append("")

    if not report.sent_items_present:
        lines += [
            "> **Sent Items was not in this scan.** Replies sent from the "
            "mailbox are therefore invisible, and every thread will look "
            "unanswered. Re-run the scan including Sent Items before treating "
            "the unanswered count as real (§1.1).",
            "",
        ]

    if report.slowest:
        lines += ["## Slowest observed responses", "",
                  "| External party | Subject template | Inbound | Hours |",
                  "|---|---|---|---|"]
        for o in report.slowest:
            lines.append(
                f"| {o.external_party} | {o.template[:50]} | {o.inbound_at} | "
                f"{o.hours_to_respond} |"
            )
        lines.append("")

    lines += [
        "## What this cannot answer",
        "",
        "- **Commercial value** in these threads (Stage H item 3) is not in "
        "metadata. It is reported as absent rather than estimated (§1.1).",
        "- A reply sent from a personal account, by phone, or in person is "
        "invisible here. 'No reply found' means exactly that — not 'no reply "
        "given' (§8.5 wording).",
        "",
    ]
    return "\n".join(lines)
