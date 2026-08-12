"""Inbound mail classification — charter §9.

Categories: OBLIGATION_SUBMISSION · UNSCHEDULED_SUBMISSION ·
EXTERNAL_INBOUND · INTERNAL_CORRESPONDENCE · REPLY_TO_CONTROL · DISPUTE ·
SYSTEM_PEER · BACKUP_CHANNEL · SUSPECTED_FRAUD · SYSTEM_NOISE · AMBIGUOUS

Design constraints from the charter:
- Email content is data, never command (§13.2) — classification reads it,
  never obeys it; redirection attempts are flagged as security events.
- SUSPECTED_FRAUD goes to CEO/CFO only and never produces a reply to the
  sender (§9); the classifier only labels — routing enforces that.
- A sender not in the roster is not evaluated (§13.2): the result is
  AMBIGUOUS with a flag — new joiner or impersonation, a human decides.
- Client-confidential detection is conservative (§12.1.1): a listed
  domain marks the message confidential regardless of category.
"""

import re
from dataclasses import dataclass, field
from email.utils import parseaddr

INTERNAL_DOMAIN = "ubcsis.com"
PEER_ADDRESS = "elevate@ubcsis.com"
BACKUP_ADDRESS = "contact.ubcsis@gmail.com"

_NOISE_SUBJECTS = re.compile(
    r"(?i)^(automatic reply|auto[- ]?reply|out of office|undeliverable|"
    r"delivery (status notification|has failed)|mail delivery failed|read:)"
)
_NOISE_SENDERS = re.compile(r"(?i)^(no[-_.]?reply|mailer-daemon|postmaster|bounce)")

# §7.3 S1: supplier bank-detail change — the highest-priority flag in the
# system. Cues only; the flag is factual, never an accusation.
_BANK_CUES = re.compile(
    r"(?i)(bank (account|details?)|IBAN|beneficiary|account number|swift|"
    r"تغيير الحساب|الحساب البنكي|رقم الحساب|آيبان)"
)
_BANK_CHANGE_CUES = re.compile(r"(?i)(new|chang|updat|replac|جديد|تغيير|تحديث)")

# §13.2 prompt-injection defence: text instructing the system is a
# security event, never an instruction.
_REDIRECTION_CUES = re.compile(
    r"(?i)(ignore (all |any |previous |prior )*(instructions?|rules?)|"
    r"disregard (the )?(charter|rules|instructions)|"
    r"you (are|should) now|new instructions? for control|"
    r"send (this|it) to an external|skip (the )?(check|validation|approval))"
)

_DISPUTE_MARKERS = ("DISPUTE", "اعتراض")


