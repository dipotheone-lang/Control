"""§9 classification over Phase 0 scan output.

The §9 classifier consumes InboundMessage objects that the mail
transport builds. Discovery has no transport — it has the metadata
JSONL from Stage A. Running the classifier over that answers a Phase 0
question the scan alone does not: what *kinds* of mail arrive, in what
proportion, in which mailbox.

It answers it partially, and the partiality is the point. Metadata
carries no message body, so every signal the charter locates in a body
is structurally silent here. Those silences are counted and named in
the output rather than left looking like zeros (§1.1): a category
reported as 0 because it cannot fire is a filled gap, not a finding.

Nothing here reads a body, so the pass stays inside §12.1.2 for
client-confidential material without needing to classify first.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..classify import Classifier, InboundMessage

# Categories that cannot be produced from metadata alone. Reported as
# structurally unavailable, never as an observed count of zero.
BODY_DEPENDENT = {
    "DISPUTE": "the marker is the first line of the body (§8.4)",
    "REPLY_TO_CONTROL": "needs thread position, which the scan does not record",
}


@dataclass
class FlaggedMessage:
    mailbox: str
    received: str
    sender: str
    subject: str
    category: str
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class ClassifyReport:
    rows: int = 0
    by_category: Counter = field(default_factory=Counter)
    by_mailbox: dict = field(default_factory=dict)      # mailbox -> Counter
    security_events: list = field(default_factory=list)  # FlaggedMessage
    confidential: int = 0
    redacted_subjects: int = 0
    unparseable_senders: int = 0
    limitations: list = field(default_factory=list)


def build_classifier(config) -> tuple[Classifier, list[str]]:
    """Assemble the §9 classifier from operative config, and report what
    is missing from it. An empty input is not a neutral default — it
    silences a whole category, and that has to be said out loud."""
    limitations: list[str] = []

    roster = {
        p["email"].lower() for p in config["people"].get("people", [])
        if p.get("email")
    }

    clients = config["confidential"].get("confidential_clients") or []
    confidential_domains = {
        str(d).lower() for client in clients for d in (client.get("domains") or [])
    }
    if clients and not confidential_domains:
        limitations.append(
            f"confidential.yaml lists {len(clients)} clients with no domains "
            "populated (Stage I / decision O-04 open). Confidential marking by "
            "sender domain cannot fire, and the near-miss reference set is "
            "ubcsis.com alone — so S1 look-alike detection is far narrower "
            "here than it will be in a live cycle."
        )

    obligations = config["obligations"].get("obligations") or []
    forms = {
        str(o["form"]): str(o["id"]) for o in obligations
        if o.get("form") and o.get("id")
    }
    if not forms:
        limitations.append(
            "obligations.yaml is empty by design until the Phase 0 register is "
            "approved (§6). OBLIGATION_SUBMISSION therefore cannot be produced: "
            "every internal message carrying an attachment falls to "
            "UNSCHEDULED_SUBMISSION. That split is an artefact of an unapproved "
            "register, not an observation about how people submit."
        )

    classifier = Classifier(
        roster_emails=roster,
        obligation_forms=forms,
        confidential_domains=confidential_domains,
        known_domains=confidential_domains,
    )
    return classifier, limitations


def classify_rows(rows, classifier: Classifier, *, mailbox: str = "") -> ClassifyReport:
    report = ClassifyReport()
    for row in rows:
        subject = str(row.get("subject") or "")
        box = str(row.get("mailbox") or mailbox)
        if subject == "[REDACTED]":
            report.redacted_subjects += 1

        result = classifier.classify(InboundMessage(
            sender=str(row.get("sender") or ""),
            to=str(row.get("to") or ""),
            cc=str(row.get("cc") or ""),
            subject=subject,
            # Body is not in the scan and is never read here (§12.1.2).
            first_line="",
            attachments=list(row.get("attachments") or []),
            in_reply_to_control=False,
        ))

        report.rows += 1
        report.by_category[result.category] += 1
        report.by_mailbox.setdefault(box, Counter())[result.category] += 1
        if result.confidential:
            report.confidential += 1
        if any("unparseable sender" in f for f in result.flags):
            report.unparseable_senders += 1
        if result.security_event:
            report.security_events.append(FlaggedMessage(
                mailbox=box,
                received=str(row.get("received") or ""),
                sender=str(row.get("sender") or ""),
                subject=subject,
                category=result.category,
                reasons=list(result.reasons),
                flags=list(result.flags),
            ))
    return report


def merge(reports: list[ClassifyReport]) -> ClassifyReport:
    merged = ClassifyReport()
    for r in reports:
        merged.rows += r.rows
        merged.by_category.update(r.by_category)
        for box, counts in r.by_mailbox.items():
            merged.by_mailbox.setdefault(box, Counter()).update(counts)
        merged.security_events.extend(r.security_events)
        merged.confidential += r.confidential
        merged.redacted_subjects += r.redacted_subjects
        merged.unparseable_senders += r.unparseable_senders
        for note in r.limitations:
            if note not in merged.limitations:
                merged.limitations.append(note)
    return merged


def render(report: ClassifyReport) -> str:
    lines = [
        "# §9 classification profile — Phase 0 scan output",
        "",
        "Metadata only: no message body was read (§12.1.2). Every row comes "
        "from the Stage A scan, so this pass adds no access and no new "
        "personal-data footprint beyond what the scan already holds.",
        "",
        f"Messages classified: **{report.rows}**",
        "",
        "## Read this first — what this pass cannot see",
        "",
        "The §9 classifier is built for live inbound mail, where it has the "
        "message body and the thread position. Here it has neither. The "
        "following categories and signals are **structurally unavailable**, "
        "not observed to be absent:",
        "",
    ]
    for category, why in BODY_DEPENDENT.items():
        lines.append(f"- **{category}** — {why}. Cannot appear below at any count.")
    lines += [
        "- **Bank-detail change cues (§7.3 S1)** — evaluated against the subject "
        "line only. The cue normally lives in the body, so under-detection here "
        "is expected and says nothing about the real rate.",
        "- **Embedded-instruction cues (§13.2)** — likewise subject-only.",
        "",
    ]
    if report.redacted_subjects:
        lines += [
            f"- **{report.redacted_subjects} messages carry redacted subjects** "
            "(hr@ mailboxes, §12.2). For those, every subject-based signal above "
            "is silent by design.",
            "",
        ]
    for note in report.limitations:
        lines.append(f"- {note}")
        lines.append("")

    lines += [
        "A count of zero against a category named above is a property of this "
        "input, not a finding about the company's mail. Do not carry these "
        "figures into a management report without this paragraph attached.",
        "",
        "## Categories observed",
        "",
        "| Category | Messages | Share |",
        "|---|---:|---:|",
    ]
    for category, n in report.by_category.most_common():
        share = f"{n / report.rows:.1%}" if report.rows else "n/a"
        lines.append(f"| {category} | {n} | {share} |")
    for category in BODY_DEPENDENT:
        if category not in report.by_category:
            lines.append(f"| {category} | — | not detectable from metadata |")
    lines.append("")

    lines += [
        f"Marked client-confidential: **{report.confidential}** "
        f"(§12.1.1 domain rule)",
        f"Unparseable sender addresses: **{report.unparseable_senders}**",
        "",
        "## By mailbox",
        "",
    ]
    categories = [c for c, _ in report.by_category.most_common()]
    lines.append("| Mailbox | " + " | ".join(categories) + " | Total |")
    lines.append("|---" * (len(categories) + 2) + "|")
    for box in sorted(report.by_mailbox):
        counts = report.by_mailbox[box]
        total = sum(counts.values())
        cells = " | ".join(str(counts.get(c, 0)) for c in categories)
        lines.append(f"| {box} | {cells} | {total} |")
    lines.append("")

    lines += ["## Security events (§7.3 S1, §13.2)", ""]
    if not report.security_events:
        lines += [
            "None raised on this input. Given the silenced signals listed above, "
            "read that as *nothing surfaced within a narrow detection window*, "
            "not as an all-clear.",
            "",
        ]
    else:
        lines += [
            f"**{len(report.security_events)}** message(s) raised a security "
            "event. Each is a factual signal for human judgement, never an "
            "accusation (§7.3). Control has taken no action on any of them and "
            "never acts on a bank-detail change (§10).",
            "",
        ]
        for flag in report.security_events:
            lines += [
                f"### {flag.received[:10] or 'date unknown'} — {flag.category}",
                "",
                f"- mailbox: `{flag.mailbox}`",
                f"- sender: `{flag.sender}`",
                f"- subject: {flag.subject or '(none)'}",
            ]
            for reason in flag.reasons:
                lines.append(f"- reason: {reason}")
            for note in flag.flags:
                lines.append(f"- flag: {note}")
            lines.append("")

    lines += [
        "## What this is good for",
        "",
        "- the shape of inbound traffic per mailbox, as §9 would label it",
        "- a first look at look-alike sender domains, within the narrow "
        "reference set currently configured",
        "- evidence that the classifier runs over real corporate mail before "
        "any live cycle depends on it",
        "",
        "## What it is not evidence for",
        "",
        "- dispute volume, reply behaviour, or submission compliance",
        "- the real rate of any body-borne fraud signal",
        "- anything about individuals: this counts messages, not people (§1.6)",
        "",
    ]
    return "\n".join(lines)


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
