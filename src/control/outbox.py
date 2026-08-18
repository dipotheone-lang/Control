"""Outbox and approval gates — charter §10, decision D-04.

The gate table is code, not convention: every outbound message passes
through decide() and the external-domain rule before anything is written
or released. Three dispositions:

- SEND   -> the caller may hand the message to transport, then must call
            mark_sent() so the dedupe key enters the register (§1.10)
- DRAFT  -> written to outbox/pending-approval/ with full headers, both
            languages, and a one-line rationale; released only by an
            authenticated CEO approval (§10, v4.3 finding V11)
- NEVER  -> GateViolation. There is no override parameter on purpose.

External-domain rule: every recipient must be internal. The sole scoped
exception is the §3.1 continuity CC (D-04), appended automatically —
and never on SUSPECTED_FRAUD, S1–S4 flags, SOD itemisations, or
confidential-client content.

Nothing releases on silence.
"""

import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from . import HaltError

INTERNAL_DOMAIN = "ubcsis.com"
BACKUP_CC = "contact.ubcsis@gmail.com"

# D-04: content classes the continuity CC never carries.
CC_EXCLUDED_CLASSES = {
    "SUSPECTED_FRAUD",
    "S1", "S2", "S3", "S4",
    "SOD_ITEMISATION",
    "CONFIDENTIAL_CLIENT",
    # Not in D-04's list, which was written before D-17. Special-category
    # health data is the thing that list exists to keep out of a consumer
    # mailbox outside company control, arriving by a door the list did
    # not anticipate. §14.1 permits a tightening without approval and
    # requires approval only to loosen, so it is applied and disclosed
    # (`hse.py: cc_exclusion_note`) rather than waited on.
    "HSE_INCIDENT",
}

# §10 gate table (v4.3). Rows: action kind -> {run_mode: disposition}.
_D, _S, _N = "DRAFT", "SEND", "NEVER"
ACTION_GATES: dict[str, dict[str, str]] = {
    "CLASS12_ALERT":     {"DRY_RUN": _D, "SUPERVISED": _S, "LIVE": _S},
    "CLASS3_REMINDER":   {"DRY_RUN": _D, "SUPERVISED": _S, "LIVE": _S},
    "VERDICT_REPLY":     {"DRY_RUN": _D, "SUPERVISED": _D, "LIVE": _S},
    "ESCALATION_L1_L2":  {"DRY_RUN": _D, "SUPERVISED": _D, "LIVE": _S},
    "CEO_ESCALATION_L3": {"DRY_RUN": _D, "SUPERVISED": _D, "LIVE": _D},
    "FRAUD_FLAG":        {"DRY_RUN": _D, "SUPERVISED": _S, "LIVE": _S},
    "WATCHDOG_NOTICE":   {"DRY_RUN": _D, "SUPERVISED": _S, "LIVE": _S},
    "MANAGEMENT_REPORT": {"DRY_RUN": _D, "SUPERVISED": _D, "LIVE": _D},
}
# DISCOVERY sends nothing (§6): everything drafts.
_DISCOVERY_DISPOSITION = _D


class GateViolation(HaltError):
    """An action the gate table forbids in every mode. Not retryable."""


class ApprovalAuthenticationError(HaltError):
    """An approval-shaped reply that fails authentication — a security
    event (§13.2), logged and flagged, never honoured."""


@dataclass
class OutboundMessage:
    kind: str
    subject: str
    body: str
    recipients: list[str]
    cc: list[str] = field(default_factory=list)
    dedupe_key: str = ""
    rationale: str = ""
    content_classes: set[str] = field(default_factory=set)


@dataclass
class Disposition:
    action: str                 # SEND | DRAFT | SKIPPED_DUPLICATE
    message: OutboundMessage | None = None
    draft_id: str | None = None
    draft_path: str | None = None


def decide(kind: str, run_mode: str) -> str:
    if run_mode == "DISCOVERY":
        return _DISCOVERY_DISPOSITION
    gates = ACTION_GATES.get(kind)
    if gates is None:
        raise GateViolation(f"unknown outbound action kind {kind!r} — nothing implicit passes the gate")
    disposition = gates.get(run_mode)
    if disposition is None:
        raise GateViolation(f"run mode {run_mode!r} has no gate row for {kind!r}")
    return disposition


def _domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower() if "@" in email else ""


