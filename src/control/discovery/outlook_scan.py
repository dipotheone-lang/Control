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

from ..outlook import OutlookTransport, is_mail_item, safe_get

INTERNAL_DOMAIN = "ubcsis.com"

# Folder naming is not portable. Exchange says "Sent Items", Gmail over
# IMAP nests "[Gmail]/Sent Mail", other clients say "Sent". Asking for
# "Sent Items" and silently matching nothing is how a scan reports every
# thread as unanswered while the replies sit in a folder it never opened.
FOLDER_ALIASES = {
    "inbox": ("inbox", "البريد الوارد"),
    "sent items": ("sent items", "sent", "sent mail", "sentitems",
                   "sent messages", "العناصر المرسلة", "المرسلة"),
    "drafts": ("drafts", "المسودات"),
    "deleted items": ("deleted items", "trash", "bin"),
}


def folder_matches(name: str, path: str, requested: list[str]) -> bool:
    """True when a folder satisfies one of the requested names."""
    name_l, path_l = (name or "").lower(), (path or "").lower()
    for request in requested:
        request_l = request.lower().strip()
        if not request_l:
            continue
        candidates = set(FOLDER_ALIASES.get(request_l, ()))
        candidates.add(request_l)
        if name_l in candidates or path_l in candidates:
            return True
        # Nested stores: "[Gmail]/Sent Mail" satisfies "Sent Items".
        if any(path_l.endswith(f"/{c}") for c in candidates):
            return True
    return False


@dataclass
class ScanSummary:
    mailbox: str
    folder: str
    total: int = 0
    skipped_non_mail: int = 0
    unreadable_items: int = 0
    attachments_unreadable: int = 0
    not_found: bool = False
    available_folders: list = field(default_factory=list)
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
                limit: int | None = None, progress=None,
                redact_subjects: bool = False,
                sink=None) -> tuple[list[dict], ScanSummary]:
    """Walk every item in a folder, collecting metadata only.

    redact_subjects drops subject lines from the output. Subjects are
    metadata, but in an HR mailbox a subject alone can disclose a
    termination, a grievance or a medical matter — sensitive personal
    data under PDPL (§12.2). Cadence and volume analysis does not need
    them, so for those mailboxes they are simply not collected."""
    summary = ScanSummary(mailbox=mailbox, folder=folder_name)
    rows: list[dict] = []
    senders: Counter = Counter()
    months: Counter = Counter()
    domains: Counter = Counter()
    extensions: Counter = Counter()
    timestamps: list[datetime] = []

    items = folder.Items
    if limit:
        # A capped run is a sample, and the useful sample is the recent
        # end: current cadence, current senders. Without this the cap
        # silently returns the oldest N in folder order.
        try:
            items.Sort("[ReceivedTime]", True)
        except Exception:
            pass
    count = int(getattr(items, "Count", 0) or 0)
    if limit:
        count = min(count, limit)

    for index in range(1, count + 1):
        # One unreadable item must never end a 10,000-item scan. Every
        # per-item failure is counted and reported, never silently
        # dropped and never fatal (§1.1, §13.2).
        try:
            item = items.Item(index)
        except Exception:
            summary.unreadable_items += 1
            continue
        if not is_mail_item(item):
            summary.skipped_non_mail += 1
            continue

        try:
            sender = OutlookTransport._sender_address(item).lower()
            received = OutlookTransport._received_at(item)
            to = str(safe_get(item, "To"))
            cc = str(safe_get(item, "CC"))

            attachment_names: list[str] = []
            attachments_unreadable = False
            try:
                attachments = item.Attachments
                att_count = int(safe_get(attachments, "Count", 0) or 0)
            except Exception:
                # Cannot tell whether this item has attachments. An empty
                # list would assert "none", which is a filled gap (§1.1).
                attachments, att_count = None, 0
                attachments_unreadable = True
            for i in range(1, att_count + 1):
                try:
                    name = str(safe_get(attachments.Item(i), "FileName"))
                except Exception:
                    attachments_unreadable = True
                    continue
                if name:
                    attachment_names.append(name)
                    if "." in name:
                        extensions[name.rsplit(".", 1)[-1].lower()] += 1

            row = {
                "mailbox": mailbox,
                "folder": folder_name,
                "sender": sender,
                "to": to,
                "cc": cc,
                "received": received.isoformat(),
                "subject": ("[REDACTED]" if redact_subjects
                            else str(safe_get(item, "Subject"))),
                "attachments": attachment_names,
            }
            if attachments_unreadable:
                row["attachments_unreadable"] = True
                summary.attachments_unreadable += 1
        except Exception:
            summary.unreadable_items += 1
            continue

        # Stream to disk when a sink is given: a crash then costs the
        # current item, not the whole run.
        if sink is not None:
            sink(row)
        else:
            rows.append(row)

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
                     progress=None, redact_subjects: bool = False,
                     recurse: bool = False) -> list[ScanSummary]:
    """Scan the named folders of a mailbox; write metadata and summaries.

    An empty folder_names list scans every folder in the store."""
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

    available: list[str] = []

    def walk(folders, prefix=""):
        for folder in folders:
            name = str(getattr(folder, "Name", ""))
            path = f"{prefix}{name}"
            available.append(path)
            if not folder_names or folder_matches(name, path, folder_names):
                yield folder, path
            if recurse:
                children = getattr(folder, "Folders", None)
                if children is not None:
                    yield from walk(children, prefix=f"{path}/")

    with jsonl_path.open("w", encoding="utf-8") as f:
        written = 0

        def sink(row):
            nonlocal written
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
            if written % 200 == 0:
                f.flush()      # survive a crash with the work so far on disk

        matched: list[str] = []
        for folder, path in walk(store.Folders):
            matched.append(path)
            _rows, summary = scan_folder(
                folder, mailbox=mailbox, folder_name=path, limit=limit,
                progress=progress, redact_subjects=redact_subjects, sink=sink,
            )
            f.flush()
            summaries.append(summary)

    # A requested folder that matched nothing is a gap, not silence. The
    # caller must be able to say "Sent Items was not found" rather than
    # reporting every thread unanswered.
    for request in folder_names:
        if not any(folder_matches(Path(p).name, p, [request]) for p in matched):
            summaries.append(ScanSummary(
                mailbox=mailbox,
                folder=f"{request} — NOT FOUND",
                not_found=True,
                available_folders=sorted(set(available))[:40],
            ))

    report_path = out_dir / f"OUTLOOK-SCAN-{safe_mailbox}.md"
    report_path.write_text(_render(summaries, mailbox), encoding="utf-8")
    return summaries


