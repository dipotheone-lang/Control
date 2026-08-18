"""Cycle orchestrator — one sweep, in the §5.6 order: state first,
mailbox last, everything logged, everything idempotent.

The orchestrator wires the tested parts together and owns none of the
rules itself: classification (§9), attachment gauntlet (§5.4),
evaluation (§7), rendering (§7.5), enforcement planning (§8), and the
outbox gates (§10). Dependencies are injected — specs, tracked items,
and the transport — so the same cycle runs against MockTransport in
DRY_RUN rehearsal and against Graph later without change.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from . import HaltError
from .anomaly import SUPPRESSED, Flag, record_flag, s1_out_of_hours
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
from .hse import HseScope
from .outbox import Disposition, OutboundMessage, Outbox
from .render import correction_due, render_verdict_reply
from .startup import StartupReport
from .transport import MailTransport
from .watchdog import Watchdog

# §8 action kinds -> §10 gate kinds.
_ACTION_TO_GATE = {
    "ALERT": "CLASS12_ALERT",
    "PRE_REMINDER": "CLASS3_REMINDER",
    "DEADLINE": "CLASS3_REMINDER",
    "L1": "ESCALATION_L1_L2",
    "L2": "ESCALATION_L1_L2",
    "L3": "CEO_ESCALATION_L3",
    "PROCESS_FINDING": "CLASS3_REMINDER",
    "WATCHDOG_NOTICE": "WATCHDOG_NOTICE",
}

INTERNAL_DOMAIN = "ubcsis.com"


def _address(sender: str) -> str:
    """The bare address out of a `Display Name <addr>` header."""
    return sender.split("<")[-1].rstrip(">").strip().lower()


def _is_internal(sender: str) -> bool:
    return _address(sender).endswith("@" + INTERNAL_DOMAIN)


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
    # §8.5 external watchdog
    threads_opened: int = 0
    threads_closed_declared: int = 0
    threads_without_id: int = 0
    cc_compliance: dict = field(default_factory=dict)
    # §7.3 substantive signals, under the D-10 CEO flag budget
    flags_raised: int = 0
    flags_suppressed: int = 0
    # §5.2 period lock: submissions refused because the period they
    # belong to has already been reported on.
    locked_period_refusals: list[str] = field(default_factory=list)


def _raise_flag(conn, flag: Flag, report: CycleReport, budget: int | None,
                since: datetime | None, audit) -> None:
    """Record a §7.3 flag under the D-10 budget.

    Written either way. Over budget it is marked suppressed rather than
    dropped, so the weekly pack can say what was held back — a budget
    whose cost is invisible cannot be reviewed.
    """
    destination = record_flag(conn, flag, budget=budget, since=since)
    if destination == SUPPRESSED:
        report.flags_suppressed += 1
    else:
        report.flags_raised += 1
    audit.append("anomaly.flag", {"signal": flag.signal, "code": flag.code,
                                  "priority": flag.priority,
                                  "destination": destination})


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
    watchdog: Watchdog | None = None,
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
        # B5: the HSE split, applied only to HSE traffic (D-17, D-18).
        hse_scope=HseScope.from_config(startup.config.get("hse")),
        hse_senders={"hse@ubcsis.com"},
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
    known = outbox.known_dedupe_keys()

    # §7.3 S1 and the D-10 budget. Working hours stay unset unless the
    # CEO confirmed them (§8.3, O-11) — the detector checks that itself,
    # so an unconfirmed config edit cannot switch the signal on.
    sla = startup.config["sla"] or {}
    working_hours = (sla.get("working_calendar") or sla).get("working_hours")
    flag_budget = (startup.config["materiality"] or {}).get(
        "ceo_flag_budget_per_week")
    week_start = datetime.combine(today, datetime.min.time()) - timedelta(days=7)

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
                        restricted_basis=classification.restricted_basis,
                    )

                evaluation = evaluate(sub.spec, doc, enforcer.cal if enforcer
                                      else _default_cal())
                report.verdicts[fetched.message_id] = evaluation.verdict

                # §7.3 S1: substantive signals. These never change the
                # verdict and never appear in the submitter's reply —
                # they are recorded for the CEO alone. Metadata-only, so
                # they run on confidential items too (§12.1.3).
                flag = s1_out_of_hours(fetched.received_at, working_hours)
                if flag:
                    flag.subject_ref = f"{obligation_id} / {fetched.sender}"
                    _raise_flag(conn, flag, report, flag_budget, week_start,
                                audit)

                # Through `insert_submission`, not raw SQL: the period
                # lock (§5.2) lives in that helper, and a raw insert
                # walks straight past it.
                try:
                    insert_submission(conn, {
                        "obligation_id": obligation_id,
                        "verdict": (evaluation.verdict
                                    if not evaluation.verdict.startswith("RECEIVED")
                                    else None),
                        "timeliness": evaluation.timeliness,
                        "confidential": int(doc.confidential),
                        "source": "LIVE",
                        "source_email_id": fetched.message_id,
                        "submitted_by": fetched.sender,
                        "submitted_at": fetched.received_at.isoformat(),
                        "period": sub.period,
                    })
                except HaltError as e:
                    # A late entry into a reported period is a real
                    # event, not a reason to abandon the sweep (§13.2).
                    # It is not posted; it needs a CEO-approved
                    # correction and a reissued report revision, and
                    # that decision is raised rather than taken here.
                    report.locked_period_refusals.append(
                        f"{obligation_id} {sub.period}: {e}")
                    audit.append("submission.refused_locked_period", {
                        "obligation": obligation_id, "period": sub.period,
                        "message_id": fetched.message_id,
                    })
                    continue

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
                    content_classes=({doc.restricted_basis}
                                     if doc.restricted_basis else set()),
                ), known, report, audit)
                continue

            if watchdog is not None:
                # §8.5. A thread id is what lets a reply close the thing
                # it answers; without one from the transport, the message
                # is its own thread and can only ever close by an
                # explicit CLOSED declaration.
                thread = fetched.thread_id or fetched.message_id
                if not fetched.thread_id:
                    report.threads_without_id += 1

                if classification.category == "EXTERNAL_INBOUND":
                    # Which of the §8.5 categories this belongs to is not
                    # decidable from metadata, and deciding it from the
                    # body is not permitted here. "unclassified" is the
                    # charter's own catch-all row — owner COO, backup CEO
                    # — so nothing is dropped while it stays uncategorised.
                    watchdog.register_inbound(
                        thread, "unclassified", fetched.received_at)
                    report.threads_opened += 1
                elif _is_internal(fetched.sender):
                    first = fetched.first_line.strip().upper()
                    if first.startswith("CLOSED"):
                        # §8.5: the owner declaring it handled. Logged
                        # with the declarant, because a declared close and
                        # an observed reply are different evidence.
                        watchdog.declare_closed(
                            thread, _address(fetched.sender), fetched.received_at)
                        report.threads_closed_declared += 1
                    else:
                        # A colleague's reply, visible only because
                        # control@ was copied (§3.1a Option A).
                        watchdog.observe_reply(thread, fetched.received_at)

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

        # ---- external watchdog (§8.5) ----------------------------------
        # After enforcement, so a breach notice reflects the replies this
        # same sweep observed. Notices go only to the internal owner and,
        # after the final SLA, their manager — never to the external
        # party (§8.5).
        if watchdog is not None:
            for action in watchdog.check(datetime.combine(
                    today, datetime.min.time().replace(hour=23, minute=59))):
                _dispatch(outbox, transport, _action_to_message(action), known,
                          report, audit)
            report.cc_compliance = watchdog.cc_compliance()
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
