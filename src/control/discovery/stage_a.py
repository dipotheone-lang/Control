"""Stage A — mail archives (charter §6).

Find .pst/.ost/.msg/.eml/.mbox under the given roots; parse what the
standard library can parse (.eml, .mbox) from a COPY, never the original;
record everything else as present-but-not-parsed with the reason. Rules:

- Always parse a copy (an .ost may be locked by a running Outlook).
- Password-protected or corrupt files are recorded as inaccessible;
  never attempt to bypass protection.
- .pst/.ost need libpff/pypff and .msg needs extract-msg; when the
  library is absent the archive is indexed with a `requires` reason so
  DISCOVERY-LIMITATIONS.md can list it honestly.
"""

import csv
import email
import email.policy
import email.utils
import json
import mailbox
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path

ARCHIVE_KINDS = {
    ".pst": "pst",
    ".ost": "ost",
    ".msg": "msg",
    ".eml": "eml",
    ".mbox": "mbox",
}


@dataclass
class ArchiveRecord:
    path: str
    kind: str
    size_bytes: int
    parsed: bool = False
    message_count: int = 0
    reason: str = ""


@dataclass
class MessageMeta:
    """Metadata only — bodies are not extracted at this stage. Stage A
    maps the correspondence landscape; content extraction happens later,
    under the §12.1 confidentiality rules."""

    archive: str
    sender: str = ""
    to: str = ""
    cc: str = ""
    date: str = ""
    subject: str = ""
    message_id: str = ""
    attachments: list[str] = field(default_factory=list)


def find_mail_archives(roots: list[Path]) -> list[ArchiveRecord]:
    records: list[ArchiveRecord] = []
    seen: set[Path] = set()
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            kind = ARCHIVE_KINDS.get(path.suffix.lower())
            if kind is None:
                continue
            real = path.resolve()
            if real in seen:
                continue
            seen.add(real)
            records.append(
                ArchiveRecord(path=str(path), kind=kind, size_bytes=path.stat().st_size)
            )
    return records


def _meta_from_message(msg: email.message.Message, archive: str) -> MessageMeta:
    attachments = []
    for part in msg.walk():
        filename = part.get_filename()
        if filename:
            attachments.append(filename)
    return MessageMeta(
        archive=archive,
        sender=str(msg.get("From", "")),
        to=str(msg.get("To", "")),
        cc=str(msg.get("Cc", "")),
        date=str(msg.get("Date", "")),
        subject=str(msg.get("Subject", "")),
        message_id=str(msg.get("Message-ID", "")),
        attachments=attachments,
    )


def parse_archive(record: ArchiveRecord, workdir: Path) -> list[MessageMeta]:
    """Parse a COPY of the archive. Mutates `record` with the outcome.
    Never raises on bad input — a corrupt archive is a recorded fact."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    source = Path(record.path)

    if record.kind in ("pst", "ost"):
        note = "requires libpff/pypff — indexed, not parsed"
        if record.kind == "ost":
            note += "; .ost is locked while Outlook runs — export to .pst or use Graph"
        record.reason = note
        return []
    if record.kind == "msg":
        record.reason = "requires extract-msg — indexed, not parsed"
        return []

    try:
        copy_path = workdir / source.name
        shutil.copy2(source, copy_path)
    except OSError as e:
        record.reason = f"copy failed: {e}"
        return []

    try:
        if record.kind == "eml":
            with copy_path.open("rb") as f:
                msg = email.message_from_binary_file(f, policy=email.policy.default)
            metas = [_meta_from_message(msg, record.path)]
        else:  # mbox
            box = mailbox.mbox(str(copy_path))
            metas = [_meta_from_message(m, record.path) for m in box]
            box.close()
    except Exception as e:  # corrupt input is data, not a crash
        record.reason = f"unparseable: {e.__class__.__name__}: {e}"
        return []
    finally:
        copy_path.unlink(missing_ok=True)

    if record.kind == "eml" and not metas[0].sender and not metas[0].subject:
        record.reason = "unparseable: no recognisable mail headers"
        return []

    record.parsed = True
    record.message_count = len(metas)
    return metas


def run_stage_a(roots: list[Path], out_dir: Path) -> dict:
    """Index and parse all archives; write outputs to discovery/."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir = out_dir / ".stage-a-work"

    records = find_mail_archives(roots)
    messages: list[MessageMeta] = []
    for record in records:
        messages.extend(parse_archive(record, workdir))
    shutil.rmtree(workdir, ignore_errors=True)

    with (out_dir / "mail-archive-index.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["path", "kind", "size_bytes", "parsed", "message_count", "reason"]
        )
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))

    with (out_dir / "mail-messages.jsonl").open("w", encoding="utf-8") as f:
        for meta in messages:
            f.write(json.dumps(asdict(meta), ensure_ascii=False) + "\n")

    unparsed = [r for r in records if not r.parsed]
    return {
        "archives_found": len(records),
        "archives_parsed": sum(1 for r in records if r.parsed),
        "messages_indexed": len(messages),
        "limitations": [f"{r.path}: {r.reason}" for r in unparsed],
    }
