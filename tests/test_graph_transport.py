import base64
import json

import pytest

from control import HaltError
from control.transport import GRAPH_BASE, GraphTransport

MAILBOX = "control@ubcsis.com"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeSession:
    """Queues responses per (method, url-prefix) and records requests."""

    def __init__(self):
        self.routes: list[tuple[str, str, FakeResponse]] = []
        self.requests: list[tuple[str, str, dict]] = []

    def add(self, method: str, url_part: str, response: FakeResponse):
        self.routes.append((method, url_part, response))

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        for i, (m, part, response) in enumerate(self.routes):
            if m == method and part in url:
                self.routes.pop(i)
                return response
        raise AssertionError(f"unexpected request {method} {url}")


def _transport(session, sleeps=None):
    return GraphTransport(
        MAILBOX,
        token_provider=lambda: "tok",
        session=session,
        sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
    )


MESSAGE = {
    "id": "graph-id-1",
    "internetMessageId": "<m1@ubcsis.com>",
    "from": {"emailAddress": {"name": "Donia Ali", "address": "donia@ubcsis.com"}},
    "toRecipients": [{"emailAddress": {"address": MAILBOX}}],
    "ccRecipients": [],
    "subject": "Weekly report",
    "bodyPreview": "DISPUTE - wrong deadline\nmore text",
    "receivedDateTime": "2026-08-13T07:00:00Z",
    "hasAttachments": True,
    "inReplyTo": None,
}


def test_fetch_with_pagination_and_attachments():
    session = FakeSession()
    page2_url = f"{GRAPH_BASE}/users/{MAILBOX}/page2"
    session.add("GET", "/mailFolders/Inbox/messages", FakeResponse(
        payload={"value": [MESSAGE], "@odata.nextLink": page2_url}))
    session.add("GET", "/attachments", FakeResponse(payload={"value": [{
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": "FRM-WPR.xlsx",
        "contentBytes": base64.b64encode(b"PK\x03\x04data").decode(),
    }]}))
    session.add("GET", "/page2", FakeResponse(payload={"value": []}))

    t = _transport(session)
    messages = t.fetch_unprocessed()
    assert len(messages) == 1
    m = messages[0]
    assert m.message_id == "<m1@ubcsis.com>"
    assert m.sender == "Donia Ali <donia@ubcsis.com>"
    assert m.first_line == "DISPUTE - wrong deadline"
    assert m.attachments == [("FRM-WPR.xlsx", b"PK\x03\x04data")]


def test_retry_after_honoured_then_success():
    session = FakeSession()
    session.add("GET", "/messages", FakeResponse(429, headers={"Retry-After": "7"}))
    session.add("GET", "/messages", FakeResponse(payload={"value": []}))
    sleeps = []
    t = _transport(session, sleeps=sleeps)
    assert t.fetch_unprocessed() == []
    assert sleeps == [7]


def test_persistent_throttle_is_failed_cycle():
    session = FakeSession()
    for _ in range(5):
        session.add("GET", "/messages", FakeResponse(429, headers={"Retry-After": "1"}))
    t = _transport(session, sleeps=[])
    with pytest.raises(HaltError, match="FAILED"):
        t.fetch_unprocessed()


def test_http_error_halts():
    session = FakeSession()
    session.add("GET", "/messages", FakeResponse(403, payload={"error": "denied"}))
    with pytest.raises(HaltError, match="403"):
        _transport(session).fetch_unprocessed()


def test_send_payload_shape():
    session = FakeSession()
    session.add("POST", "/sendMail", FakeResponse(202))
    t = _transport(session)
    message_id = t.send(["ahmed@ubcsis.com"], ["contact.ubcsis@gmail.com"],
                        "[CONTROL] Test", "body")
    assert message_id.startswith("<graph-accepted-")
    method, url, kwargs = session.requests[-1]
    body = kwargs["json"]["message"]
    assert body["toRecipients"] == [{"emailAddress": {"address": "ahmed@ubcsis.com"}}]
    assert kwargs["json"]["saveToSentItems"] is True


def test_mark_processed_patches_graph_id():
    session = FakeSession()
    msg = dict(MESSAGE, hasAttachments=False)
    session.add("GET", "/messages", FakeResponse(payload={"value": [msg]}))
    t = _transport(session)
    t.fetch_unprocessed()
    session.add("PATCH", "/messages/graph-id-1", FakeResponse(200))
    t.mark_processed("<m1@ubcsis.com>")
    method, url, kwargs = session.requests[-1]
    assert method == "PATCH" and kwargs["json"] == {"isRead": True}


def test_missing_credentials_fail_loudly():
    with pytest.raises(HaltError, match="certificate"):
        GraphTransport(MAILBOX)
