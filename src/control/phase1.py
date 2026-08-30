"""Phase 1 — the DRY_RUN phase and the gate at the end of it (§16, §13.1).

Phase 0 asks what the company has. Phase 1 asks whether Control reads it
correctly, and it answers that question by running the whole engine with
the sending disabled: every class evaluated, every message drafted, and
nothing leaving the building. `cycle` already does that. What did not
exist was anything that says **whether Phase 1 is finished**, and the
charter is specific that the answer is not a feeling:

> *Gate: golden set <5% false positives · usage policy circulated and
> acknowledged · IWR amended · PDPL basis documented · client
> confidentiality scope decided · absence register live · dispute path
> published.*

Seven conditions, and Control can close exactly none of them by itself.
That is the point of writing them down. Six need a human to do something
outside this system, and the seventh — the golden set — needs the CEO's
own verdicts under D-03. A gate the system could close alone would not be
a gate.

So this module measures rather than decides. Each condition becomes a row
with a state, the evidence Control actually observed, and the named person
who can close it. Three states only:

- `CLOSED` — evidence exists on disk or in the database that the
  condition is met
- `OPEN` — it is not met, and a named human can meet it
- `BLOCKED` — it is not met and cannot be, because something else must
  happen first

`BLOCKED` is not a softer `OPEN`. It exists because "the golden set has
not passed" and "the golden set is empty and nobody has been asked to
judge it" are different situations with different next actions, and a
report that renders them identically sends the CEO to look at the wrong
thing.

**Two gates are assessed, not one.** §16 puts the obligation register at
the *Phase 0* gate, and Phase 1 runs on that register. Reporting only the
Phase 1 row would let an unapproved register sit underneath a green Phase
1 line, which is the shape of failure §12.1.4 warns about — a dashboard
that looks like assurance over ground nobody approved.

**The gate's own wording is contested, and the stricter reading wins.**
§16 says *"golden set <5% false positives"*; §13.1 as revised by finding
V2 says *"zero false RETURNED_FOR_REVISION or NOT_ACCEPTED verdicts"* and
adds that a 30–50 item set is too small to certify a percentage at all.
Both sentences are in the charter. This module applies the zero-false-
returns rule, reports the §16 percentage alongside it as information, and
says in the rendered gate which of the two it applied — §1.3 resolves a
conflict by quoting the clause, and quoting only the half that passes is
not resolving it.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

CLOSED = "CLOSED"
OPEN = "OPEN"
BLOCKED = "BLOCKED"

STATE_ORDER = (BLOCKED, OPEN, CLOSED)


@dataclass(frozen=True)
class GateItem:
    key: str
    requirement: str
    state: str
    evidence: str
    owner: str
    reference: str
    #  What the CEO or the named owner would actually do next. Empty on a
    #  closed row. §7.5 makes the same demand of every finding: a finding
    #  without an action line is not a finding.
    action: str = ""

    @property
    def blocking(self) -> bool:
        return self.state != CLOSED


@dataclass
class Evidence:
    """What Control observed. Every field is a fact from disk or the
    database — nothing here is inferred, so a wrong gate row traces to a
    wrong observation rather than to a judgement made here."""

    # Phase 0 gate
    register_approved: int = 0
    register_proposed: int = 0
    reporting_lines_unconfirmed: int = 0
    statutory_verified_by_advisor: bool = False
    statutory_ceo_stated: int = 0
    authority_thresholds_set: bool = False
    authority_interim_active: bool = False
    authority_review_due: str = ""

    # Phase 1 gate
    golden_cases: int = 0
    golden_pending: int = 0
    golden_false_returns: int | None = None
    golden_fp_checks: int = 0
    golden_fp_opportunities: int = 0
    golden_batches_issued: int = 0
    golden_batches_outstanding: int = 0
    golden_stalled: int = 0
    clause_subsample: int = 0

    usage_policy_drafted: bool = False
    usage_policy_acknowledged: int = 0
    usage_policy_expected: int = 0
    iwr_drafted: bool = False
    iwr_adopted: bool = False
    pdpl_drafted: bool = False
    pdpl_issued: bool = False
    confidential_clients: int = 0
    confidential_confirmed: int = 0
    absence_register_present: bool = False
    absence_owner: str = ""
    dispute_path_published: bool = False

    # The Phase 1 body rather than its gate: did the dry run actually run?
    dry_run_cycles: int = 0
    drafts_pending: int = 0


# ---- the Phase 0 gate, because Phase 1 stands on it -------------------

def assess_phase0(e: Evidence) -> list[GateItem]:
    items = []

    if e.register_approved:
        state, evidence = CLOSED, f"{e.register_approved} obligation(s) approved"
        action = ""
    elif e.register_proposed:
        state = OPEN
        evidence = (f"{e.register_proposed} obligation(s) proposed, none "
                    "approved — obligations.yaml is empty")
        action = ("Read PROPOSED-OBLIGATION-REGISTER.yaml and approve, amend "
                  "or reject each row. Approval is what ends Phase 0 (§6).")
    else:
        state = BLOCKED
        evidence = "no register proposed and none approved"
        action = ("Run Stage D so there is something to approve. Until then "
                  "class 3 tracks nothing.")
    items.append(GateItem(
        "obligation_register", "Obligation register approved", state,
        evidence, "Ahmed Diab, CEO", "§6, §16 Phase 0 gate", action))

    if e.reporting_lines_unconfirmed:
        items.append(GateItem(
            "reporting_lines", "Reporting lines confirmed", OPEN,
            f"{e.reporting_lines_unconfirmed} line(s) still marked inferred",
            "Ahmed Diab, CEO", "§3, O-01",
            "Confirm or correct the inferred lines in people.yaml."))
    else:
        items.append(GateItem(
            "reporting_lines", "Reporting lines confirmed", CLOSED,
            "no inferred lines remain in people.yaml", "Ahmed Diab, CEO",
            "§3, O-01"))

    if e.statutory_verified_by_advisor:
        items.append(GateItem(
            "statutory_calendar", "Statutory calendar verified with the tax "
            "advisor", CLOSED, "verified_by_advisor is true",
            "Mohamed Abdelsadiq / tax advisor", "§2.1, O-03"))
    else:
        items.append(GateItem(
            "statutory_calendar",
            "Statutory calendar verified with the tax advisor", OPEN,
            f"{e.statutory_ceo_stated} rule(s) CEO-stated, none verified by "
            "an advisor",
            "tax advisor — none engaged", "§2.1, O-03",
            "Send the completed statutory table for correction (execution "
            "order step 5). A CEO-stated rule still alerts; it is not "
            "verified, and §7 of the order makes promoting one without a "
            "named human a stop condition."))

    if e.authority_thresholds_set:
        state, evidence, action = CLOSED, "thresholds populated", ""
    elif e.authority_interim_active:
        state = OPEN
        evidence = ("interim itemise-everything under D-06; threshold is zero "
                    f"so every commitment is itemised — review due "
                    f"{e.authority_review_due or 'not recorded'}")
        action = ("Set the thresholds from the observed month, or extend the "
                  "interim period in writing. D-06 is a chosen operating "
                  "position, so this row is open rather than failing.")
    else:
        state = BLOCKED
        evidence = "thresholds null and no interim position recorded"
        action = ("Either populate authority.yaml or record the interim "
                  "position. Neither is in place, so §7.3 S2 cannot check a "
                  "delegated limit against a value.")
    items.append(GateItem(
        "authority_matrix", "Authority matrix defined", state, evidence,
        "Ahmed Diab, CEO", "§3.2, O-02, D-06", action))

    return items


# ---- the Phase 1 gate --------------------------------------------------

def assess_phase1(e: Evidence) -> list[GateItem]:
    items = [_golden_gate(e)]

    if e.confidential_clients and e.confidential_confirmed >= e.confidential_clients:
        items.append(GateItem(
            "confidential_scope", "Client confidentiality scope decided",
            CLOSED,
            f"{e.confidential_confirmed} of {e.confidential_clients} clients "
            "confirmed", "Ahmed Diab, CEO", "§12.1, O-04"))
    else:
        unconfirmed = e.confidential_clients - e.confidential_confirmed
        items.append(GateItem(
            "confidential_scope", "Client confidentiality scope decided",
            OPEN,
            f"{unconfirmed} of {e.confidential_clients} client(s) not yet "
            "confirmed — each is treated as confidential meanwhile",
            "Ahmed Diab, CEO", "§12.1, O-04",
            "Confirm the classifications in CONFIDENTIAL-SCOPE.md. An "
            "unconfirmed client is read as confidential (§12.1.1), so the "
            "cost of leaving this open is checks not run, never content "
            "read."))

    items.append(_document_gate(
        "usage_policy", "Usage policy circulated and acknowledged",
        drafted=e.usage_policy_drafted, adopted=(
            e.usage_policy_expected > 0
            and e.usage_policy_acknowledged >= e.usage_policy_expected),
        drafted_note=(
            f"drafted; {e.usage_policy_acknowledged} of "
            f"{e.usage_policy_expected or 'unknown'} acknowledgement(s) on "
            "record"),
        adopted_note=(f"{e.usage_policy_acknowledged} acknowledgement(s) on "
                      "record — the whole roster"),
        owner="Mohamed Ali, HR — issued by the CEO",
        reference="§12.4, O-08, mitigation M3",
        action=("Circulate the policy and collect the eleven signatures. "
                "§16 requires this **before the first live reminder**, not "
                "alongside it — §12.4 warns a system introduced quietly "
                "becomes a grievance and people route around it within a "
                "week.")))

    items.append(_document_gate(
        "iwr", "Internal Work Regulations amended",
        drafted=e.iwr_drafted, adopted=e.iwr_adopted,
        drafted_note="amendment drafted, adoption not recorded",
        adopted_note="adopted and acknowledged",
        owner="Mohamed Ali, HR", reference="§12.3, O-06, D-42, D-48",
        action=("Adopt the drafted clauses A–G internally — D-42 records "
                "that no refiling is required — and state working hours "
                "09:00–17:00 expressly (D-48). Record the adoption date so "
                "this row can close.")))

    items.append(_document_gate(
        "pdpl", "PDPL lawful basis documented and notified",
        drafted=e.pdpl_drafted, adopted=e.pdpl_issued,
        drafted_note="basis documented; employee notification not recorded "
                     "as issued",
        adopted_note="documented and notified",
        owner="Ahmed Diab, CEO — contact Mohamed Ali (D-11 of the order)",
        reference="§12.2, O-07, D-13/D-37/D-44 of the order",
        action=("Issue the written notification by email (D-44 makes email "
                "sufficient and requires no signature) and record the date. "
                "The positions in it are CEO-stated, not counsel-verified, "
                "and stay that way until counsel is engaged — that is D-52 "
                "working.")))

    if e.absence_register_present:
        items.append(GateItem(
            "absence_register", "Absence register live", CLOSED,
            f"absence.yaml present, owner {e.absence_owner or 'not named'}",
            e.absence_owner or "Mohamed Ali, HR", "§3.3, A2"))
    else:
        items.append(GateItem(
            "absence_register", "Absence register live", OPEN,
            "absence.yaml missing or unowned", "Mohamed Ali, HR", "§3.3, A2",
            "Register the file and its owner. Without it every approved "
            "absence produces a false escalation, which finding A2 rates "
            "CRITICAL."))

    if e.dispute_path_published:
        items.append(GateItem(
            "dispute_path", "Dispute path published", CLOSED,
            "the DISPUTE instruction appears in the announcement and the "
            "usage policy", "Ahmed Diab, CEO", "§8.4, §12.4, A3"))
    else:
        items.append(GateItem(
            "dispute_path", "Dispute path published", OPEN,
            "no circulated document tells anyone how to contest a finding",
            "Ahmed Diab, CEO", "§8.4, §12.4, A3",
            "Publish it with the announcement. Every verdict reply already "
            "carries the instruction, but a right nobody has been told "
            "about in advance is not an appeal path (A3)."))

    return items


def _golden_gate(e: Evidence) -> GateItem:
    reference = "§13.1, §16 Phase 1 gate, D-03"
    requirement = "Golden set built and passing"
    owner = "Ahmed Diab, CEO — D-03 puts these verdicts with him alone"

    if not e.golden_cases and not e.golden_pending:
        # Owner deliberately not the CEO. With nothing pending there is
        # nothing for him to judge, and naming him against it sent the
        # bill to the wrong person for as long as the step that builds
        # the cases did not exist. His time is the constraint from the
        # moment a batch is issued, and not before.
        return GateItem(
            "golden_set", requirement, BLOCKED,
            "no judged cases and no pending cases — nothing has been built "
            "to judge, so nothing is waiting on a verdict",
            "Control — the cases are built from the archive first",
            reference,
            "python -m control golden --build --ub-root <UB_ROOT>, then "
            "--issue for the first batch of 10. An empty set is not a pass "
            "(§16), and a set that can only exercise C1 is not one either — "
            "the build states which checks its cases could exercise.")

    if not e.golden_cases:
        outstanding = ""
        if e.golden_batches_outstanding:
            outstanding = (f"; {e.golden_batches_outstanding} batch(es) issued "
                           "and awaiting verdicts")
        return GateItem(
            "golden_set", requirement, BLOCKED,
            f"{e.golden_pending} case(s) pending, none judged{outstanding}",
            owner, reference,
            "Fill VERDICT on the issued worksheet and apply it. Phase 1 "
            "cannot complete without this time, and §13.1 asks for that to "
            "be said rather than waited out.")

    failures = e.golden_false_returns or 0
    fp_rate = (e.golden_fp_checks / e.golden_fp_opportunities
               if e.golden_fp_opportunities else 0.0)
    detail = (f"{e.golden_cases} case(s) judged, {failures} false return(s), "
              f"{e.golden_fp_checks}/{e.golden_fp_opportunities} check-level "
              f"false positives ({fp_rate:.1%})")

    if failures:
        return GateItem(
            "golden_set", requirement, OPEN, detail, owner, reference,
            "Each false return is the engine returning work the CEO "
            "accepted. §13.1 requires zero before Phase 2, because a system "
            "that wrongly returns correct work loses authority permanently "
            "and gets one chance to make that impression.")

    if e.golden_cases < 30:
        return GateItem(
            "golden_set", requirement, OPEN,
            detail + f" — but {e.golden_cases} cases, below the §13.1 range "
            "of 30–50", owner, reference,
            "Judge further batches. Zero false returns over a set this size "
            "is not yet a test of the whole engine, and reporting it as a "
            "pass would certify coverage the set never had.")

    if e.clause_subsample < 10:
        return GateItem(
            "golden_set", requirement, OPEN,
            detail + f" — clause-mapping subsample is {e.clause_subsample}, "
            "below the §13.1 minimum of 10", owner, reference,
            "Judge more items with the clause withheld. Control selecting "
            "the clause frames the judgement, and finding V3 asks for that "
            "framing to be measured rather than assumed away.")

    return GateItem("golden_set", requirement, CLOSED, detail, owner, reference)


def _document_gate(key: str, requirement: str, *, drafted: bool, adopted: bool,
                   drafted_note: str, adopted_note: str, owner: str,
                   reference: str, action: str) -> GateItem:
    """A governance condition met by a human act, not by a file existing.

    A drafted document and an adopted one are far apart, and the failure
    mode is specific: the draft sits in the repository looking finished
    while nobody has signed anything, and the row reads green because the
    file is there. So the draft never closes the row — it only changes
    what the row says is missing.
    """
    if adopted:
        return GateItem(key, requirement, CLOSED, adopted_note, owner,
                        reference)
    if drafted:
        return GateItem(key, requirement, OPEN, drafted_note, owner,
                        reference, action)
    return GateItem(key, requirement, BLOCKED, "not drafted", owner,
                    reference, "Draft it first. " + action)


# ---- rendering ---------------------------------------------------------

def summary(items: list[GateItem]) -> dict[str, int]:
    return {state: sum(1 for i in items if i.state == state)
            for state in STATE_ORDER}


def passed(items: list[GateItem]) -> bool:
    return all(i.state == CLOSED for i in items)


def render(phase0: list[GateItem], phase1: list[GateItem], e: Evidence,
           today: date) -> str:
    lines = [
        f"# PHASE 1 GATE — {today:%d-%b-%Y}",
        "",
        "Charter §16, Phase 1 (DRY_RUN, Level 1). What is closed, what is "
        "open, and who closes it.",
        "",
        "**Control closes none of these rows.** Six of the seven Phase 1 "
        "conditions are human acts outside this system, and the seventh — "
        "the golden set — is reserved to the CEO by D-03. A gate the system "
        "could close by itself would not be a gate, so a row here moving to "
        "`CLOSED` always means a person did something, never that Control "
        "decided it had.",
        "",
        "**Which golden-set rule applies.** §16 says *golden set <5% false "
        "positives*; §13.1, as revised by finding V2, says *zero false "
        "`RETURNED_FOR_REVISION` or `NOT_ACCEPTED` verdicts*, counted per "
        "check rather than per document, and adds that a 30–50 item set is "
        "too small to certify a percentage at all. Both sentences are in "
        "the charter. The zero-false-returns rule is applied here and the "
        "percentage is reported beside it as information, because §1.3 "
        "resolves a conflict by quoting the clause and quoting only the "
        "half that passes is not resolving it.",
        "",
    ]

    for title, items, note in (
        ("Phase 0 gate — Phase 1 stands on this", phase0,
         "§16 puts the obligation register at the Phase 0 gate. Phase 1 runs "
         "on that register, so reporting only the Phase 1 rows would leave "
         "an unapproved register sitting under a green line."),
        ("Phase 1 gate — what Phase 2 waits on", phase1,
         "§12 opens *Phase 2 does not begin until every item is closed*. "
         "D-52 of the execution order overrides that for the legal items "
         "and accepts the risk; the rows below still say what is open, "
         "because legal coverage must stay visible rather than be counted "
         "as closed."),
    ):
        counts = summary(items)
        lines += [
            f"## {title}",
            "",
            note,
            "",
            f"**{counts[CLOSED]} closed · {counts[OPEN]} open · "
            f"{counts[BLOCKED]} blocked**",
            "",
            "| State | Requirement | Observed | Owner | Charter |",
            "|---|---|---|---|---|",
        ]
        for item in _ordered(items):
            lines.append(
                f"| {item.state} | {item.requirement} | {item.evidence} | "
                f"{item.owner} | {item.reference} |")
        lines.append("")
        actions = [i for i in _ordered(items) if i.action]
        if actions:
            lines += ["### What would close each open row", ""]
            for item in actions:
                lines += [f"**{item.requirement}** — {item.owner}",
                          "", f"{item.action}", ""]

    lines += [
        "## The dry run itself",
        "",
        f"- cycles recorded in DRY_RUN: {e.dry_run_cycles}",
        f"- drafts awaiting release: {e.drafts_pending}",
        "",
        "§16 asks Phase 1 to run 14 days with everything evaluated and "
        "everything drafted. Nothing releases on silence (§10), so a "
        "growing draft count is the phase working, not a backlog.",
        "",
        "## What this gate does not measure",
        "",
        "- **Whether the CEO-stated legal positions are right.** They are "
        "  operative under D-52 and unverified by counsel. Legal coverage "
        "  reads 0% and stays visible at 0% — that is D-52 working, not "
        "  failing (execution order §6).",
        "- **Whether the obligation register is complete.** Approval makes "
        "  it operative, not exhaustive. An obligation nobody has ever met "
        "  leaves no trace in a mailbox and no row in Stage D.",
        "- **Anything about a person.** Every row above is a property of "
        "  the system or of a document (§1.4, §1.6).",
    ]
    return "\n".join(lines) + "\n"


def _ordered(items: list[GateItem]) -> list[GateItem]:
    return sorted(items, key=lambda i: (STATE_ORDER.index(i.state), i.key))


def console_lines(phase0: list[GateItem], phase1: list[GateItem]) -> list[str]:
    """The same gate, short enough to read at the end of a run."""
    out = []
    for title, items in (("PHASE 0 GATE", phase0), ("PHASE 1 GATE", phase1)):
        counts = summary(items)
        out.append(
            f"{title} — {counts[CLOSED]} closed, {counts[OPEN]} open, "
            f"{counts[BLOCKED]} blocked")
        for item in _ordered(items):
            mark = {CLOSED: "ok  ", OPEN: "OPEN", BLOCKED: "BLOCK"}[item.state]
            out.append(f"  [{mark}] {item.requirement}")
            if item.state != CLOSED:
                out.append(f"         {item.evidence}")
                out.append(f"         -> {item.owner}")
    return out


# ---- gathering the evidence -------------------------------------------

def acknowledgements(config_dir: Path, document: str) -> tuple[int, int]:
    """Signatures recorded against one governance document.

    Returns (signed, expected). §12.4 requires written acknowledgement and
    M3 keeps the eleven signatures on the usage policy; without somewhere
    to record them the condition can never close, so the register is a
    config file the CEO's office fills in rather than something Control
    infers from an email.

    A missing register returns (0, 0) — not met, and the gate says the
    register is missing rather than reporting nought out of eleven, which
    would read as eleven people who declined.
    """
    import yaml

    path = Path(config_dir) / "acknowledgements.yaml"
    if not path.is_file():
        return 0, 0
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = (data.get("documents") or {}).get(document) or {}
    rows = entries.get("acknowledged_by") or []
    signed = sum(1 for r in rows if r.get("date"))
    expected = int(entries.get("expected") or len(rows))
    return signed, expected


def document_adopted(config_dir: Path, document: str) -> bool:
    """Whether a governance document has an adoption date on record."""
    import yaml

    path = Path(config_dir) / "acknowledgements.yaml"
    if not path.is_file():
        return False
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = (data.get("documents") or {}).get(document) or {}
    return bool(entries.get("adopted") or entries.get("issued"))


# ---- gathering the evidence -------------------------------------------

def gather(control_root: Path, conn, config) -> Evidence:
    """Read the gate's evidence off disk and out of the database.

    Every field is an observation. Nothing here decides whether a
    condition is met — `assess_phase0` and `assess_phase1` do that, and
    keeping the two apart is what makes a wrong row traceable to a wrong
    reading rather than to a judgement buried in a gatherer.

    A source that is absent produces the default, which is always the
    conservative one: zero cases, nothing acknowledged, nothing adopted.
    An unreadable file must never read as a satisfied condition.
    """
    import yaml

    control_root = Path(control_root)
    config_dir = control_root / "config"
    e = Evidence()

    obligations = (config["obligations"] or {}).get("obligations") or []
    e.register_approved = len([r for r in obligations
                               if r.get("approved_by_ceo")])
    proposed = control_root / "discovery" / "PROPOSED-OBLIGATION-REGISTER.yaml"
    if proposed.is_file():
        try:
            data = yaml.safe_load(proposed.read_text(encoding="utf-8")) or {}
            e.register_proposed = len(data.get("obligations") or [])
        except Exception:
            e.register_proposed = 0

    people = (config["people"] or {}).get("people") or []
    e.reporting_lines_unconfirmed = len(
        [p for p in people if p.get("confirmed") is False])

    statutory = config["statutory-calendar"] or {}
    e.statutory_verified_by_advisor = bool(
        statutory.get("verified_by_advisor"))
    e.statutory_ceo_stated = len(
        [r for r in (statutory.get("obligations") or [])
         if r.get("provenance") == "ceo_stated"])

    authority = config["authority"] or {}
    thresholds = authority.get("thresholds") or {}
    e.authority_thresholds_set = any(
        v for v in thresholds.values() if isinstance(v, (int, float)) and v)
    e.authority_interim_active = bool(authority.get("interim"))
    e.authority_review_due = str(authority.get("review_due") or "")

    golden = control_root / "tests" / "golden-set"
    if golden.is_dir():
        e.golden_cases = len(list(golden.glob("*.yaml")))
    worksheets = golden / "worksheets"
    if worksheets.is_dir():
        e.golden_batches_issued = len(list(worksheets.glob("batch-*.md")))

    e.usage_policy_drafted = _drafted(control_root, "USAGE-POLICY")
    e.iwr_drafted = _drafted(control_root, "IWR-AMENDMENT")
    e.pdpl_drafted = _drafted(control_root, "PDPL-BASIS")
    e.usage_policy_acknowledged, e.usage_policy_expected = acknowledgements(
        config_dir, "usage_policy")
    e.iwr_adopted = document_adopted(config_dir, "iwr")
    e.pdpl_issued = document_adopted(config_dir, "pdpl_notification")

    confidential = config["confidential"] or {}
    clients = confidential.get("confidential_clients") or []
    e.confidential_clients = len(clients)
    e.confidential_confirmed = len([c for c in clients if c.get("confirmed")])

    absence = config["absence"] or {}
    e.absence_register_present = bool(absence.get("absences") is not None
                                      or absence.get("owner"))
    e.absence_owner = str(absence.get("owner") or "")

    # The dispute path is published when staff have been told how to use
    # it, which is the announcement and the policy — not when the code
    # exists. `disputes.py` has worked for weeks and nobody has been told.
    e.dispute_path_published = bool(
        e.usage_policy_acknowledged and e.usage_policy_expected
        and e.usage_policy_acknowledged >= e.usage_policy_expected)

    logs = control_root / "logs"
    if logs.is_dir():
        e.dry_run_cycles = len(list(logs.glob("????-??-??.jsonl")))
    pending = control_root / "outbox" / "pending-approval"
    if pending.is_dir():
        e.drafts_pending = len(list(pending.glob("*.json")))

    if conn is not None:
        try:
            e.golden_pending = conn.execute(
                "SELECT COUNT(*) FROM disputes WHERE state = 'PENDING'"
            ).fetchone()[0]
        except Exception:
            pass
    return e


def _drafted(control_root: Path, stem: str) -> bool:
    """A governance document exists as a draft.

    Looked for in the repository's `docs/governance` as well as in
    CONTROL_ROOT, because that is where they are written and a machine
    that has not copied them has not thereby un-drafted them.
    """
    repo = Path(__file__).resolve().parent.parent.parent
    for base in (Path(control_root) / "knowledge" / "policies",
                 repo / "docs" / "governance"):
        if (base / f"{stem}.md").is_file():
            return True
    return False