class Outbox:
    def __init__(self, control_root: Path, run_mode: str, ceo: str,
                 backup_cc: str = BACKUP_CC, coo: str | None = None,
                 ceo_absent: bool = False):
        self.pending = Path(control_root) / "outbox" / "pending-approval"
        self.sent_dir = Path(control_root) / "outbox" / "sent"
        self.pending.mkdir(parents=True, exist_ok=True)
        self.sent_dir.mkdir(parents=True, exist_ok=True)
        self.run_mode = run_mode
        self.ceo = ceo.lower()
        self.coo = (coo or "").lower()
        # §3.3, extended to draft release on 16-Aug-2026: during
        # REGISTERED CEO absence the COO deputises. Not a standing
        # delegation — the flag is set from the absence register, so an
        # unregistered absence does not open the gate, and a deputy
        # cannot appoint themselves.
        self.ceo_absent = bool(ceo_absent)
        self.backup_cc = backup_cc

    def _may_release(self, sender: str) -> tuple[bool, bool]:
        """(permitted, deputised) for this authenticated sender."""
        sender = sender.lower()
        if sender == self.ceo:
            return True, False
        if self.coo and sender == self.coo and self.ceo_absent:
            return True, True
        return False, False

    # -- gate enforcement --------------------------------------------------

    def _check_recipients(self, msg: OutboundMessage) -> None:
        for address in msg.recipients + msg.cc:
            d = _domain(address)
            if d != INTERNAL_DOMAIN and address.lower() != self.backup_cc:
                raise GateViolation(
                    f"external recipient {address!r} — the external gate never opens (§10)"
                )

    def _apply_continuity_cc(self, msg: OutboundMessage) -> None:
        """D-04: standing CC, excluding the sensitive content classes."""
        if msg.content_classes & CC_EXCLUDED_CLASSES:
            return
        if self.backup_cc not in [c.lower() for c in msg.cc]:
            msg.cc.append(self.backup_cc)

    def known_dedupe_keys(self) -> set[str]:
        """Idempotency source (§1.10): keys already sent, or already pending.

        Pending counts. A draft awaiting the CEO's release is a message
        that exists; producing a second one for the same event would put
        two versions of the same report in front of the same person with
        nothing saying which is current.
        """
        keys: set[str] = set()
        for folder in (self.sent_dir, self.pending):
            for path in folder.glob("*.json"):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                key = record.get("dedupe_key")
                if key:
                    keys.add(key)
        return keys

    def submit(self, msg: OutboundMessage, already_sent: set[str] | None = None) -> Disposition:
        if msg.dedupe_key and already_sent and msg.dedupe_key in already_sent:
            return Disposition("SKIPPED_DUPLICATE")

        disposition = decide(msg.kind, self.run_mode)  # raises on NEVER/unknown
        self._check_recipients(msg)
        self._apply_continuity_cc(msg)
        self._check_recipients(msg)  # re-verify after mutation

        if disposition == _S:
            return Disposition("SEND", message=msg)

        draft_id = f"DRAFT-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8]}"
        record = {
            "draft_id": draft_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "run_mode": self.run_mode,
            "rationale": msg.rationale or "(rationale not provided)",
            "headers": {
                "To": msg.recipients,
                "Cc": msg.cc,
                "Subject": msg.subject,
            },
            "kind": msg.kind,
            "dedupe_key": msg.dedupe_key,
            "content_classes": sorted(msg.content_classes),
            "body": msg.body,
            "status": "PENDING_APPROVAL",
        }
        path = self.pending / f"{draft_id}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return Disposition("DRAFT", message=msg, draft_id=draft_id, draft_path=str(path))

    # -- approval (§10, authenticated per v4.3/V11) ------------------------

    def approve(
        self,
        draft_id: str,
        *,
        authenticated_sender: str,
        in_reply_to_draft: str | None,
        reply_body: str,
        message_id: str,
    ) -> OutboundMessage:
        """Release a pending draft. Valid only when the reply:
        - carries the CEO's authenticated internal sender (message
          properties, never display name),
        - is in-thread on this draft,
        - quotes the draft ID.
        Anything else is a security event and the draft stays pending.
        """
        path = self.pending / f"{draft_id}.json"
        if not path.exists():
            raise ApprovalAuthenticationError(f"no pending draft {draft_id!r}")

        permitted, deputised = self._may_release(authenticated_sender)
        if not permitted:
            if self.coo and authenticated_sender.lower() == self.coo:
                raise ApprovalAuthenticationError(
                    f"approval sender {authenticated_sender!r} is the COO, but "
                    "no CEO absence is registered — the deputy path opens from "
                    "the absence register, never from the deputy (§3.3)"
                )
            raise ApprovalAuthenticationError(
                f"approval sender {authenticated_sender!r} is not the CEO — security event (§13.2)"
            )
        if in_reply_to_draft != draft_id:
            raise ApprovalAuthenticationError(
                "approval reply is not in-thread on the pending draft — security event (§13.2)"
            )
        if not re.search(re.escape(draft_id), reply_body):
            raise ApprovalAuthenticationError(
                "approval reply does not quote the draft ID — nothing releases on silence (§10)"
            )

        record = json.loads(path.read_text(encoding="utf-8"))
        record["status"] = "APPROVED"
        record["approved_by"] = authenticated_sender
        # §3.3: every deputised approval is logged as such, so the
        # record shows who actually released it and under what authority.
        record["deputised"] = deputised
        if deputised:
            record["deputised_for"] = self.ceo
        record["approval_message_id"] = message_id
        record["approved_at"] = datetime.now(timezone.utc).isoformat()
        (self.sent_dir / f"{draft_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        path.unlink()
        return OutboundMessage(
            kind=record["kind"],
            subject=record["headers"]["Subject"],
            body=record["body"],
            recipients=record["headers"]["To"],
            cc=record["headers"]["Cc"],
            dedupe_key=record["dedupe_key"],
            content_classes=set(record["content_classes"]),
        )

    def mark_sent(self, msg: OutboundMessage, message_id: str) -> Path:
        record = asdict(msg) | {
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "message_id": message_id,
            "content_classes": sorted(msg.content_classes),
        }
        path = self.sent_dir / f"SENT-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
