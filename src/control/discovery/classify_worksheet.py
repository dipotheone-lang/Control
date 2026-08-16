"""Confidentiality classification worksheet — decision O-04, Stage I.

486 external domains cannot be classified from a summary table, and
they should not be: §12.1.1 makes each one a judgement with asymmetric
cost — a misclassification toward confidential costs a check, away from
it costs a client relationship.

This produces a worksheet the CEO can actually work through: every
domain, with the evidence needed to judge it (volume, date range,
direction, whether attachments flow), a proposed classification, and a
blank column for the decision. `apply_worksheet` reads the answers back
into `config/confidential.yaml`.

Nothing here decides anything. Domains stay at the conservative default
until a human writes in the column (§12.1.1).

Known limitation, stated rather than hidden: Outlook exposes `To` and
`CC` as display names in many profiles, so the outbound count is a lower
bound — it counts only recipients that resolved to an address. Inbound
counts come from the sender address and are reliable.
"""

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

INTERNAL_DOMAIN = "ubcsis.com"
VALID_DECISIONS = ("CONFIDENTIAL", "NOT_CONFIDENTIAL", "")

# Hints only. A name match is not a contract, and the worksheet says so.
KNOWN_CLIENT_HINTS = {
    "siemens": "Siemens Energy", "saint-gobain": "Saint-Gobain",
    "saintgobain": "Saint-Gobain", "knauf": "KNAUF",
    "galaxy": "Galaxy Chemicals", "canalsugar": "Canal Sugar",
    "canal-sugar": "Canal Sugar", "sukari": "Sukari Gold Mines",
    "airliquide": "Air Liquide", "air-liquide": "Air Liquide",
    # Confirmed as active clients on 16-Aug-2026 from Phase 0 evidence.
    # None were in the charter's §12.1.1 list.
    "enova": "Enova", "suezsteel": "Suez Steel", "suez-steel": "Suez Steel",
    "lafarge": "Lafarge", "ivldhunseri": "IVL Dhunseri",
    "dhunseri": "IVL Dhunseri", "fertiglobe": "Fertiglobe",
}


def client_hints_from_config(config: dict | None) -> dict[str, str]:
    """Derive hints from the confirmed client list.

    Preferred over the constant above, so adding a client to
    confidential.yaml does not silently leave the worksheet proposing
    NOT_CONFIDENTIAL for its domains.
    """
    hints = dict(KNOWN_CLIENT_HINTS)
    for client in (config or {}).get("confidential_clients") or []:
        name = client.get("name")
        if not name:
            continue
        for domain in client.get("domains") or []:
            hints[str(domain).lower()] = name
    return hints


# Domains that are infrastructure, not counterparties.
NOISE_HINTS = ("google.com", "googlemail.com", "microsoft.com", "outlook.com",
               "linkedin.com", "facebook.com", "no-reply", "noreply",
               "mailchimp", "sendgrid", "amazonses")


@dataclass
class DomainRow:
    domain: str
    messages: int = 0
    inbound: int = 0
    outbound: int = 0
    with_attachments: int = 0
    first_seen: str = ""
    last_seen: str = ""
    mailboxes: set = field(default_factory=set)
    matched_client: str = ""
    proposed: str = ""
    note: str = ""


def build_rows(scan_rows: list[dict],
               client_hints: dict[str, str] | None = None) -> list[DomainRow]:
    by_domain: dict[str, DomainRow] = {}
    timestamps: dict[str, list[datetime]] = defaultdict(list)

    for row in scan_rows:
        sender = (row.get("sender") or "").lower()
        recipients = f"{row.get('to', '')};{row.get('cc', '')}".lower()
        sender_domain = sender.rsplit("@", 1)[-1] if "@" in sender else ""

        # A domain is a counterparty whether it wrote to us or we to it.
        domains = set()
        if sender_domain and not sender_domain.endswith(INTERNAL_DOMAIN):
            domains.add((sender_domain, "in"))
        for part in recipients.replace(",", ";").split(";"):
            part = part.strip()
            if "@" not in part:
                continue
            domain = part.rsplit("@", 1)[-1].strip("<> ")
            if domain and not domain.endswith(INTERNAL_DOMAIN):
                domains.add((domain, "out"))

        directions: dict[str, set[str]] = defaultdict(set)
        for domain, direction in domains:
            directions[domain].add(direction)

        for domain, seen in directions.items():
            entry = by_domain.setdefault(domain, DomainRow(domain=domain))
            # One message counts once per domain, however many of its
            # addresses appear on it.
            entry.messages += 1
            if "in" in seen:
                entry.inbound += 1
            if "out" in seen:
                entry.outbound += 1
            if row.get("attachments"):
                entry.with_attachments += 1
            if row.get("mailbox"):
                entry.mailboxes.add(row["mailbox"])
            try:
                timestamps[domain].append(datetime.fromisoformat(row["received"]))
            except (KeyError, TypeError, ValueError):
                pass

    for domain, entry in by_domain.items():
        stamps = timestamps.get(domain) or []
        if stamps:
            entry.first_seen = min(stamps).strftime("%Y-%m-%d")
            entry.last_seen = max(stamps).strftime("%Y-%m-%d")
        hints = KNOWN_CLIENT_HINTS if client_hints is None else client_hints
        entry.matched_client = next(
            (name for hint, name in hints.items() if hint in domain), "")
        if entry.matched_client:
            entry.proposed = "CONFIDENTIAL"
            entry.note = f"matches confirmed client {entry.matched_client}"
        elif any(hint in domain for hint in NOISE_HINTS):
            entry.proposed = "NOT_CONFIDENTIAL"
            entry.note = "platform/infrastructure, not a counterparty"
        else:
            entry.proposed = "CONFIDENTIAL"
            entry.note = "unclassified — conservative default (§12.1.1)"

    return sorted(by_domain.values(), key=lambda r: -r.messages)


