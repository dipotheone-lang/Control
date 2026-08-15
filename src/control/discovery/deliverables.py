"""Phase 0 deliverable generation — charter §6 Stage J.

Turns scan and analysis output into the documents the CEO gate needs,
so the human step is running one command, not assembling reports.

Every generated document states its own limits. A deliverable that
looks complete but rests on partial evidence is worse than one that
says what it could not see (§1.1).
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .analyse import (
    ObligationCandidate,
    ResponseReport,
    analyse_responses,
    infer_obligations,
    load_rows,
)

# §12.1.1 default confidential list. Domains are guessed from the client
# names and MUST be confirmed - a wrong guess here is a scope error.
KNOWN_CLIENT_HINTS = {
    "siemens": "Siemens Energy",
    "saint-gobain": "Saint-Gobain",
    "saintgobain": "Saint-Gobain",
    "knauf": "KNAUF",
    "galaxy": "Galaxy Chemicals",
    "canalsugar": "Canal Sugar",
    "canal-sugar": "Canal Sugar",
    "sukari": "Sukari Gold Mines",
    "airliquide": "Air Liquide",
    "air-liquide": "Air Liquide",
}


@dataclass
class MailboxResult:
    mailbox: str
    rows: list
    candidates: list
    responses: ResponseReport


def build_results(discovery_dir: Path, min_occurrences: int = 3) -> list[MailboxResult]:
    results = []
    for scan in sorted(Path(discovery_dir).glob("outlook-scan-*.jsonl")):
        rows = load_rows(scan)
        if not rows:
            continue
        results.append(MailboxResult(
            mailbox=rows[0].get("mailbox", scan.stem),
            rows=rows,
            candidates=infer_obligations(rows, min_occurrences=min_occurrences),
            responses=analyse_responses(rows),
        ))
    return results


def _external_domains(results: list[MailboxResult]) -> Counter:
    domains: Counter = Counter()
    for result in results:
        for row in result.rows:
            sender = (row.get("sender") or "").lower()
            if "@" not in sender:
                continue
            domain = sender.rsplit("@", 1)[-1]
            if domain.endswith("ubcsis.com"):
                continue
            domains[domain] += 1
    return domains


def write_confidential_scope(results: list[MailboxResult], out_dir: Path) -> Path:
    """CONFIDENTIAL-SCOPE.md — Stage I, decision O-04."""
    domains = _external_domains(results)
    matched: list[tuple[str, str, int]] = []
    unmatched: list[tuple[str, int]] = []
    for domain, count in domains.most_common():
        client = next((name for hint, name in KNOWN_CLIENT_HINTS.items()
                       if hint in domain), None)
        if client:
            matched.append((domain, client, count))
        else:
            unmatched.append((domain, count))

    lines = [
        "# CONFIDENTIAL-SCOPE — proposed classifications",
        "",
        f"Generated {date.today():%d-%b-%Y} from observed correspondence.",
        "",
        "Decision **O-04**: the CEO confirms every classification below.",
        "Per §12.1.1 the asymmetry is deliberate — a misclassification toward",
        "confidential costs a check; away from it costs a client relationship.",
        "",
        "## Domains matching a client on the §12.1.1 list",
        "",
        "| Domain | Client | Messages seen |",
        "|---|---|---|",
    ]
    lines += [f"| {d} | {c} | {n} |" for d, c, n in matched] or \
             ["| — | none matched | — |"]
    lines += [
        "",
        "## Other external domains — classification required",
        "",
        "Listed by volume. Anything genuinely uncertain is confidential by",
        "default until the CEO says otherwise (§12.1.1).",
        "",
        "| Domain | Messages seen | Proposed |",
        "|---|---|---|",
    ]
    for domain, count in unmatched[:40]:
        lines.append(f"| {domain} | {count} | CONFIDENTIAL (default, unconfirmed) |")
    if len(unmatched) > 40:
        lines.append(f"| … {len(unmatched) - 40} further domains | | see scan output |")
    lines += [
        "",
        "## Limits of this proposal",
        "",
        "- Domain matching is by name fragment, not by contract. A client "
        "corresponding from an agent, a group domain or a personal address "
        "will not appear here.",
        "- Project-to-client mapping (§12.1.1 second test) is not derivable "
        "from mail metadata and must come from the contracts in Stage C.",
        "- Absence from this list is not evidence a client is unrestricted.",
        "",
    ]
    path = Path(out_dir) / "CONFIDENTIAL-SCOPE.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_discovery_report(results: list[MailboxResult], out_dir: Path,
                           gaps: list[str] | None = None) -> Path:
    """DISCOVERY-REPORT.md — leads with the ten things the CEO most needs
    to know (§6 Stage J item 1)."""
    gaps = gaps or []
    total_messages = sum(len(r.rows) for r in results)
    all_candidates: list[ObligationCandidate] = [
        c for r in results for c in r.candidates
    ]
    high = [c for c in all_candidates if c.confidence == "HIGH"]
    medium = [c for c in all_candidates if c.confidence == "MEDIUM"]
    domains = _external_domains(results)

    answered = sum(r.responses.answered for r in results)
    unanswered = sum(r.responses.unanswered for r in results)
    external_total = answered + unanswered
    missing_sent = [r.mailbox for r in results if not r.responses.sent_items_present]

    copied = sum(
        1 for r in results for row in r.rows
        if "control@" in f"{row.get('to','')};{row.get('cc','')}".lower()
    )

    lines = [
        "# DISCOVERY REPORT — Phase 0",
        "",
        f"Generated {date.today():%d-%b-%Y}. Metadata only: no message body was "
        "read (§12.1.2).",
        "",
        "## The ten things you most need to know",
        "",
        f"1. **{total_messages:,} messages** were examined across "
        f"{len(results)} mailbox(es).",
        f"2. **{len(high)} high-confidence recurring patterns** look like "
        f"controlled obligations; {len(medium)} more are plausible. These are "
        "candidates, not a register — approving the register ends Phase 0.",
        f"3. **{len(domains)} distinct external domains** appear in the "
        "correspondence. Each needs a confidentiality classification (O-04).",
        f"4. **{copied:,} messages** were copied to control@. Read this against "
        "when control@ went live before drawing conclusions about CC "
        "discipline (O-05).",
    ]
    if external_total:
        lines.append(
            f"5. **{unanswered:,} of {external_total:,} external messages** show "
            f"no reply in the scanned folders "
            f"({unanswered / external_total:.0%}). "
            + ("This figure is unreliable: Sent Items was missing for "
               f"{', '.join(missing_sent)}." if missing_sent
               else "Sent Items was scanned, so this is a real signal.")
        )
    else:
        lines.append("5. No external correspondence was observed — verify the "
                     "scan covered the right folders before accepting that.")

    lines += [
        "6. **Nothing in this report is an obligation, a finding about a "
        "person, or a decision.** It is what the mailboxes contain.",
        "7. **Statutory deadlines are absent from this evidence.** They live "
        "in law and with the tax advisor, not in mail (O-03).",
        "8. **Contract dates, guarantees and accreditations** are not "
        "derivable from metadata. `COMMERCIAL-EXPOSURE.md` — the charter's "
        "highest-value output — needs the contracts themselves (Stage C).",
        "9. **The authority matrix is still empty** (O-02). Until it is "
        "populated the segregation-of-duties controls default to itemising "
        "every commitment (§3.2).",
        f"10. **{len(gaps)} source(s) could not be read** and are listed as "
        "gaps below. A gap is a finding, not an omission (§1.1).",
        "",
        "## Candidate obligations by mailbox",
        "",
    ]

    for result in results:
        lines.append(f"### {result.mailbox} — {len(result.rows):,} messages")
        lines.append("")
        top = [c for c in result.candidates if c.confidence in ("HIGH", "MEDIUM")][:12]
        if not top:
            lines += ["No recurring pattern met the threshold.", ""]
            continue
        lines += ["| Confidence | Cadence | n | Sender | Subject template |",
                  "|---|---|---|---|---|"]
        for c in top:
            lines.append(
                f"| {c.confidence} | {c.cadence} | {c.occurrences} | {c.sender} | "
                f"{c.subject_template[:50]} |"
            )
        lines.append("")

    lines += ["## Gaps and limitations", ""]
    lines += [f"- {g}" for g in gaps] or ["- None recorded."]
    lines += [
        "",
        "- Mailboxes absent from the Outlook profile were not scanned and are "
        "not represented here.",
        "- An obligation nobody has been meeting leaves no trace in a mailbox. "
        "Those are found in the manuals, not here.",
        "",
        "## What must happen before Phase 0 closes (§6)",
        "",
        "- **O-01** confirm the reporting lines marked ⚠ in §3",
        "- **O-02** approval thresholds and delegated limits → `authority.yaml`",
        "- **O-03** statutory calendar verified with the tax advisor",
        "- **O-04** confirm the classifications in `CONFIDENTIAL-SCOPE.md`",
        "- **O-05** the shared-mailbox decision, on measured evidence",
        "- **O-09** confirm `UB_ROOT` so the folder inventory can run",
        "",
    ]
    path = Path(out_dir) / "DISCOVERY-REPORT.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_paste_summary(results: list[MailboxResult], out_dir: Path,
                        gaps: list[str] | None = None) -> Path:
    """A short digest to hand back for interpretation."""
    gaps = gaps or []
    lines = ["PHASE 0 SUMMARY", "=" * 40]
    for result in results:
        high = sum(1 for c in result.candidates if c.confidence == "HIGH")
        medium = sum(1 for c in result.candidates if c.confidence == "MEDIUM")
        dates = [row["received"][:10] for row in result.rows if row.get("received")]
        lines += [
            "",
            f"{result.mailbox}",
            f"  messages: {len(result.rows):,}",
            f"  range: {min(dates) if dates else 'n/a'} to {max(dates) if dates else 'n/a'}",
            f"  candidates: {high} HIGH, {medium} MEDIUM",
            f"  external answered/unanswered: {result.responses.answered}/"
            f"{result.responses.unanswered}",
            f"  sent items scanned: {'yes' if result.responses.sent_items_present else 'NO'}",
        ]
        for c in result.candidates[:6]:
            lines.append(f"    [{c.confidence}] {c.cadence} n={c.occurrences} "
                         f"{c.sender} :: {c.subject_template[:45]}")
    domains = _external_domains(results)
    lines += ["", f"external domains: {len(domains)}",
              "top: " + ", ".join(f"{d}({n})" for d, n in domains.most_common(10))]
    if gaps:
        lines += ["", "GAPS:"] + [f"  - {g}" for g in gaps]
    path = Path(out_dir) / "PHASE0-SUMMARY.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
