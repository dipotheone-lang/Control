"""Read-only Outlook connection check — the local alternative to Graph.

Attaches to classic Outlook on this machine, resolves the mailbox, and
reports what it can see. Prints counts and subjects only; sends
nothing, marks nothing read, opens no attachment.

Usage:
    python scripts\\outlook_smoketest.py                     # control@ubcsis.com
    python scripts\\outlook_smoketest.py someone@ubcsis.com  # another mailbox
    python scripts\\outlook_smoketest.py --list              # show all accounts
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from control import HaltError                          # noqa: E402
from control.outlook import OutlookTransport, _dispatch_namespace   # noqa: E402

DEFAULT_MAILBOX = "control@ubcsis.com"


def list_accounts() -> int:
    try:
        namespace = _dispatch_namespace()
    except HaltError as e:
        print(f"NOT READY: {e}", file=sys.stderr)
        return 2
    print("Mailboxes in this Outlook profile:")
    for store in namespace.Folders:
        address = getattr(store, "SmtpAddress", "") or getattr(store, "Name", "?")
        print(f"  - {address}")
        for folder in store.Folders:
            name = getattr(folder, "Name", "?")
            try:
                count = folder.Items.Count
            except Exception:
                count = "?"
            print(f"      {name} ({count} items)")
    return 0


def main(argv: list[str]) -> int:
    if "--list" in argv:
        return list_accounts()
    mailbox = next((a for a in argv if "@" in a), DEFAULT_MAILBOX)

    try:
        transport = OutlookTransport(mailbox)
        messages = transport.fetch_unprocessed()
    except HaltError as e:
        print(f"NOT READY: {e}", file=sys.stderr)
        print("\nTip: run with --list to see which mailboxes this profile holds.",
              file=sys.stderr)
        return 1

    print(f"OK - attached to {mailbox} via Outlook")
    print(f"unread messages visible: {len(messages)}")
    print(f"of which with attachments: {sum(1 for m in messages if m.attachments)}")
    if messages:
        newest = max(m.received_at for m in messages)
        print(f"newest unread received: {newest:%d-%b-%Y %H:%M}")
        print("\nmost recent subjects:")
        for m in sorted(messages, key=lambda x: x.received_at, reverse=True)[:5]:
            print(f"  {m.received_at:%d-%b %H:%M}  {m.subject[:60]}")
    print("\nread-only check: nothing sent, nothing marked read")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
