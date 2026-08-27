"""Stage C terms to proposed class 2 register rows — §2.2, §6.

The gap this closes. `contracts` wrote `COMMERCIAL-EXPOSURE.md` and
stopped. The alerts — 60 / 30 / 14 / 7 days on a guarantee, and on
retention release dates — are driven by the class 2 *registers*, which
are populated by `registers --import-file` from a YAML nobody produced.
So a guarantee expiry Stage C found sat in a markdown file and alerted
on nothing unless a person hand-transcribed it. §6 calls that report
the likely highest-value single output of the build; it was an output
with no wire to anything.

**Proposing is inference; importing is the decision.** This module only
writes a file. `registers --import-file` is a separate deliberate act
naming that file, and that act is the approval — the same split as the
obligation register (§6), for the same reason: acting on a Stage D or
Stage C inference is acting on an inference (§1.1).

**What is deliberately NOT proposed.** A register row is proposed only
when every column the schema requires comes from evidence. The rest are
listed with the exact field that is missing and why, because a row
invented to satisfy a NOT NULL constraint is a fabrication that then
alerts (§2.1: a confident wrong date is worse than no date).

Three cases account for nearly all of it:

- **Confidential guarantees (D-05).** The date is extracted; the clause
  text is redacted at capture, so the *instrument type* — performance
  bond, advance payment guarantee, bid bond — is not recoverable, and
  the schema requires one of five exact values. Guessing would put a
  fabricated instrument type in the register of the company's largest
  clients. A human names it.
- **Dates already passed.** A 2023 expiry found in a 2021 document is
  most likely a discharged instrument. Importing it as OPEN would fill
  the horizon with stale alerts and teach people to skim it, which
  §13.3 rates a failed control. Listed for status confirmation instead.
- **Terms with no date at all.** Notice periods and LD caps are
  durations running from an event, not calendar dates. They belong on a
  contract row, which needs a client this module cannot infer from a
  file path without guessing.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import PurePosixPath

# The matched phrase decides the instrument type. Ordered: "advance
# payment guarantee" contains "guarantee", so the specific reading has
# to be tried before the general one.
_INSTRUMENT_TYPES = (
    ("advance payment guarantee", "ADVANCE_PAYMENT_GUARANTEE"),
    ("performance bond", "PERFORMANCE_BOND"),
    ("bid bond", "BID_BOND"),
    ("letter of guarantee", "LETTER_OF_GUARANTEE"),
    ("bank guarantee", "LETTER_OF_GUARANTEE"),
    ("خطاب ضمان", "LETTER_OF_GUARANTEE"),
)

_REDACTED = "[REDACTED"


@dataclass
class Proposal:
    rows: dict = field(default_factory=dict)      # register name -> [row]
    blocked: list = field(default_factory=list)   # {source, kind, date, reason}

    @property
    def count(self) -> int:
        return sum(len(v) for v in self.rows.values())


def _instrument_type(term_text: str) -> str:
    """From the matched phrase, never from the context window.

    The window spans neighbouring clauses by design — it is the citation
    — so reading the type out of it labelled the Delta Steel performance
    bond ADVANCE_PAYMENT_GUARANTEE, because the next sentence mentioned
    one. Same disease as a date crossing a clause boundary, one field
    over.
    """
    lowered = str(term_text or "").lower()
    for phrase, kind in _INSTRUMENT_TYPES:
        if phrase in lowered:
            return kind
    return ""


def _reference(source: str) -> str:
    """A stable human-recognisable reference for the document.

    The file name, not a generated id: whoever reviews this has to find
    the document again, and `INS-0007` does not help them.
    """
    return PurePosixPath(str(source).replace("\\", "/")).stem[:80]


def _project(source: str) -> str:
    parts = PurePosixPath(str(source).replace("\\", "/")).parts
    return parts[0] if len(parts) > 1 else ""


def propose(terms, today: date) -> Proposal:
    """Class 2 register rows from Stage C terms.

    `terms` are `CommercialTerm`s. Only guarantees with a future date
    and a recoverable instrument type become rows; everything else is
    reported with its reason.
    """
    proposal = Proposal()
    instruments: dict[tuple, dict] = {}

    for term in terms:
        entry = {"source": term.source, "kind": term.kind,
                 "date": term.found_date}

        if term.kind != "GUARANTEE_EXPIRY":
            proposal.blocked.append({
                **entry,
                "reason": f"{term.kind} is not an instrument row. A dated "
                          "contract term belongs on a contract row, which "
                          "needs a client this cannot read from a file path "
                          "without guessing",
            })
            continue

        if not term.found_date:
            proposal.blocked.append({
                **entry,
                "reason": "no date in the clause — nothing to alert on. The "
                          "guarantee exists in the document; its expiry has "
                          "to be read by a person",
            })
            continue

        instrument_type = _instrument_type(term.term_text)
        if not instrument_type:
            redacted = str(term.context or "").startswith(_REDACTED)
            proposal.blocked.append({
                **entry,
                "reason": (
                    "instrument type not recoverable — the clause text is "
                    "redacted under D-05, so which guarantee this is cannot "
                    "be known without opening a confidential document. Name "
                    "it and import manually"
                    if redacted else
                    "instrument type not recognised in the clause. The "
                    "schema requires one of PERFORMANCE_BOND, "
                    "ADVANCE_PAYMENT_GUARANTEE, BID_BOND, "
                    "LETTER_OF_GUARANTEE, INSURANCE_POLICY, RETENTION"),
            })
            continue

        if term.found_date < today.isoformat():
            proposal.blocked.append({
                **entry,
                "reason": "expiry already passed — most likely a discharged "
                          "instrument. Importing it as OPEN would fill the "
                          "horizon with stale alerts. Confirm the status and "
                          "import as RELEASED or EXPIRED, or not at all",
            })
            continue

        reference = _reference(term.source)
        key = (reference, instrument_type, term.found_date)
        if key in instruments:
            continue
        instruments[key] = {
            "instrument_ref": reference,
            "instrument_type": instrument_type,
            "expiry_date": term.found_date,
            "project_ref": _project(term.source),
            "status": "OPEN",
            # §5.2: every row records where it came from. These are read
            # out of historical documents on the drive, not received
            # live, and the distinction is the difference between a fact
            # and a reconstruction.
            "source": "BACKFILL",
        }

    _disambiguate(instruments.values())
    if instruments:
        proposal.rows["instruments"] = sorted(
            instruments.values(), key=lambda r: r["expiry_date"])
    return proposal


def _disambiguate(rows) -> None:
    """Make `instrument_ref` unique, because the register keys on it.

    The reference started as the document's file name, and one supply
    agreement naming both a performance bond and an advance payment
    guarantee produced two rows under one reference. `registers.current`
    keeps one current row per key, so the register accepted both and the
    horizon showed one: a guarantee expiry silently gone from the
    register that exists to alert on it — §1.1's worst shape, and §2.2's
    most expensive class of miss.

    The file name alone stays the reference wherever it is already
    unique, because whoever reviews this has to find the document again.
    Only the colliding ones are extended, and by their own type and
    expiry rather than a counter, so the same document scanned again
    produces the same references.
    """
    seen: dict[str, int] = {}
    for row in rows:
        seen[row["instrument_ref"]] = seen.get(row["instrument_ref"], 0) + 1
    for row in rows:
        if seen[row["instrument_ref"]] > 1:
            kind = row["instrument_type"].replace("_", " ").lower()
            row["instrument_ref"] = (
                f"{row['instrument_ref']} · {kind} {row['expiry_date']}")


def to_yaml(proposal: Proposal, today: date) -> str:
    """The import file, with its own provenance written into it.

    Comments survive because this is rendered rather than dumped: a
    reviewer opening the file has to see that these are inferences and
    what importing them does, not just a list of rows.
    """
    import yaml

    header = [
        f"# PROPOSED CLASS 2 REGISTER ROWS — {today:%d-%b-%Y}",
        "#",
        "# Inferred by Stage C from documents on the drive. NOTHING HERE IS",
        "# IN A REGISTER YET. Importing is the decision, and it is a",
        "# separate deliberate act:",
        "#",
        "#   python -m control registers --import-file <this file>",
        "#",
        "# Review before importing. Every row alerts once imported — §2.2",
        "# schedules guarantees at 60 / 30 / 14 / 7 days — and the register",
        "# is append-only (§5.2), so a wrong row is corrected by another",
        "# row, never erased. Delete a line here rather than fix it there.",
        "#",
        "# Each row's expiry was read from the clause that names the",
        "# instrument. Rows that could NOT be proposed are listed in",
        "# PROPOSED-CLASS2-REGISTERS.md alongside, each with the field that",
        "# is missing — that list is the finding, not the leftovers (§1.1).",
        "",
    ]
    body = yaml.safe_dump(proposal.rows or {}, allow_unicode=True,
                          sort_keys=False) if proposal.rows else "{}\n"
    return "\n".join(header) + body


def render(proposal: Proposal, today: date) -> str:
    """What could not be proposed, and what each one needs."""
    lines = [
        f"# PROPOSED CLASS 2 REGISTER ROWS — {today:%d-%b-%Y}",
        "",
        f"**{proposal.count} row(s) ready to import**, "
        f"**{len(proposal.blocked)} term(s) that cannot become a row "
        "without a person.**",
        "",
        "Stage C reads documents. This turns what it read into register "
        "rows — but only where every column the schema requires comes "
        "from evidence. A row invented to satisfy a NOT NULL constraint "
        "is a fabrication that then alerts (§1.1, §2.1).",
        "",
        "To import the ready rows:",
        "",
        "    python -m control registers --import-file "
        "discovery/PROPOSED-CLASS2-REGISTERS.yaml",
        "",
    ]

    for register, rows in (proposal.rows or {}).items():
        lines += [f"## Ready to import — {register} ({len(rows)})", "",
                  "| expiry | type | reference | project |",
                  "|---|---|---|---|"]
        for row in rows:
            lines.append(f"| {row['expiry_date']} | {row['instrument_type']} | "
                         f"{row['instrument_ref']} | {row.get('project_ref', '')} |")
        lines.append("")

    if not proposal.rows:
        lines += ["## Ready to import — none", "",
                  "No term in the scan carried both a future date and an "
                  "instrument type the schema recognises. That is a finding "
                  "about the documents, not about the scan — read the list "
                  "below for which of the two was missing.", ""]

    lines += [f"## Could not be proposed — {len(proposal.blocked)}", ""]
    if not proposal.blocked:
        lines += ["None.", ""]
        return "\n".join(lines)

    grouped: dict[str, list] = {}
    for item in proposal.blocked:
        grouped.setdefault(item["reason"], []).append(item)

    for reason, items in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        lines += [f"### {len(items)} — {reason}", "",
                  "| kind | date | source |", "|---|---|---|"]
        for item in items[:40]:
            lines.append(f"| {item['kind']} | {item['date'] or '—'} | "
                         f"{item['source']} |")
        if len(items) > 40:
            lines.append(f"| … | | {len(items) - 40} more |")
        lines.append("")
    return "\n".join(lines)
