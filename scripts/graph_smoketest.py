"""Read-only Graph connection smoke test — Track B step B6.

Verifies certificate auth and single-mailbox access. Fetches unread
message METADATA counts only — prints no content, sends nothing.

Usage (after provision-graph.ps1 and dot-sourcing graph-env.ps1):
    python scripts/graph_smoketest.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from control import HaltError                      # noqa: E402
from control.transport import GraphTransport       # noqa: E402


def main() -> int:
    try:
        transport = GraphTransport.from_env()
    except HaltError as e:
        print(f"NOT READY: {e}", file=sys.stderr)
        return 2

    try:
        messages = transport.fetch_unprocessed()
    except HaltError as e:
        print(f"CONNECTION FAILED: {e}", file=sys.stderr)
        print("Check: admin consent granted? Application Access Policy applied "
              "(can take ~30 minutes)? Certificate uploaded?", file=sys.stderr)
        return 1

    print(f"OK — connected to {transport.mailbox}")
    print(f"unread messages visible: {len(messages)}")
    with_attachments = sum(1 for m in messages if m.attachments)
    print(f"of which with attachments: {with_attachments}")
    if messages:
        newest = max(m.received_at for m in messages)
        print(f"newest unread received: {newest:%d-%b-%Y %H:%M}")
    print("smoke test read metadata only; nothing was sent or modified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