def write_worksheet(rows: list[DomainRow], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "domain", "messages", "inbound", "outbound", "with_attachments",
            "first_seen", "last_seen", "seen_in_mailboxes",
            "proposed", "basis", "YOUR_DECISION", "notes",
        ])
        for row in rows:
            writer.writerow([
                row.domain, row.messages, row.inbound, row.outbound,
                row.with_attachments, row.first_seen, row.last_seen,
                "; ".join(sorted(row.mailboxes)),
                row.proposed, row.note, "", "",
            ])
    return path


def read_worksheet(path: Path) -> tuple[dict[str, str], list[str]]:
    """Return {domain: decision} and a list of problems found."""
    decisions: dict[str, str] = {}
    problems: list[str] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        for number, record in enumerate(csv.DictReader(f), 2):
            domain = (record.get("domain") or "").strip().lower()
            if not domain:
                continue
            decision = (record.get("YOUR_DECISION") or "").strip().upper()
            if decision not in VALID_DECISIONS:
                problems.append(
                    f"line {number}: {domain} has {decision!r} — expected "
                    "CONFIDENTIAL, NOT_CONFIDENTIAL, or blank")
                continue
            if decision:
                decisions[domain] = decision
    return decisions, problems


def confidential_domains(config: dict) -> set[str]:
    """Every domain the engine must treat as client-confidential.

    Two sources, unioned deliberately: the per-client lists that predate
    O-04, and the O-04 decisions. A domain named in either is
    confidential; `not_confidential` never subtracts from the client
    lists, because those were set against an NDA and this worksheet was
    not.
    """
    domains = {
        d.lower()
        for client in (config or {}).get("confidential_clients") or []
        for d in client.get("domains") or []
    }
    decided = (config or {}).get("domain_classifications") or {}
    domains |= {d.lower() for d in decided.get("confidential") or []}
    return {d for d in domains if d}


def apply_worksheet(decisions: dict[str, str], config_path: Path,
                    decided_by: str, decided_on: str) -> dict:
    """Write decisions into confidential.yaml.

    A blank decision leaves the domain at the conservative default; it
    is never silently promoted to non-confidential (§12.1.1).
    """
    config_path = Path(config_path)
    original = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(original) or {}

    confidential = sorted(d for d, v in decisions.items() if v == "CONFIDENTIAL")
    not_confidential = sorted(d for d, v in decisions.items()
                              if v == "NOT_CONFIDENTIAL")

    # Where a decided domain belongs to a client already named under
    # §12.1.1, record it against that client too, so the config reads as
    # the NDA does rather than as a flat list.
    for client in data.get("confidential_clients") or []:
        name = (client.get("name") or "").lower()
        attached = set(client.get("domains") or [])
        for domain in confidential:
            matched = next((n for hint, n in KNOWN_CLIENT_HINTS.items()
                            if hint in domain), "")
            if matched and matched.lower() == name:
                attached.add(domain)
        client["domains"] = sorted(attached)

    data["processing"] = "DISABLED"          # D-01 is untouched by this
    data["domain_classifications"] = {
        "decided_by": decided_by,
        "decided_on": decided_on,
        "confidential": confidential,
        "not_confidential": not_confidential,
        "unclassified_default": "CONFIDENTIAL",
    }
    # The file's header carries the D-01 lock in prose. yaml.safe_dump
    # would silently drop it, leaving a config that no longer says why
    # it is what it is.
    config_path.write_text(
        _leading_comment(original)
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    return {"confidential": len(confidential),
            "not_confidential": len(not_confidential)}


def _leading_comment(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        if line.startswith("#") or (not line.strip() and kept):
            kept.append(line)
            continue
        break
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept) + "\n\n" if kept else ""
