"""Mail transport — charter §5.1.

The engine talks to this interface, never to Microsoft Graph directly.

GraphTransport is a real implementation: certificate-authenticated
app-only access to the single control mailbox, honouring the §5.1
rules — respect Retry-After with bounded retries, and treat any
incomplete sweep as a FAILED cycle (HaltError) rather than a shorter
message list. It still requires the tenant-side provisioning (Entra app,
certificate, Exchange Application Access Policy — see
docs/PHASE0-RUNBOOK.md); without credentials it fails loudly at
construction, never silently.
"""

import base64
import os
import time as _time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import HaltError

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_MAX_RETRIES = 3


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

    def mark_processed(self, message_id: str) -> None:
        """Marking read is permitted only as part of processing (§9)."""
        raise NotImplementedError


class MockTransport(MailTransport):
    """In-memory transport for tests and DRY_RUN rehearsals."""

    def __init__(self, inbox: list[FetchedMessage] | None = None):
        self.inbox = list(inbox or [])
        self.outgoing: list[dict] = []
        self.processed: list[str] = []
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

    def mark_processed(self, message_id: str) -> None:
        self.processed.append(message_id)


class GraphTransport(MailTransport):
    """App-only Microsoft Graph access to the control mailbox.

    Construction paths:
    - production: pass tenant_id, client_id, certificate private key PEM
      and thumbprint — MSAL acquires tokens by certificate (§5.1: never
      a client secret in a file)
    - tests: pass token_provider and session explicitly

    All requests honour Retry-After on 429/503 with bounded retries;
    exhausting retries raises HaltError so the cycle records FAILED
    rather than operating on a partial sweep.
    """

    def __init__(
        self,
        mailbox: str,
        *,
        tenant_id: str | None = None,
        client_id: str | None = None,
        certificate_pem: str | None = None,
        certificate_thumbprint: str | None = None,
        token_provider=None,
        session=None,
        sleep=_time.sleep,
    ):
        self.mailbox = mailbox
        self._sleep = sleep
        self._graph_ids: dict[str, str] = {}
        if session is None:
            import requests
            session = requests.Session()
        self.session = session

        if token_provider is not None:
            self._token_provider = token_provider
        else:
            if not all([tenant_id, client_id, certificate_pem, certificate_thumbprint]):
                raise HaltError(
                    "GraphTransport requires tenant_id, client_id, certificate_pem "
                    "and certificate_thumbprint (§5.1 — certificate auth, never a "
                    "client secret). See docs/PHASE0-RUNBOOK.md."
                )
            # MSAL app construction performs OIDC discovery (network I/O),
            # so it is deferred to the first token request — construction
            # of the transport itself never touches the network.
            _app_holder: list = []

            def _acquire() -> str:
                if not _app_holder:
                    import msal

                    _app_holder.append(msal.ConfidentialClientApplication(
                        client_id,
                        authority=f"https://login.microsoftonline.com/{tenant_id}",
                        client_credential={
                            "private_key": certificate_pem,
                            "thumbprint": certificate_thumbprint,
                        },
                    ))
                result = _app_holder[0].acquire_token_for_client(
                    scopes=["https://graph.microsoft.com/.default"]
                )
                if "access_token" not in result:
                    raise HaltError(
                        f"Graph auth failed: {result.get('error')}: "
                        f"{result.get('error_description')} — after retries the "
                        "cycle halts and the CEO is alerted via the backup address "
                        "(§13.2)"
                    )
                return result["access_token"]

            self._token_provider = _acquire

    # -- HTTP with §5.1 throttling discipline ------------------------------

    def _request(self, method: str, url: str, **kwargs):
        headers = kwargs.pop("headers", {})
        for attempt in range(_MAX_RETRIES + 1):
            headers["Authorization"] = f"Bearer {self._token_provider()}"
            response = self.session.request(method, url, headers=headers, **kwargs)
            if response.status_code in (429, 503):
                if attempt == _MAX_RETRIES:
                    break
                retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
                self._sleep(retry_after)
                continue
            if response.status_code >= 400:
                raise HaltError(
                    f"Graph {method} {url} failed: {response.status_code} "
                    f"{getattr(response, 'text', '')[:200]}"
                )
            return response
        raise HaltError(
            f"Graph throttling persisted after {_MAX_RETRIES} retries on {url} — "
            "incomplete sweep, cycle FAILED (§5.1)"
        )

    # -- interface ---------------------------------------------------------

    def fetch_unprocessed(self) -> list[FetchedMessage]:
        url = (
            f"{GRAPH_BASE}/users/{self.mailbox}/mailFolders/Inbox/messages"
            "?$filter=isRead eq false"
            "&$select=id,internetMessageId,from,toRecipients,ccRecipients,"
            "subject,bodyPreview,receivedDateTime,hasAttachments,"
            "conversationId,inReplyTo"
            "&$top=50&$orderby=receivedDateTime asc"
        )
        messages: list[FetchedMessage] = []
        while url:
            payload = self._request("GET", url).json()
            for item in payload.get("value", []):
                attachments: list[tuple[str, bytes]] = []
                if item.get("hasAttachments"):
                    att_url = (f"{GRAPH_BASE}/users/{self.mailbox}/messages/"
                               f"{item['id']}/attachments")
                    for att in self._request("GET", att_url).json().get("value", []):
                        if att.get("@odata.type") == "#microsoft.graph.fileAttachment":
                            attachments.append((
                                att.get("name", "unnamed"),
                                base64.b64decode(att.get("contentBytes", "")),
                            ))
                sender = (item.get("from", {}).get("emailAddress", {}) or {})
                messages.append(FetchedMessage(
                    message_id=item.get("internetMessageId") or item["id"],
                    sender=f"{sender.get('name', '')} <{sender.get('address', '')}>",
                    received_at=datetime.fromisoformat(
                        item["receivedDateTime"].replace("Z", "+00:00")),
                    to="; ".join(r["emailAddress"]["address"]
                                 for r in item.get("toRecipients", [])),
                    cc="; ".join(r["emailAddress"]["address"]
                                 for r in item.get("ccRecipients", [])),
                    subject=item.get("subject", ""),
                    first_line=(item.get("bodyPreview", "").splitlines() or [""])[0],
                    attachments=attachments,
                    in_reply_to_control=bool(item.get("inReplyTo")),
                ))
                # Graph id needed for mark_processed: remember the mapping.
                self._graph_ids[messages[-1].message_id] = item["id"]
            url = payload.get("@odata.nextLink")
        return messages

    def send(self, recipients, cc, subject, body) -> str:
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": a}} for a in recipients],
                "ccRecipients": [{"emailAddress": {"address": a}} for a in cc],
            },
            "saveToSentItems": True,
        }
        self._request("POST", f"{GRAPH_BASE}/users/{self.mailbox}/sendMail",
                      json=payload)
        # sendMail returns 202 with no body; the durable record is the
        # outbox JSON plus the Sent Items copy.
        return f"<graph-accepted-{datetime.now():%Y%m%d%H%M%S%f}@{self.mailbox}>"

    def mark_processed(self, message_id: str) -> None:
        graph_id = self._graph_ids.get(message_id)
        if graph_id is None:
            return
        self._request(
            "PATCH", f"{GRAPH_BASE}/users/{self.mailbox}/messages/{graph_id}",
            json={"isRead": True},
        )

    # -- construction helpers ----------------------------------------------

    @classmethod
    def from_pfx(cls, mailbox: str, *, tenant_id: str, client_id: str,
                 pfx_path: str | Path, pfx_password: str | bytes, **kwargs):
        """Build from a password-protected PFX bundle.

        MSAL needs the private key material, so a Windows-store
        non-exportable key cannot be used directly from Python. The
        §5.1-compliant compromise: the key travels only inside an
        encrypted PFX, and the password lives in Windows Credential
        Manager (never in a file) — see from_env() and the runbook.
        """
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat, pkcs12,
        )

        data = Path(pfx_path).read_bytes()
        password = pfx_password.encode() if isinstance(pfx_password, str) else pfx_password
        try:
            key, cert, _chain = pkcs12.load_key_and_certificates(data, password)
        except ValueError as e:
            raise HaltError(f"cannot open PFX {pfx_path}: {e}") from e
        if key is None or cert is None:
            raise HaltError(f"PFX {pfx_path} does not contain both key and certificate")
        pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
        thumbprint = cert.fingerprint(hashes.SHA1()).hex().upper()
        return cls(mailbox, tenant_id=tenant_id, client_id=client_id,
                   certificate_pem=pem, certificate_thumbprint=thumbprint, **kwargs)

    @classmethod
    def from_env(cls, environ=None, **kwargs):
        """Build from the §5.1 environment. The PFX password is read from
        Windows Credential Manager (service 'UBCSIS-Control', user 'pfx')
        via keyring when available, else from GRAPH_PFX_PASSWORD."""
        env = environ if environ is not None else os.environ
        required = ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "CONTROL_MAILBOX",
                    "GRAPH_PFX_PATH")
        missing = [k for k in required if not env.get(k)]
        if missing:
            raise HaltError(f"missing environment: {', '.join(missing)} "
                            "(§5.1; see docs/PHASE0-RUNBOOK.md)")
        password = env.get("GRAPH_PFX_PASSWORD")
        if not password:
            try:
                import keyring
                password = keyring.get_password("UBCSIS-Control", "pfx")
            except ImportError:
                password = None
        if not password:
            raise HaltError(
                "PFX password not found: store it in Windows Credential Manager "
                "(service 'UBCSIS-Control', user 'pfx') or set GRAPH_PFX_PASSWORD"
            )
        return cls.from_pfx(
            env["CONTROL_MAILBOX"],
            tenant_id=env["GRAPH_TENANT_ID"],
            client_id=env["GRAPH_CLIENT_ID"],
            pfx_path=env["GRAPH_PFX_PATH"],
            pfx_password=password,
            **kwargs,
        )
