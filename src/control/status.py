"""One page of what the runs actually found — for a go/no-go decision.

Everything here already exists somewhere: in the register, the database,
the Stage C cache, the discovery folder, the gate. Scattered across six
outputs it cannot be weighed, and a decision about whether to continue
this project has been resting on a summary of a summary.

So this reads what is on disk and prints the numbers, with nothing
recomputed and nothing scanned. It takes seconds and it starts nothing.

**An absent number and a zero are different facts**, and the difference
decides the question. "No guarantees in the register" reads the same
whether the registers were never populated or the company has none, and
those need opposite responses. Every line below says which it is.

Nothing here recommends. §15 keeps the decision with the CEO and this is
a larger version of the same decision.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class Line:
    label: str
    value: str
    note: str = ""


@dataclass
class Status:
    sections: list = field(default_factory=list)   # (title, [Line])
    scope: str = "FULL"

    def add(self, title: str, lines: list) -> None:
        self.sections.append((title, lines))


def _yaml(path: Path) -> dict:
    import yaml

    if not path.is_file():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:                                   # noqa: BLE001
        return {}


def _obligations(control_root: Path) -> list[Line]:
    rows = _yaml(control_root / "config" / "obligations.yaml").get(
        "obligations") or []
    approved = [r for r in rows if r.get("approved_by_ceo")]
    assigned = [r for r in approved
                if str(r.get("date_basis") or "") == "assigned_by_control"]
    return [
        Line("class 3 obligations in the register", str(len(rows)),
             "none at all" if not rows else ""),
        Line("approved by the CEO", str(len(approved)),
             "§6: an unapproved row is a proposal and tracks nothing"),
        Line("whose deadline Control assigned rather than observed",
             str(len(assigned)),
             "each carries an open_question; correcting one is a line edit"),
    ]


def _statutory(control_root: Path) -> list[Line]:
    # Usability is decided by the engine's own parser, not by a second
    # reading of the same field. A status page that disagrees with the
    # engine about what is tracked is worse than no status page, and the
    # field is `rule` rather than `due` — a detail a re-implementation
    # got wrong on the first attempt.
    from .loader import parse_due

    rules = _yaml(control_root / "config" / "statutory-calendar.yaml").get(
        "obligations") or []
    verified = [r for r in rules if r.get("verified_by_advisor")]
    dated = [r for r in rules
             if parse_due(str(r.get("rule") or ""),
                          str(r.get("cadence") or ""), date.today())[0]
             is not None]
    return [
        Line("class 1 statutory obligations", str(len(rules))),
        Line("with a date Control can count down to", str(len(dated)),
             "the rest fire no countdown — the others are awaiting a date, "
             "event-driven, or have no mechanism yet"),
        Line("confirmed by a tax advisor", str(len(verified)),
             "O-03. CEO-stated dates still alert, erring early — but nobody "
             "qualified has checked them and time passing does not check them"),
    ]


def _registers(control_root: Path) -> list[Line]:
    from .db import connect

    path = control_root / "data" / "control.db"
    if not path.is_file():
        return [Line("database", "NOT CREATED",
                     "no run has reached it — this is absent, not empty")]

    counts, conn = {}, None
    try:
        conn = connect(path)
        for table in ("registers_instruments", "registers_contracts",
                      "registers_accreditations", "registers_tenders",
                      "registers_quotations", "submissions",
                      "external_threads", "anomalies"):
            try:
                counts[table] = conn.execute(
                    f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except Exception:                            # noqa: BLE001
                counts[table] = None
    finally:
        if conn is not None:
            conn.close()

    def show(table: str) -> str:
        value = counts.get(table)
        return "TABLE MISSING" if value is None else str(value)

    return [
        Line("guarantees / bonds / retention rows", show("registers_instruments"),
             "§2.2 alerts these at 60/30/14/7 days — the charter's most "
             "expensive class of miss"),
        Line("contracts", show("registers_contracts")),
        Line("accreditations", show("registers_accreditations"),
             "§2.2: a lapsed prequalification shows up as silence, not "
             "rejection"),
        Line("tenders", show("registers_tenders"),
             "§2.2 calls these the highest-value items in the system"),
        Line("quotations", show("registers_quotations")),
        Line("submissions recorded", show("submissions")),
        Line("external threads tracked", show("external_threads")),
        Line("anomaly flags raised", show("anomalies")),
    ]


def _stage_c(control_root: Path) -> list[Line]:
    cache = control_root / "data" / "stage-c-cache"
    if not cache.is_dir():
        return [Line("Stage C", "NEVER RUN",
                     "no contract scan has completed on this machine")]

    documents = terms = dated = ocr_attempted = ocr_read = 0
    confidential = unreadable = 0
    confidences: list[float] = []
    for entry in cache.glob("*.json"):
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except Exception:                                # noqa: BLE001
            continue
        documents += 1
        rows = payload.get("terms") or []
        terms += len(rows)
        dated += sum(1 for t in rows if t.get("found_date"))
        if payload.get("d05"):
            confidential += 1
        if payload.get("outcome") == "unreadable":
            unreadable += 1
        info = payload.get("ocr") or {}
        if info.get("attempted"):
            ocr_attempted += 1
            if info.get("read"):
                ocr_read += 1
            if info.get("confidence"):
                confidences.append(float(info["confidence"]))

    confidences.sort()
    median = (f"{confidences[len(confidences) // 2]:.1f}" if confidences
              else "no readings")
    return [
        Line("documents scanned", str(documents)),
        Line("commercial terms found", str(terms)),
        Line("of those, carrying a date", str(dated),
             "a term with no date alerts on nothing. This is the number the "
             "class 2 registers are built from"),
        Line("client-confidential contracts read under D-05", str(confidential),
             "dates only, no clause text retained"),
        Line("unreadable even so", str(unreadable)),
        Line("OCR: read / attempted", f"{ocr_read} / {ocr_attempted}",
             f"median confidence {median}; the floor is a decision waiting "
             "(§5.5)"),
    ]


def _governance(control_root: Path) -> list[Line]:
    data = _yaml(control_root / "config" / "acknowledgements.yaml").get(
        "documents") or {}
    lines = []
    for key, title in (("usage_policy", "usage policy"),
                       ("pdpl_notification", "PDPL notification"),
                       ("iwr", "IWR amendment")):
        entry = data.get(key) or {}
        expected = entry.get("expected") or 0
        got = len([a for a in (entry.get("acknowledged_by") or [])
                   if a.get("date")])
        circulated = entry.get("circulated")
        lines.append(Line(
            f"{title} — acknowledged", f"{got} of {expected or '?'}",
            "not circulated yet" if not circulated
            else f"circulated {circulated}"))
    return lines


def _mailbox(control_root: Path) -> list[Line]:
    scope = _yaml(control_root / "config" / "mailbox-scope.yaml")
    state = str(scope.get("state") or "unknown")
    discovery = control_root / "discovery"
    scanned = discovery / "DISCOVERY-REPORT.md"
    return [
        Line("scope state", state,
             "D-07 decided Option C; it takes effect only when O-07, O-08 "
             "and O-10 close"),
        Line("mailbox scan output on disk",
             "yes" if scanned.is_file() else "NONE",
             "if NONE, no scan has completed here — that is absent, not a "
             "quiet mailbox"),
    ]


def build(control_root: Path, today: date, scope: str = "FULL") -> Status:
    # This page was what the narrowing decision was taken on, so it has
    # to survive the decision: every section below still reports, and
    # the ones outside the scope are labelled rather than dropped.
    #
    # Dropping them would be the same mistake in a new place. "No
    # guarantees in the register" and "guarantees are not this system's
    # job any more" are different facts, and a page that showed only the
    # second would hide the exposure that has not gone anywhere — §3.2
    # says narrowing the software does not narrow the risk.
    from .scope_statutory import CLASS2_REGISTERS, CLASS3_LADDER, MAILBOX_READ
    from .scope_statutory import permits as scope_permits

    def label(title: str, capability: str) -> str:
        if scope_permits(scope, capability):
            return title
        return f"{title}   — OUT OF SCOPE (D-15), still reported"

    status = Status()
    status.add("CLASS 1 — STATUTORY (§2.1)", _statutory(control_root))
    status.add(label("CLASS 2 — COMMERCIAL REGISTERS (§2.2)", CLASS2_REGISTERS),
               _registers(control_root))
    status.add(label("CLASS 3 — THE OBLIGATION REGISTER (§6)", CLASS3_LADDER),
               _obligations(control_root))
    status.add(label("WHAT THE CONTRACT SCAN FOUND (§6 Stage C)",
                     CLASS2_REGISTERS), _stage_c(control_root))
    status.add(label("MAILBOX (§3.1a)", MAILBOX_READ), _mailbox(control_root))
    status.add(label("GOVERNANCE — THE PHASE 2 PRE-CONDITIONS (§12)",
                     MAILBOX_READ), _governance(control_root))
    status.scope = scope
    return status


def render(status: Status, today: date) -> str:
    lines = [f"WHERE CONTROL ACTUALLY IS — {today:%d-%b-%Y}", ""]
    scope = getattr(status, "scope", "FULL")
    if str(scope).strip().upper() != "FULL":
        lines += [
            "OPERATING_SCOPE=STATUTORY_ONLY (D-15). Class 1 is what Control",
            "operates on; the sections marked out of scope are still measured",
            "and still reported, because the exposure they describe has not",
            "gone anywhere — narrowing the software does not narrow the risk",
            "(§3.2). They are what widening would have to re-open.",
            "",
        ]
    for title, entries in status.sections:
        lines += [title, ""]
        for entry in entries:
            lines.append(f"  {entry.value:>16}   {entry.label}")
            if entry.note:
                lines.append(f"  {'':>16}   {entry.note}")
        lines.append("")
    lines += [
        "Read from the register, the database, the Stage C cache and the",
        "config as they stand. Nothing was scanned and nothing recomputed.",
        "",
        "An absent number and a zero are different facts, and every line",
        "above says which it is — \"no guarantees in the register\" reads the",
        "same whether the registers were never populated or the company has",
        "none, and those need opposite answers (§1.1).",
    ]
    return "\n".join(lines)
