"""Stage A (live) — historical mailbox scan through Outlook.

The transport's fetch_unprocessed() reads unread mail for the operating
cycle. Discovery needs the opposite: the whole history, read or not, to
measure what actually happened (§6 Stage A, and the Stage H numbers
behind decision O-05).

METADATA ONLY. Sender, recipients, timestamp, subject, attachment
filenames, sizes. Message bodies are never read and never written —
that keeps the scan inside §12.1.2 for client-confidential material
without needing to classify each message first.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..outlook import OutlookTransport

INTERNAL_DOMAIN = "ubcsis.com"


@dataclass
class ScanSummary:
    mailbox: str
    folder: str
    total: int = 0
    skipped_non_mail: int = 0
    with_attachments: int = 0
    earliest: str = ""
    latest: str = ""
    top_senders: list = field(default_factory=list)
    by_month: dict = field(default_factory=dict)
    internal_count: int = 0
    external_count: int = 0
    external_domains: list = field(default_factory=list)
    attachment_types: dict = field(default_factory=dict)
    copied_to_control: int = 0          # CC-discipline evidence (O-05)


def _address_of(value: str) -> str:
    value = (value or "").strip().lower()
    if "<" in value and ">" in value:
        value = value[value.rfind("<") + 1:value.rfind(">")]
    return value


def scan_folder(folder, *, mailbox: str, folder_name: str,
                limit: int | None = None, progress=None) -> tuple[list[dict], ScanSummary]:
    """Walk every item in a folder, collecting metadata only."""
    summary = ScanSummary(mailbox=mailbox, folder=folder_name)
    rows: list[dict] = []
    senders: Counter = Counter()
    months: Counter = Counter()
    domains: Counter = Counter()
    extensions: Counter = Counter()
    timestamps: list[datetime] = []

    items = folder.Items
    count = int(getattr(items, "Count", 0) or 0)
    if limit:
        count = min(count, limit)

    for index in range(1, count + 1):
        try:
            item = items.Item(index)
        except Exception:
            continue
        if not hasattr(item, "SenderEmailAddress"):
            summary.skipped_non_mail += 1
            continue

        sender = OutlookTransport._sender_address(item).lower()
        received = OutlookTransport._received_at(item)
        to = str(getattr(item, "To", "") or "")
        cc = str(getattr(item, "CC", "") or "")

        attachment_names: list[str] = []
        attachments = getattr(item, "Attachments", None)
        att_count = int(getattr(attachments, "Count", 0) or 0) if attachments else 0
        for i in range(1, att_count + 1):
            try:
                name = str(getattr(attachments.Item(i), "FileName", "") or "")
            except Exception:
                continue
            if name:
                attachment_names.append(name)
                if "." in name:
                    extensions[name.rsplit(".", 1)[-1].lower()] += 1

        rows.append({
            "mailbox": mailbox,
            "folder": folder_name,
            "sender": sender,
            "to": to,
            "cc": cc,
            "received": received.isoformat(),
            "subject": str(getattr(item, "Subject", "") or ""),
            "attachments": attachment_names,
        })

        summary.total += 1
        if attachment_names:
            summary.with_attachments += 1
        senders[sender] += 1
        timestamps.append(received)
        months[f"{received:%Y-%m}"] += 1

        domain = sender.rsplit("@", 1)[-1] if "@" in sender else ""
        if domain == INTERNAL_DOMAIN:
            summary.internal_count += 1
        elif domain:
            summary.external_count += 1
            domains[domain] += 1

        recipients = f"{to};{cc}".lower()
        if "control@" in recipients:
            summary.copied_to_control += 1

        if progress and summary.total % 500 == 0:
            progress(summary.total, count)

    if timestamps:
        summary.earliest = min(timestamps).strftime("%d-%b-%Y")
        summary.latest = max(timestamps).strftime("%d-%b-%Y")
    summary.top_senders = senders.most_common(15)
    summary.by_month = dict(sorted(months.items()))
    summary.external_domains = domains.most_common(15)
    summary.attachment_types = dict(extensions.most_common(15))
    return rows, summary


def run_outlook_scan(namespace, mailbox: str, folder_names: list[str],
                     out_dir: Path, *, limit: int | None = None,
                     progress=None) -> list[ScanSummary]:
    """Scan the named folders of a mailbox; write metadata and summaries."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    transport = OutlookTransport(mailbox, namespace=namespace)

    # Resolve the store once, then pick folders by name from it.
    store = None
    for candidate in namespace.Folders:
        address = transport._smtp_of_store(candidate)
        if address == mailbox.lower():
            store = candidate
            break
    if store is None:
        from .. import HaltError
        raise HaltError(f"mailbox {mailbox} is not in this Outlook profile")

    summaries: list[ScanSummary] = []
    safe_mailbox = mailbox.replace("@", "_at_").replace(".", "_")
    jsonl_path = out_dir / f"outlook-scan-{safe_mailbox}.jsonl"

    with jsonl_path.open("w", encoding="utf-8") as f:
        for folder in store.Folders:
            name = str(getattr(folder, "Name", ""))
            if folder_names and name not in folder_names:
                continue
            rows, summary = scan_folder(folder, mailbox=mailbox, folder_name=name,
                                        limit=limit, progress=progress)
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            summaries.append(summary)

    report_path = out_dir / f"OUTLOOK-SCAN-{safe_mailbox}.md"
    report_path.write_text(_render(summaries, mailbox), encoding="utf-8")
    return summaries


def _render(summaries: list[ScanSummary], mailbox: str) -> str:
    lines = [f"# Outlook scan — {mailbox}", "",
             "Metadata only: no message body was read (§12.1.2).", ""]
    for s in summaries:
        lines += [
            f"## {s.folder}",
            "",
            f"- messages: {s.total}" + (f" (+{s.skipped_non_mail} non-mail items skipped)"
                                        if s.skipped_non_mail else ""),
            f"- date range: {s.earliest or 'n/a'} to {s.latest or 'n/a'}",
            f"- with attachments: {s.with_attachments}",
            f"- internal senders: {s.internal_count} | external senders: {s.external_count}",
            f"- copied to control@: {s.copied_to_control}"
            + (f" ({s.copied_to_control / s.total:.0%} of traffic)" if s.total else ""),
            "",
            "### Top senders", "",
        ]
        lines += [f"- {addr or '(unknown)'}: {n}" for addr, n in s.top_senders] or ["- none"]
        lines += ["", "### External domains", ""]
        lines += [f"- {d}: {n}" for d, n in s.external_domains] or ["- none"]
        lines += ["", "### Attachment types", ""]
        lines += [f"- .{ext}: {n}" for ext, n in s.attachment_types.items()] or ["- none"]
        lines += ["", "### Volume by month", ""]
        lines += [f"- {month}: {n}" for month, n in s.by_month.items()] or ["- none"]
        lines.append("")
    return "\n".join(lines)
