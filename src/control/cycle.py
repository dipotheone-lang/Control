"""Cycle orchestrator — one sweep, in the §5.6 order: state first,
mailbox last, everything logged, everything idempotent.

The orchestrator wires the tested parts together and owns none of the
rules itself: classification (§9), attachment gauntlet (§5.4),
evaluation (§7), rendering (§7.5), enforcement planning (§8), and the
outbox gates (§10). Dependencies are injected — specs, tracked items,
and the transport — so the same cycle runs against MockTransport in
DRY_RUN rehearsal and against Graph later without change.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .attachments import build_submission_doc, quarantine, validate_attachment
from .classify import Classifier, InboundMessage
from .config import known_addresses
from .db import connect, insert_submission
from .discovery.classify_worksheet import (
    confidential_domains as _confidential_domains,
)
from .discovery.classify_worksheet import known_domains as _known_domains
from .enforce import Absence, Action, Enforcer, TrackedItem
from .evaluate import ObligationSpec, evaluate
from .outbox import Disposition, Outbox, OutboundMessage
from .render import correction_due, render_verdict_reply
from .startup import StartupReport
from .transport import FetchedMessage, MailTransport

# §8 action kinds -> §10 gate kinds.
_ACTION_TO_GATE = {
    "ALERT": "CLASS12_ALERT",
    "PRE_REMINDER": "CLASS3_REMINDER",
    "DEADLINE": "CLASS3_REMINDER",
    "L1": "ESCALATION_L1_L2",
    "L2": "ESCALATION_L1_L2",
    "L3": "CEO_ESCALATION_L3",
    "PROCESS_FINDING": "CLASS3_REMINDER",
}


@dataclass
class SubmissionSpec:
    """Everything the cycle needs to judge one obligation's submissions."""
    spec: ObligationSpec
    mapping: dict[str, str]
    surname: str
    period: str


@dataclass
class Class3State:
    submitted: bool = False
    dispute_active: bool = False
    absence: Absence | None = None
    reliable: bool = False


@dataclass
class CycleReport:
    processed: int = 0
    verdicts: dict = field(default_factory=dict)          # message_id -> verdict
    quarantined: list[str] = field(default_factory=list)
    security_events: list[str] = field(default_factory=list)
    sent: list[str] = field(default_factory=list)          # dedupe keys sent
    drafted: list[str] = field(default_factory=list)       # draft ids written
    skipped_duplicates: int = 0


def _known_dedupe_keys(outbox: Outbox) -> set[str]:
    """Idempotency source (§1.10): keys already sent or already pending."""
    keys: set[str] = set()
    for folder in (outbox.sent_dir, outbox.pending):
        for path in folder.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            key = record.get("dedupe_key")
            if key:
                keys.add(key)
    return keys


def _dispatch(outbox: Outbox, transport: MailTransport, msg: OutboundMessage,
              known: set[str], report: CycleReport, audit) -> None:
    disposition: Disposition = outbox.submit(msg, already_sent=known)
    if disposition.action == "SKIPPED_DUPLICATE":
        report.skipped_duplicates += 1
        return
    if disposition.action == "SEND":
        message_id = transport.send(
            disposition.message.recipients, disposition.message.cc,
            disposition.message.subject, disposition.message.body,
        )
        outbox.mark_sent(disposition.message, message_id)
        if msg.dedupe_key:
            known.add(msg.dedupe_key)
            report.sent.append(msg.dedupe_key)
        audit.append("outbox.sent", {"kind": msg.kind, "key": msg.dedupe_key,
                                     "message_id": message_id})
    else:  # DRAFT
        if msg.dedupe_key:
            known.add(msg.dedupe_key)
        report.drafted.append(disposition.draft_id)
        audit.append("outbox.drafted", {"kind": msg.kind, "key": msg.dedupe_key,
                                        "draft_id": disposition.draft_id})


