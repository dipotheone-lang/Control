"""Delegated limits read out of the delegation documents — O-02, §3.2.

D-06 put the authority thresholds on an interim itemise-everything
position on 16-Aug-2026, with a review due **16-Sep-2026**, and gave the
reason plainly: observe a month of real commitment volume so the numbers
come from evidence rather than estimate.

That month produced no volume. Control is in Phase 0 and has recorded no
transactions, so on 16-Sep the review arrives with exactly the evidence
it started with, and the choice becomes extend the interim again or pick
numbers out of the air. There is a third option, and it was on the drive
the whole time: `13. Delegations` holds the company's own delegation of
authority documents.

**This proposes; it never applies.** §14.2 puts authority limits in Tier
C — *"never applied by the system, raised with evidence for human
decision"* — and §10 makes anything touching authority a Never in every
mode. So the output is a worksheet and a proposal file. `authority.yaml`
is edited by a human or not at all.

**It extracts amounts, not attributions.** A delegation document names a
role — "the Head of Procurement" — and mapping that to an address is a
judgement about who holds what authority, which is the substance of the
decision rather than a step towards it. Every candidate carries the
phrase it was read from and the document it came from, and the holder
column is left for the CEO. Guessing it would put a fabricated authority
limit into the check that decides whether a commitment needed a second
signature (§7.3 S2).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

# Money as this company writes it. The currency is captured rather than
# assumed: §5.2 requires a currency code on every monetary field, and a
# limit read as EGP when the document said USD is a control that passes
# transactions it should stop.
_AMOUNT = re.compile(
    r"(?i)\b(EGP|LE|L\.E\.|USD|EUR|جنيه|دولار)?\s*"
    r"(\d{1,3}(?:[,\s]\d{3})+|\d{4,12})(?:\.\d{1,2})?\s*"
    r"(EGP|LE|L\.E\.|USD|EUR|جنيه|دولار|ألف|مليون)?")

# The phrases that make an amount a limit rather than a price.
_AUTHORITY = re.compile(
    r"(?i)(up to|not exceeding|shall not exceed|maximum of|limit of|"
    r"within a limit|authori[sz]ed to approve|may approve|approval limit|"
    r"delegat\w*|صلاحية|حد أقصى|بحد أقصى|لا يتجاوز|حتى مبلغ|تفويض)")

_CURRENCY = {
    "le": "EGP", "l.e.": "EGP", "egp": "EGP", "جنيه": "EGP",
    "usd": "USD", "دولار": "USD", "eur": "EUR",
}

# How near an amount must sit to an authority phrase to be one.
_WINDOW = 160


@dataclass
class Candidate:
    amount: float
    currency: str
    phrase: str            # the authority wording, for the CEO to read
    source: str            # document, relative
    holder: str = ""       # never inferred — the CEO fills this


@dataclass
class Proposal:
    candidates: list = field(default_factory=list)
    documents_read: int = 0
    documents_with_no_amount: int = 0


def _currency_of(before: str, after: str) -> str:
    for token in (before or "", after or ""):
        code = _CURRENCY.get(str(token).strip().lower())
        if code:
            return code
    return ""


def extract(text: str, source: str) -> list[Candidate]:
    """Amounts that sit inside an authority statement.

    An amount alone is a number in a contract. An amount inside "may
    approve up to" is a delegated limit, and the difference is the only
    thing that makes this worth reading at all.
    """
    found: list[Candidate] = []
    seen: set[tuple] = set()
    for match in _AMOUNT.finditer(text):
        digits = match.group(2).replace(",", "").replace(" ", "")
        try:
            amount = float(digits)
        except ValueError:
            continue
        # A year is not a limit, and a delegation document is full of
        # them. Four digits in the plausible-year range with no currency
        # beside it is almost always a date.
        currency = _currency_of(match.group(1), match.group(3))
        if not currency and 1900 <= amount <= 2100:
            continue
        if amount < 1000:
            continue

        start = max(0, match.start() - _WINDOW)
        window = text[start:match.end() + _WINDOW]
        authority = _AUTHORITY.search(window)
        if not authority:
            continue

        key = (amount, currency)
        if key in seen:
            continue
        seen.add(key)
        found.append(Candidate(
            amount=amount, currency=currency or "NOT STATED",
            phrase=" ".join(window.split())[:200], source=source))
    return found


def render(proposal: Proposal, today) -> str:
    lines = [
        f"# PROPOSED AUTHORITY LIMITS — {today:%d-%b-%Y}",
        "",
        "Read out of the delegation documents on the drive, for the **O-02 "
        "review due 16-Sep-2026**.",
        "",
        "**Nothing here is in force.** §14.2 puts authority limits in Tier C "
        "— never applied by the system, raised with evidence for human "
        "decision — and §10 makes anything touching authority a Never in "
        "every mode. `config/authority.yaml` is edited by a person or not "
        "at all.",
        "",
        f"{proposal.documents_read} document(s) read, "
        f"{len(proposal.candidates)} candidate limit(s) found.",
        "",
        "## What D-06 was waiting for, and why it did not arrive",
        "",
        "D-06 set the interim on 16-Aug-2026 to observe one month of real "
        "commitment volume, so the thresholds would come from evidence "
        "rather than estimate. Control is in Phase 0 and has recorded no "
        "transactions, so that month produced no volume. On 16-Sep the "
        "review would otherwise arrive with the evidence it started with "
        "(§1.1). These documents are the company's own answer to the same "
        "question, and they predate the interim.",
        "",
    ]

    if not proposal.candidates:
        lines += [
            "## No candidate limits found",
            "",
            "No amount on the drive sits inside an authority statement — "
            "\"up to\", \"not exceeding\", \"may approve\", \"تفويض\", "
            "\"حد أقصى\". That is a finding about the documents, not a "
            "reading of them: either the delegation documents state roles "
            "without values, or they are scans the OCR floor rejected "
            "(§5.5). Both are answerable, and neither is an empty result.",
            "",
        ]
    else:
        lines += [
            "## Candidate limits",
            "",
            "**The holder column is deliberately empty.** A delegation "
            "document names a role — \"the Head of Procurement\" — and "
            "mapping that to an address is a judgement about who holds what "
            "authority, which is the substance of this decision rather than "
            "a step towards it. A guessed holder would put a fabricated "
            "limit into the check that decides whether a commitment needed "
            "a second signature (§7.3 S2).",
            "",
            "| amount | currency | holder (you) | read from | document |",
            "|---|---|---|---|---|",
        ]
        for item in sorted(proposal.candidates,
                           key=lambda c: -c.amount)[:60]:
            phrase = item.phrase.replace("|", "/")[:120]
            lines.append(f"| {item.amount:,.0f} | {item.currency} |  | "
                         f"{phrase} | {item.source} |")
        lines.append("")

    lines += [
        "## To put a number into force",
        "",
        "Edit `config/authority.yaml` by hand: `thresholds."
        "ceo_weekly_itemisation`, `thresholds.second_approval_above`, and "
        "`delegated_limits` per address. Then set `interim.active: false`.",
        "",
        "Until then the zero threshold stands and every commitment is "
        "itemised — the conservative default is the operative one, not a "
        "switched-off control (§3.2).",
        "",
        "**A currency of NOT STATED is not a detail.** §5.2 requires a "
        "currency code on every monetary field, and a limit read as EGP "
        "when the document said USD is a control that passes the "
        "transactions it exists to stop.",
    ]
    return "\n".join(lines)


def to_yaml(proposal: Proposal, today) -> str:
    import yaml

    header = [
        f"# PROPOSED AUTHORITY LIMITS — {today:%d-%b-%Y}",
        "#",
        "# NOT IN FORCE. §14.2 Tier C: authority limits are never applied by",
        "# the system. Copy a value into config/authority.yaml by hand, with",
        "# the holder you decide — this file names none, because attributing",
        "# a limit to a person is the decision itself (§7.3 S2).",
        "",
    ]
    rows = [{"amount": c.amount, "currency": c.currency, "holder": "",
             "read_from": c.phrase, "document": c.source}
            for c in sorted(proposal.candidates, key=lambda c: -c.amount)]
    body = yaml.safe_dump({"candidate_limits": rows}, allow_unicode=True,
                          sort_keys=False) if rows else "candidate_limits: []\n"
    return "\n".join(header) + body