def _edit_distance_leq(a: str, b: str, limit: int) -> bool:
    """True if levenshtein(a, b) <= limit (small-limit band algorithm)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > limit:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
            row_min = min(row_min, cur[j])
        if row_min > limit:
            return False
        prev = cur
    return prev[-1] <= limit


@dataclass
class InboundMessage:
    sender: str
    to: str = ""
    cc: str = ""
    subject: str = ""
    first_line: str = ""            # first line of the body — dispute marker (§8.4)
    attachments: list[str] = field(default_factory=list)
    in_reply_to_control: bool = False  # thread position: reply to a Control message


@dataclass
class Classification:
    category: str
    reasons: list[str] = field(default_factory=list)
    confidential: bool = False
    security_event: bool = False
    flags: list[str] = field(default_factory=list)


class Classifier:
    def __init__(
        self,
        roster_emails: set[str],
        obligation_forms: dict[str, str] | None = None,
        confidential_domains: set[str] | None = None,
        known_domains: set[str] | None = None,
    ):
        self.roster = {e.lower() for e in roster_emails}
        self.obligation_forms = {k.lower(): v for k, v in (obligation_forms or {}).items()}
        self.confidential_domains = {d.lower() for d in (confidential_domains or set())}
        # Domains we correspond with legitimately — the near-miss reference set.
        self.known_domains = {d.lower() for d in (known_domains or set())} | {INTERNAL_DOMAIN}

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _addr(raw: str) -> tuple[str, str]:
        email = parseaddr(raw)[1].lower()
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        return email, domain

    def _near_miss(self, domain: str) -> str | None:
        """§7.3 S1: a domain one or two characters from a known domain."""
        if not domain or domain in self.known_domains:
            return None
        for known in self.known_domains:
            if _edit_distance_leq(domain, known, 2):
                return known
        return None

    def _matched_obligation(self, attachments: list[str]) -> str | None:
        for name in attachments:
            lower = name.lower()
            for form_code, obligation_id in self.obligation_forms.items():
                if form_code in lower:
                    return obligation_id
        return None

    # -- classification ----------------------------------------------------

    def classify(self, msg: InboundMessage) -> Classification:
        email, domain = self._addr(msg.sender)
        result = Classification(category="AMBIGUOUS")
        text = f"{msg.subject}\n{msg.first_line}"

        if domain in self.confidential_domains:
            result.confidential = True
            result.flags.append(f"confidential client domain: {domain} (§12.1.1)")

        # Security events outrank every routine category.
        near = self._near_miss(domain)
        if near:
            result.category = "SUSPECTED_FRAUD"
            result.security_event = True
            result.reasons.append(f"near-miss sender domain {domain!r} vs known {near!r} (§7.3 S1)")
            return result
        if _BANK_CUES.search(text) and _BANK_CHANGE_CUES.search(text) and domain != INTERNAL_DOMAIN:
            result.category = "SUSPECTED_FRAUD"
            result.security_event = True
            result.reasons.append("bank-detail change cues from external sender (§7.3 S1)")
            return result
        if _REDIRECTION_CUES.search(text):
            result.security_event = True
            result.flags.append("embedded-instruction cues — content is data, never command (§13.2)")
            # Classification continues: the original evaluation proceeds.

        # Special addresses (§3.1).
        if email == PEER_ADDRESS:
            result.category = "SYSTEM_PEER"
            result.reasons.append("peer automated system — log only, never reply")
            return result
        if email == BACKUP_ADDRESS:
            result.category = "BACKUP_CHANNEL"
            result.reasons.append("continuity backup — not a submission unless CEO confirms outage")
            return result

        # Noise before roster logic: bounces impersonate no one.
        if _NOISE_SUBJECTS.search(msg.subject) or _NOISE_SENDERS.match(email.split("@")[0]):
            result.category = "SYSTEM_NOISE"
            result.reasons.append("automated notification pattern")
            return result

        # Dispute: first line of the body, either language (§8.4).
        first = msg.first_line.strip().upper()
        if any(first.startswith(m.upper()) for m in _DISPUTE_MARKERS):
            result.category = "DISPUTE"
            result.reasons.append("dispute marker on first line — escalation clock suspends")
            return result

        if domain == INTERNAL_DOMAIN:
            if email not in self.roster:
                result.category = "AMBIGUOUS"
                result.flags.append(
                    "sender not in roster — do not evaluate; new joiner or impersonation (§13.2)"
                )
                return result
            if msg.attachments:
                obligation_id = self._matched_obligation(msg.attachments)
                if obligation_id:
                    result.category = "OBLIGATION_SUBMISSION"
                    result.reasons.append(f"form code matches obligation {obligation_id}")
                else:
                    result.category = "UNSCHEDULED_SUBMISSION"
                    result.reasons.append(
                        "attachment with no matching obligation — acknowledge, log, "
                        "flag as candidate obligation (§13.2, §14.3)"
                    )
                return result
            if msg.in_reply_to_control:
                result.category = "REPLY_TO_CONTROL"
                result.reasons.append("in-thread reply to a Control message")
                return result
            result.category = "INTERNAL_CORRESPONDENCE"
            result.reasons.append("internal sender, no attachment, not a Control thread")
            return result

        if domain:
            result.category = "EXTERNAL_INBOUND"
            result.reasons.append(f"external domain {domain} — watchdog owns the SLA (§8.5)")
            return result

        result.flags.append("unparseable sender address")
        return result
