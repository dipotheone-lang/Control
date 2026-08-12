"""Mail transport boundary — charter §5.1.

The engine never talks to Microsoft Graph directly; it talks to this
interface. GraphTransport is deliberately a stub: it documents the §5.1
requirements (certificate auth, single-mailbox Application Access
Policy, Retry-After handling, FAILED cycle on partial sweep) and raises
until the tenant, certificate, and mailbox exist (decision O-09 and the
§5.1 environment values). No fake network code pretending to work.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FetchedMessage:
    message_id: str
    sender: str
    received_at: datetime
    to: str = ""
    cc: str = ""
    subject: str = ""
    first_line: str = ""
    attachments: list[tuple[str, bytes]] = field(default_factory=list)
    in_reply_to_control: bool = False


class MailTransport:
    """Interface. fetch_unprocessed must be COMPLETE or raise — an
    incomplete sweep is a FAILED cycle, never a shorter message list
    (§5.1); absences must never be recorded from a partial view."""

    def fetch_unprocessed(self) -> list[FetchedMessage]:
        raise NotImplementedError

    def send(self, recipients: list[str], cc: list[str], subject: str, body: str) -> str:
        """Returns the transport message id."""
        raise NotImplementedError


class MockTransport(MailTransport):
    """In-memory transport for tests and DRY_RUN rehearsals."""

    def __init__(self, inbox: list[FetchedMessage] | None = None):
        self.inbox = list(inbox or [])
        self.outgoing: list[dict] = []
        self._counter = 0

    def fetch_unprocessed(self) -> list[FetchedMessage]:
        batch, self.inbox = self.inbox, []
        return batch

    def send(self, recipients, cc, subject, body) -> str:
        self._counter += 1
        message_id = f"<mock-{self._counter}@ubcsis.com>"
        self.outgoing.append({
            "message_id": message_id, "to": list(recipients), "cc": list(cc),
            "subject": subject, "body": body,
        })
        return message_id


class GraphTransport(MailTransport):
    """Microsoft Graph transport — NOT IMPLEMENTED until §5.1 is
    provisioned: Entra app scoped to control@ubcsis.com, certificate
    auth (non-exportable), Exchange Application Access Policy, and the
    GRAPH_* environment values (O-09). Implementations must honour
    Retry-After with exponential backoff and raise on any partial sweep
    so the cycle is marked FAILED (§5.1, §13.2)."""

    def __init__(self, *_args, **_kwargs):
        raise NotImplementedError(
            "GraphTransport requires the §5.1 provisioning: tenant, "
            "certificate thumbprint, Application Access Policy, and "
            "CONTROL_MAILBOX. Use MockTransport until then."
        )
