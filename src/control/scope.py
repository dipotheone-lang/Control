"""Mailbox scope — charter §3.1a, CEO decision D-07.

The CEO closed O-05 on Option C: widen the Application Access Policy
from control@ alone to the named shared functional mailboxes. The
charter attaches one condition to that option in the same sentence that
offers it — "Requires the §12.4 usage policy to state it explicitly" —
and §12.2 attaches another, because wider ingestion of correspondence
about identified individuals is more personal-data processing, not the
same amount from more places.

So this module holds two things apart that are easy to conflate:

  what the CEO decided      — Option C, recorded, settled
  what Control may read now — control@, until the preconditions close

A decision is not a deployment. Control operates on Option A until
every precondition in mailbox-scope.yaml is closed, and says so in
every report while that remains true. It never advances its own scope.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import HaltError

CONTROL_MAILBOX_DEFAULT = "control@ubcsis.com"
VALID_STATES = ("DECIDED", "PROVISIONED", "LIVE")


@dataclass
class MailboxScope:
    option: str = "A"
    state: str = "DECIDED"
    control_mailbox: str = CONTROL_MAILBOX_DEFAULT
    declared: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    open_preconditions: list[dict] = field(default_factory=list)

    @property
    def effective(self) -> list[str]:
        """The mailboxes Control may actually read.

        Not what was decided — what is permitted today. The two differ
        for as long as a precondition is open, and that difference is
        the honest state of the system, not a bug to be smoothed over.
        """
        if self.state == "LIVE" and not self.open_preconditions:
            return [self.control_mailbox] + [
                m for m in self.declared if m != self.control_mailbox]
        return [self.control_mailbox]

    @property
    def operating_option(self) -> str:
        """The option in force right now, which may not be the one chosen."""
        return self.option if len(self.effective) > 1 else "A"

    @property
    def pending(self) -> bool:
        return self.option != "A" and self.operating_option == "A"


def load_scope(config: dict | None) -> MailboxScope:
    """Read mailbox-scope.yaml content into a scope.

    A missing or empty file means Option A — control@ only. That is the
    charter's own default (§3.1a "Until then Control operates on Option
    A"), so absence is a safe state rather than a halt.
    """
    data = config or {}
    state = str(data.get("state") or "DECIDED").upper()
    if state not in VALID_STATES:
        raise HaltError(
            f"mailbox-scope.yaml: state must be one of {', '.join(VALID_STATES)}, "
            f"not {state!r} (§3.1a)"
        )
    option = str(data.get("option") or "A").upper()

    control_mailbox = str(
        data.get("control_mailbox") or CONTROL_MAILBOX_DEFAULT).lower()
    declared = [str(m).lower() for m in (data.get("mailboxes") or []) if m]
    excluded = list(data.get("excluded") or [])
    open_pre = [p for p in (data.get("preconditions") or [])
                if not p.get("closed")]

    scope = MailboxScope(
        option=option, state=state, control_mailbox=control_mailbox,
        declared=declared, excluded=excluded, open_preconditions=open_pre,
    )

    # The one combination that must never pass silently: scope declared
    # LIVE while a condition the charter names is still open.
    if state == "LIVE" and open_pre:
        raise HaltError(
            "mailbox-scope.yaml: state is LIVE with "
            f"{len(open_pre)} open precondition(s) — "
            + ", ".join(str(p.get("id")) for p in open_pre)
            + ". Option C requires them closed first (§3.1a, §12.2, §12.4). "
            "Control does not widen its own scope."
        )
    return scope


def load_scope_file(config_dir: Path) -> MailboxScope:
    path = Path(config_dir) / "mailbox-scope.yaml"
    if not path.is_file():
        return MailboxScope()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise HaltError(f"mailbox-scope.yaml unparseable: {e}") from e
    return load_scope(data)


def assert_readable(mailbox: str, scope: MailboxScope) -> None:
    """Guard a live read. Discovery is not routed through here."""
    if mailbox.lower() not in scope.effective:
        raise HaltError(
            f"{mailbox} is not in the operative mailbox scope "
            f"({', '.join(scope.effective)}). Decision D-07 chose Option C, "
            "but it does not take effect until its preconditions close "
            "(§3.1a)."
        )


# ---- what the reports must say ---------------------------------------

def limitation_lines(scope: MailboxScope) -> tuple[str, str]:
    """The §3.1a standing limitation, matched to the state in force.

    The charter mandates a verbatim line while Option A is operative.
    Once a wider scope is genuinely live, repeating it would be a false
    statement in the opposite direction — claiming a blind spot that no
    longer exists understates what Control holds about people.
    """
    if scope.operating_option == "A":
        en = (
            "External SLA coverage is limited to threads copied to control@. "
            "Traffic in sales@ and procure@ is not visible to this system."
        )
        ar = (
            "تقتصر تغطية مواعيد الرد الخارجية على المراسلات المحوّلة إلى control@. "
            "المراسلات في sales@ و procure@ غير مرئية لهذا النظام."
        )
        if scope.pending:
            en += (
                f" Option {scope.option} was decided on {scope.state.lower()} "
                "terms (D-07) and is not yet in effect."
            )
            ar += (
                f" تم اتخاذ القرار بتوسيع النطاق (الخيار {scope.option}) "
                "ولم يدخل حيّز التنفيذ بعد."
            )
        return en, ar

    named = ", ".join(scope.effective)
    en = (
        "External SLA coverage spans the mailboxes in scope under decision "
        f"D-07: {named}. Correspondence outside these mailboxes remains "
        "invisible to this system."
    )
    ar = (
        "تشمل تغطية مواعيد الرد الخارجية صناديق البريد المدرجة ضمن النطاق "
        f"بموجب القرار D-07: {named}. وتظل المراسلات خارج هذه الصناديق غير "
        "مرئية لهذا النظام."
    )
    return en, ar


def open_precondition_lines(scope: MailboxScope) -> list[str]:
    """Decision-required lines for a chosen-but-blocked scope change."""
    if not scope.pending:
        return []
    lines = [
        f"O-05 is closed (D-07: Option {scope.option}), but the scope change "
        f"is blocked by {len(scope.open_preconditions)} open precondition(s). "
        "Control is operating on Option A meanwhile."
    ]
    for item in scope.open_preconditions:
        requirement = " ".join(str(item.get("requirement", "")).split())
        lines.append(f"   {item.get('id')}: {requirement}")
    return lines