def run_cycle(
    startup: StartupReport,
    transport: MailTransport,
    control_root: Path,
    *,
    specs: dict[str, SubmissionSpec],
    tracked_items: list[TrackedItem] | None = None,
    class3_state: dict[str, Class3State] | None = None,
    enforcer: Enforcer | None = None,
    today: date | None = None,
    ceo: str,
    cfo: str,
    coo: str | None = None,
) -> CycleReport:
    control_root = Path(control_root)
    audit = startup.audit
    report = CycleReport()
    today = today or datetime.now().date()

    # All three lists in people.yaml, not just `people:` — vacancies
    # carry live traffic and special addresses are recognised senders
    # (§13.2). Leavers are excluded on purpose.
    roster_emails = known_addresses(startup.config["people"])
    # Per-client NDA lists unioned with the O-04 worksheet decisions.
    confidential_domains = _confidential_domains(startup.config["confidential"])
    obligation_forms = {
        s.spec.form_code: obligation_id for obligation_id, s in specs.items()
    }
    classifier = Classifier(
        roster_emails=roster_emails,
        obligation_forms=obligation_forms,
        confidential_domains=confidential_domains,
        # Wider than the confidential set on purpose: a spoofed supplier
        # is the §7.3 S1 vector, and suppliers are not under NDA.
        known_domains=_known_domains(startup.config["confidential"]),
    )
    conn = connect(startup.db_path)
    # §3.3, extended to draft release: the COO deputises only while the
    # CEO's absence is REGISTERED. Read from the register, never from a
    # flag the deputy could set.
    ceo_absent = bool(conn.execute(
        "SELECT 1 FROM absence WHERE email = ? AND from_date <= ?"
        " AND to_date >= ? LIMIT 1",
        (ceo, today.isoformat(), today.isoformat()),
    ).fetchone())
    outbox = Outbox(control_root, startup.state.run_mode, ceo=ceo,
                    coo=coo, ceo_absent=ceo_absent)
    known = _known_dedupe_keys(outbox)

    try:
        # ---- inbound ----------------------------------------------------
        processed_ids: list[str] = []
        for fetched in transport.fetch_unprocessed():
            report.processed += 1
            processed_ids.append(fetched.message_id)
            classification = classifier.classify(InboundMessage(
                sender=fetched.sender, to=fetched.to, cc=fetched.cc,
                subject=fetched.subject, first_line=fetched.first_line,
                attachments=[name for name, _ in fetched.attachments],
                in_reply_to_control=fetched.in_reply_to_control,
            ))
            audit.append("classify", {
                "message_id": fetched.message_id,
                "category": classification.category,
                "confidential": classification.confidential,
                "flags": classification.flags,
            })

            if classification.security_event:
                report.security_events.append(fetched.message_id)

            if classification.category == "SUSPECTED_FRAUD":
                # §9: CEO/CFO only, never a reply to the sender.
                _dispatch(outbox, transport, OutboundMessage(
                    kind="FRAUD_FLAG",
                    subject=f"[CONTROL] SUSPECTED FRAUD SIGNAL — {fetched.subject[:60]}",
                    body=(
                        "Factual flag, not an accusation (§7.3 S1).\n"
                        f"Message: {fetched.message_id}\nSender: {fetched.sender}\n"
                        f"Subject: {fetched.subject}\n"
                        f"Reasons: {'; '.join(classification.reasons)}\n"
                        "No action has been taken. Never act on a bank-detail "
                        "change without callback verification on a known number."
                    ),
                    recipients=[ceo, cfo],
                    dedupe_key=f"FRAUD:{fetched.message_id}",
                    rationale="S1 fraud signal to CEO/CFO",
                    content_classes={"SUSPECTED_FRAUD", "S1"},
                ), known, report, audit)
                continue

            if classification.category == "DISPUTE":
                conn.execute(
                    "INSERT INTO disputes (raised_by, raised_at, state, source,"
                    " source_email_id) VALUES (?, ?, 'PENDING', 'LIVE', ?)",
                    (fetched.sender, fetched.received_at.isoformat(), fetched.message_id),
                )
                conn.commit()
                audit.append("dispute.logged", {"message_id": fetched.message_id})
                continue

            if classification.category == "OBLIGATION_SUBMISSION":
                obligation_id = next(
                    (oid for code, oid in obligation_forms.items()
                     if any(code.lower() in n.lower() for n, _ in fetched.attachments)),
                    None,
                )
                sub = specs[obligation_id]
                filename, content = fetched.attachments[0]

                validation = validate_attachment(filename, content)
                if not validation.ok:
                    target = quarantine(filename, content, validation.reason,
                                        control_root / "data" / "quarantine")
                    report.quarantined.append(str(target))
                    audit.append("attachment.quarantined",
                                 {"file": filename, "reason": validation.reason})
                    # No usable attachment: evaluation yields NOT_ACCEPTED.
                    doc = build_submission_doc(filename, None, fetched.received_at)
                else:
                    doc = build_submission_doc(
                        filename, content, fetched.received_at,
                        mapping=sub.mapping,
                        form_code=sub.spec.form_code,
                        revision=sub.spec.current_revision,
                        confidential=classification.confidential,
                    )

                evaluation = evaluate(sub.spec, doc, enforcer.cal if enforcer
                                      else _default_cal())
                report.verdicts[fetched.message_id] = evaluation.verdict

                conn.execute(
                    "INSERT INTO submissions (obligation_id, verdict, timeliness,"
                    " confidential, source, source_email_id, submitted_by,"
                    " submitted_at, period) VALUES (?, ?, ?, ?, 'LIVE', ?, ?, ?, ?)",
                    (obligation_id,
                     evaluation.verdict if not evaluation.verdict.startswith("RECEIVED")
                     else None,
                     evaluation.timeliness, int(doc.confidential),
                     fetched.message_id, fetched.sender,
                     fetched.received_at.isoformat(), sub.period),
                )
                conn.commit()
                audit.append("submission.evaluated", {
                    "obligation": obligation_id, "verdict": evaluation.verdict,
                    "message_id": fetched.message_id,
                })

                cal = enforcer.cal if enforcer else _default_cal()
                reply = render_verdict_reply(
                    evaluation, sub.spec, sub.surname, sub.period,
                    fetched.received_at,
                    correction_due_at=correction_due(fetched.received_at, cal)
                    if evaluation.verdict in ("RETURNED_FOR_REVISION", "NOT_ACCEPTED")
                    else None,
                )
                _dispatch(outbox, transport, OutboundMessage(
                    kind="VERDICT_REPLY",
                    subject=reply["subject"],
                    body=reply["body"],
                    recipients=[fetched.sender.split("<")[-1].rstrip(">")],
                    dedupe_key=f"{obligation_id}:VERDICT:{sub.period}:{fetched.message_id}",
                    rationale=f"Verdict {evaluation.verdict} on {obligation_id} {sub.period}",
                    content_classes={"CONFIDENTIAL_CLIENT"} if doc.confidential else set(),
                ), known, report, audit)
                continue

            # Everything else is logged, not acted on, in this version.
            audit.append("inbound.logged", {"message_id": fetched.message_id,
                                            "category": classification.category})

        # Mark the sweep's messages read only after the whole batch
        # processed — part of processing, per §9.
        for message_id in processed_ids:
            try:
                transport.mark_processed(message_id)
            except NotImplementedError:
                break

        # ---- enforcement planning --------------------------------------
        if enforcer and tracked_items:
            state = class3_state or {}
            for item in tracked_items:
                if item.obligation_class in (1, 2):
                    actions = enforcer.plan_class12(item, today)
                elif item.obligation_class == 3:
                    s = state.get(item.item_id, Class3State())
                    actions = enforcer.plan_class3(
                        item, today, submitted=s.submitted,
                        dispute_active=s.dispute_active,
                        absence=s.absence, reliable=s.reliable,
                    )
                else:
                    actions = enforcer.plan_class4(item, today)
                for action in actions:
                    _dispatch(outbox, transport, _action_to_message(action), known,
                              report, audit)
    finally:
        conn.close()

    audit.append("cycle.complete", {
        "processed": report.processed,
        "sent": len(report.sent), "drafted": len(report.drafted),
        "quarantined": len(report.quarantined),
        "security_events": len(report.security_events),
    })
    return report


def _action_to_message(action: Action) -> OutboundMessage:
    return OutboundMessage(
        kind=_ACTION_TO_GATE[action.kind],
        subject=f"[CONTROL] {action.kind} — {action.note[:80]}",
        body=action.note,
        recipients=action.recipients,
        cc=action.cc,
        dedupe_key=action.dedupe_key,
        rationale=action.note[:100],
    )


def _default_cal():
    from .calendar import WorkingCalendar
    return WorkingCalendar()