def write_overview(all_summaries: dict[str, list[ScanSummary]], out_dir: Path) -> Path:
    """Consolidated view across mailboxes — the input Phase 0 gate
    decisions actually need (§6 Stage A/H)."""
    out_dir = Path(out_dir)
    lines = [
        "# Mailbox overview — Phase 0 discovery",
        "",
        "Metadata only: no message body was read (§12.1.2).",
        "",
        "| Mailbox | Messages | Range | With attachments | External | Copied to control@ |",
        "|---|---|---|---|---|---|",
    ]
    totals = Counter()
    for mailbox, summaries in all_summaries.items():
        total = sum(s.total for s in summaries)
        attachments = sum(s.with_attachments for s in summaries)
        external = sum(s.external_count for s in summaries)
        copied = sum(s.copied_to_control for s in summaries)
        dates = [s.earliest for s in summaries if s.earliest] + \
                [s.latest for s in summaries if s.latest]
        span = f"{min(dates)} – {max(dates)}" if dates else "n/a"
        lines.append(
            f"| {mailbox} | {total} | {span} | {attachments} | {external} | {copied} |"
        )
        totals["total"] += total
        totals["external"] += external
        totals["copied"] += copied

    lines += [
        "",
        "## What this says about decision O-05 (§3.1a)",
        "",
        f"- external correspondence observed across these mailboxes: **{totals['external']}**",
        f"- of which visible to control@: **{totals['copied']}**",
    ]
    if totals["external"]:
        share = totals["copied"] / totals["external"]
        lines.append(f"- observed coverage: **{share:.1%}**")
        lines.append("")
        lines.append(
            "Under Option A (CC discipline) Control sees only what is copied to "
            "control@. The figure above is the share of external traffic the "
            "system would have been able to watch."
        )
        if totals["copied"] == 0:
            lines += [
                "",
                "> **Read this figure with care.** A coverage of 0% over historical "
                "traffic does **not** measure CC discipline if control@ did not "
                "exist for most of that period — nothing could have been copied to "
                "a mailbox that was not yet in use. Confirm when control@ went "
                "live. If it postdates this traffic, the honest conclusion is that "
                "**no historical baseline exists**, and CC discipline can only be "
                "measured forward from the date staff were asked to copy control@. "
                "Deciding O-05 on this number alone would be deciding on an "
                "artefact (§1.1).",
            ]
    lines += [
        "",
        "## What this scan cannot tell you",
        "",
        "- **Commercial value** in these threads (Stage H item 3) is not in "
        "metadata. It requires reading bodies or attachments, which this scan "
        "deliberately does not do.",
        "- **Unanswered threads beyond SLA** (Stage H item 2) needs reply "
        "matching across Inbox and Sent Items; run the scan over both folders "
        "before drawing that conclusion.",
        "- Anything in a mailbox not present in this Outlook profile is "
        "invisible here and must be listed as a gap, not assumed empty (§1.1).",
        "",
    ]
    path = out_dir / "MAILBOX-OVERVIEW.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _render(summaries: list[ScanSummary], mailbox: str) -> str:
    lines = [f"# Outlook scan — {mailbox}", "",
             "Metadata only: no message body was read (§12.1.2).", ""]
    for s in summaries:
        lines += [
            f"## {s.folder}",
            "",
            f"- messages: {s.total}"
            + (f" (+{s.skipped_non_mail} non-mail items skipped)"
               if s.skipped_non_mail else "")
            + (f" (+{s.unreadable_items} unreadable — listed as a gap)"
               if s.unreadable_items else ""),
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
