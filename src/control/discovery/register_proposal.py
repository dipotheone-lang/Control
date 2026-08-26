"""The proposed obligation register — Stage D's deliverable (§6, Stage J.2).

This is the document the CEO approves, and that approval is what ends
Phase 0. Everything in it is a **proposal with its evidence attached**;
nothing here is an obligation until a human says so, and every row
carries `approved_by_ceo: null` until one does.

Three sources, and the register says which produced each row:

- **The statutory calendar** (class 1). Already decided by the CEO in the
  execution order of 18-Aug-2026. Those rows are referenced, not
  re-proposed — re-proposing a decision the CEO has taken would invite
  it to be taken differently by accident.
- **Document series on the drive** (class 3 and some class 2). Recurring
  families of filenames with an observed cadence. This is where the
  company's actual reporting lives.
- **The controlled forms register** (240 forms across 12 manuals). A
  registered form with a cadence in its title and no document evidence
  anywhere on the drive is a *ghost requirement* — the management system
  requires it and nothing suggests it has ever been filed.

**The five Stage D categories are the point, not a footnote.** §6 asks
for ghost requirements, orphan reports, dead reports, shadow reports and
formless reports to be reported *separately*. They are five different
problems with five different answers — retire it, formalise it, chase it,
merge them, put it on a form — and a register that folded them into one
list of obligations would ask the CEO to approve the tracking of reports
that should be retired.

**Owner is proposed from the folder, and the rule is printed.** A series
under `9. HR Department/` is proposed to the HR & Admin Manager. That is
an inference from where the company files things, and it is wrong
sometimes; it is offered as a routing proposal with its rule visible so a
wrong row is obvious rather than buried. §1.4 applies throughout — every
row is about a document, never about whether somebody has been doing
their job.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import forms as forms_mod
from .series import Series

# ---- what looks like a report ----------------------------------------

# A recurring family of files is only a candidate obligation if its name
# says it is a report, record or return. Quotations, purchase orders and
# invoices recur too, and they are commercial artefacts rather than
# controlled reporting — §2.2 tracks them through the class 2 registers,
# not through the class 3 ladder.
_REPORT_WORDS = re.compile(
    r"(?i)\b(report|register|ledger|log|statement|minutes|kpi|audit|"
    r"inspection|checklist|return|declaration|payroll|timesheet|"
    r"attendance|reconciliation|summary|dashboard|review)\b"
    r"|تقرير|سجل|كشف|ميزان|مرتبات|رصيد|حصر|محضر|مراجعة|بيان"
)

# Commercial artefacts: real recurring evidence, but §2.2 owns them.
_COMMERCIAL_WORDS = re.compile(
    r"(?i)\b(quotation|quote|proposal|offer|tender|bid|rfq|rfp|"
    r"purchase order|\bpo\b|\bpr\b|invoice|proforma|contract|guarantee|"
    r"bond|accreditation|prequalification|registration)\b"
    r"|عرض سعر|أمر شراء|فاتورة|عقد|ضمان"
)

# Cadence stated in a form's own title. A form called "Monthly HSE Audit
# Checklist" declares its own frequency; one called "Gate Pass" does not,
# and an event-driven form with no evidence is not a missed obligation.
_FORM_CADENCE = re.compile(
    r"(?i)\b(daily|weekly|fortnightly|monthly|quarterly|annual|periodic)\b")

# ---- who a folder belongs to -----------------------------------------

# The routing rule, published with the register. Each entry is
# (folder prefix, owner email, department, default class). Matched
# case-insensitively against the first path segment.
FOLDER_ROUTING = (
    ("9. HR Department", "hr@ubcsis.com", "HR & Administration", 3),
    ("15. Social Insurance", "accounts@ubcsis.com", "Finance — statutory", 1),
    ("8. Finance", "accounts@ubcsis.com", "Finance & Accounting", 3),
    ("16. Safety Documents", "hse@ubcsis.com", "Corporate HSE", 3),
    ("18. KPIs", "ghareeb@ubcsis.com", "Strategy Execution", 3),
    ("14. Construction Management Files", "shymaa@ubcsis.com",
     "Technical Office", 3),
    ("1. Invoices", "shymaa@ubcsis.com", "Technical Office", 3),
    ("2. Quotations", "donia@ubcsis.com", "Tendering & Proposals", 2),
    ("3. Purchase Orders", "info@ubcsis.com", "Procurement (vacant, interim)", 2),
    ("4. Suppliers POs", "info@ubcsis.com", "Procurement (vacant, interim)", 2),
    ("5. Purchasing Invoices", "accounts@ubcsis.com", "Finance & Accounting", 2),
    ("Invoices from Suppliers", "accounts@ubcsis.com", "Finance & Accounting", 2),
    ("6. Clients Legal Documents", "info@ubcsis.com", "Legal & Contracts", 2),
    ("7. Suppliers Legal Documents", "info@ubcsis.com", "Legal & Contracts", 2),
    ("11. Vendor Registeration Request", "donia@ubcsis.com",
     "Client accreditation", 2),
    ("10. Marketing & Publicity", "marketing@ubcsis.com", "Marketing", 4),
    ("17. Work Experience", "marketing@ubcsis.com", "Marketing", 4),
    ("22. Warehouse Management", "a.elsayed@ubcsis.com", "Site operations", 3),
)

UNROUTED = ("NOT PROVIDED", "unrouted", 3)

# Stage D's five categories (§6), plus the ordinary case.
LIVE = "live"
DEAD = "dead"
GHOST = "ghost"
SHADOW = "shadow"
FORMLESS = "formless"
ORPHAN = "orphan"

CATEGORY_NOTE = {
    LIVE: "recurring, current, and on a controlled form",
    DEAD: "recurred for a period and then stopped — retired, or unmet, "
          "and the filesystem cannot tell which",
    GHOST: "the management system registers this form and no document "
           "evidence of it exists anywhere on the drive",
    SHADOW: "the same series filed in two places — one of them is a copy, "
            "and a register tracking both would double-count",
    FORMLESS: "recurring and current, but on no controlled form — C2 "
              "cannot name a revision for it",
    ORPHAN: "recurring with no controlled form and no manual clause "
            "behind it — somebody produces this for a reason nobody "
            "wrote down",
}

RECOMMENDATION = {
    LIVE: "formalise — adopt as a tracked obligation",
    DEAD: "investigate — confirm retired, or reinstate",
    GHOST: "investigate — is this form live? If not, retire it from the "
           "manual rather than tracking a report nobody files",
    SHADOW: "merge — name one location as the record copy",
    FORMLESS: "formalise — map to a controlled form, or register the "
              "layout in use as one",
    ORPHAN: "investigate — establish who needs it and under which clause",
}


@dataclass
class Proposal:
    obligation_id: str
    obligation_class: int
    name: str
    owner: str
    department: str
    form: str
    form_basis: str
    cadence: str
    confidence: str
    category: str
    evidence: str
    folder: str
    first_seen: str = ""
    last_seen: str = ""
    instances: int = 0
    governing_clause: str = "NOT ESTABLISHED"
    due: str = "NOT ESTABLISHED"
    source: str = "PHASE0-STAGE-D"

    def as_yaml_row(self) -> dict:
        return {
            "id": self.obligation_id,
            "class": self.obligation_class,
            "name": self.name,
            "owner": self.owner,
            "department": self.department,
            "form": self.form,
            "form_basis": self.form_basis,
            "cadence": self.cadence,
            "due": self.due,
            "governing_clause": self.governing_clause,
            "confidence": self.confidence,
            "stage_d_category": self.category,
            "recommendation": RECOMMENDATION[self.category],
            "evidence": self.evidence,
            "folder": self.folder,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "instances": self.instances,
            "source": self.source,
            "approved_by_ceo": None,
        }


@dataclass
class Register:
    proposals: list = field(default_factory=list)
    statutory: list = field(default_factory=list)
    set_aside: list = field(default_factory=list)
    generated: date = None

    def by_category(self, category: str) -> list:
        return [p for p in self.proposals if p.category == category]

    def by_class(self, obligation_class: int) -> list:
        return [p for p in self.proposals
                if p.obligation_class == obligation_class]


def route(folder: str) -> tuple:
    """(owner, department, default class) for a folder path."""
    head = folder.replace("\\", "/").split("/")[0].strip().lower()
    for prefix, owner, department, obligation_class in FOLDER_ROUTING:
        if head.startswith(prefix.lower()):
            return owner, department, obligation_class
    return UNROUTED


def _identifier(department: str, index: int, obligation_class: int) -> str:
    prefix = {1: "STAT", 2: "COMM", 3: "OPS", 4: "INFO"}[obligation_class]
    tag = "".join(w[0] for w in re.findall(r"[A-Za-z]+", department))[:3].upper()
    return f"{prefix}-{tag or 'GEN'}-{index:03d}"


def _shadow_groups(series: list) -> dict:
    """Series sharing a filename template across different folders.

    The drive really does this: `17. Work Experience/PPT/Purchase Orders/`
    mirrors `3. Purchase Orders/` file for file. Tracking both as
    obligations would double every count in the register and produce two
    reminders for one report.
    """
    by_template: dict = {}
    for item in series:
        by_template.setdefault(item.template, []).append(item)
    return {template: found for template, found in by_template.items()
            if len(found) > 1}


def build(series: list, register: forms_mod.FormsRegister,
          statutory_config: dict | None, today: date) -> Register:
    """Turn observed evidence into proposals. Decides nothing."""
    result = Register(generated=today)

    for row in (statutory_config or {}).get("obligations") or []:
        result.statutory.append({
            "id": row.get("id"),
            "name": row.get("name"),
            "cadence": row.get("cadence"),
            "owner": row.get("owner"),
            "basis": ("verified_by_advisor" if row.get("verified_by_advisor")
                      else "ceo_stated — not advisor-verified (O-03)"),
        })

    shadows = _shadow_groups(series)
    shadowed: set = set()
    for group in shadows.values():
        # Keep the one with the shortest folder path as the record copy;
        # the rest are proposed as shadows. Shortest rather than newest
        # because a copy filed for a bid pack sits deeper than the
        # original, and mtime on a copied tree says when it was copied.
        ordered = sorted(group, key=lambda s: (len(s.folder_label), s.folder_label))
        for duplicate in ordered[1:]:
            shadowed.add(id(duplicate))

    counters: dict = {}
    for item in series:
        label = item.label
        folder = item.folder_label
        owner, department, default_class = route(folder)

        is_report = bool(_REPORT_WORDS.search(label))
        is_commercial = bool(_COMMERCIAL_WORDS.search(label))

        if not is_report:
            result.set_aside.append({
                "name": label, "folder": folder, "instances": item.count,
                "cadence": item.cadence,
                "why": ("commercial artefact — §2.2 tracks these through the "
                        "class 2 registers, not the class 3 ladder"
                        if is_commercial else
                        "name carries no report, record or return vocabulary"),
            })
            continue

        found = forms_mod.match(label, register)
        if found.matched:
            form = f"{found.form.code} rev {found.form.revision}"
            basis = (f"title match against the controlled forms register "
                     f"({found.score:.0%} of the form title present)")
            clause = f"{found.form.manual_code or found.form.manual}, {found.form.code}"
        elif found.ambiguous:
            form = "AMBIGUOUS — CEO DECISION"
            basis = (f"{found.form.code} and {found.runner_up.code} score "
                     f"{found.score:.0%} and {found.runner_up_score:.0%} — "
                     "no basis to choose (§6 Stage C)")
            clause = "NOT ESTABLISHED — governing form undecided"
        else:
            form = "FORMLESS — no controlled form matched"
            basis = (f"best candidate reached {found.score:.0%} of a form "
                     "title, below the threshold for proposing one")
            clause = "NOT ESTABLISHED"

        dormant = item.dormant_since(today)
        if id(item) in shadowed:
            category = SHADOW
        elif dormant:
            category = DEAD
        elif not found.matched and not found.ambiguous:
            category = ORPHAN if default_class == 3 else FORMLESS
        else:
            category = LIVE

        obligation_class = default_class
        index = counters[department] = counters.get(department, 0) + 1
        evidence = (f"{item.count} document(s) in {folder or 'UB_ROOT'} "
                    f"between {item.first:%b-%Y} and {item.last:%b-%Y}, "
                    f"median gap {item.median_gap_days:.0f} days")
        if dormant:
            evidence += (f"; nothing filed for {dormant} days past the point "
                         "its own rhythm would have expected the next one")

        result.proposals.append(Proposal(
            obligation_id=_identifier(department, index, obligation_class),
            obligation_class=obligation_class, name=label, owner=owner,
            department=department, form=form, form_basis=basis,
            cadence=item.cadence, confidence=item.confidence,
            category=category, evidence=evidence, folder=folder,
            first_seen=item.first.isoformat(), last_seen=item.last.isoformat(),
            instances=item.count, governing_clause=clause))

    result.proposals.extend(
        _ghosts(series, register, len(result.proposals)))
    return result


def _ghosts(series: list, register: forms_mod.FormsRegister,
            offset: int) -> list:
    """Registered forms with a stated cadence and no evidence at all.

    Only forms whose own title states a frequency are considered. A
    "Gate Pass" leaving no trace is not a missed obligation — it is an
    event-driven form nobody needed this week — and reporting 200 ghosts
    would bury the dozen that mean something.
    """
    filed = " || ".join(item.label.lower() for item in series)
    ghosts = []
    for index, form in enumerate(sorted(register.forms, key=lambda f: f.code)):
        if not _FORM_CADENCE.search(form.title):
            continue
        tokens = form.tokens
        if tokens and all(token in filed for token in tokens):
            continue
        cadence = _FORM_CADENCE.search(form.title).group(1).lower()
        ghosts.append(Proposal(
            obligation_id=f"GHOST-{form.code}",
            obligation_class=3, name=form.title,
            owner="NOT PROVIDED", department=form.manual,
            form=f"{form.code} rev {form.revision}",
            form_basis="registered in the controlled forms register",
            cadence=cadence, confidence="LOW", category=GHOST,
            evidence=("no document series on the drive matches this form's "
                      "title — the management system requires it and there "
                      "is no evidence it has been filed"),
            folder="", governing_clause=f"{form.manual_code}, {form.code}",
            source="PHASE0-STAGE-C — controlled forms register"))
    return ghosts


# ---- rendering ---------------------------------------------------------

def to_yaml(register: Register) -> str:
    import yaml

    payload = {
        "generated": register.generated.isoformat(),
        "status": "PROPOSED — NOT OPERATIVE",
        "how_to_approve": (
            "Set approved_by_ceo to your address on each row you accept, and "
            "delete or annotate the rest. Approving this file is what ends "
            "Phase 0 (§6). Nothing here is tracked until then: "
            "config/obligations.yaml stays empty and class 3 tracks nothing."),
        "class_1_statutory": {
            "note": ("Already decided in the execution order of 18-Aug-2026 "
                     "and operative from config/statutory-calendar.yaml. "
                     "Listed for completeness, not for re-approval."),
            "obligations": register.statutory,
        },
        "proposed_obligations": [p.as_yaml_row() for p in register.proposals],
        "set_aside": {
            "note": ("Recurring document series that were NOT proposed as "
                     "obligations, with the reason. Listed so the CEO can "
                     "see what was left out — a register showing only what "
                     "it selected cannot be checked."),
            "series": register.set_aside,
        },
        "routing_rule": {
            "note": ("Owner is proposed from the top-level folder. This is "
                     "an inference from where the company files things and "
                     "it is wrong sometimes; the rule is printed so a wrong "
                     "row is obvious."),
            "map": [{"folder": f, "owner": o, "department": d, "class": c}
                    for f, o, d, c in FOLDER_ROUTING],
        },
    }
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False,
                          width=100)


def render_gap_analysis(register: Register, today: date) -> str:
    """GAP-ANALYSIS.md — Stage J deliverable 4, one recommendation each."""
    lines = [
        f"# GAP ANALYSIS — {today:%d-%b-%Y}",
        "",
        "Charter §6 Stage D asks for five things to be reported separately: "
        "ghost requirements, orphan reports, dead reports, shadow reports "
        "and formless reports. They are five different problems with five "
        "different answers, and a single list of \"issues\" would ask for "
        "the same action on all of them.",
        "",
        "Every recommendation below is **formalise / retire / merge / "
        "investigate**, per Stage J.4. None of them is taken.",
        "",
    ]
    for category in (GHOST, DEAD, SHADOW, FORMLESS, ORPHAN, LIVE):
        found = register.by_category(category)
        lines += [
            f"## {category.upper()} — {len(found)}",
            "",
            f"*{CATEGORY_NOTE[category]}*",
            "",
            f"**Recommendation: {RECOMMENDATION[category]}**",
            "",
        ]
        if not found:
            lines += ["None found.", ""]
            continue
        lines += ["| Proposed id | Name | Owner | Cadence | Evidence |",
                  "|---|---|---|---|---|"]
        for proposal in found[:60]:
            lines.append(
                f"| {proposal.obligation_id} | {proposal.name[:60]} | "
                f"{proposal.owner} | {proposal.cadence} | "
                f"{proposal.evidence[:110]} |")
        if len(found) > 60:
            lines.append(f"| … | *{len(found) - 60} more in "
                         "PROPOSED-OBLIGATION-REGISTER.yaml* | | | |")
        lines.append("")

    lines += [
        "## What this analysis cannot see",
        "",
        "- **An obligation nobody has ever met.** It leaves no series on "
        "  the drive and no row in the mail. The ghost list catches only "
        "  those a registered form names.",
        "- **Whether a dead series was retired on purpose.** The "
        "  filesystem records that filing stopped, never why. That is the "
        "  difference between a retired report and an unmet one, and it is "
        "  a question for a person.",
        "- **Anything about who filed what.** Every row is a property of a "
        "  document series (§1.4).",
    ]
    return "\n".join(lines) + "\n"


def render_summary(register: Register) -> list:
    """Console lines — what the run found, in the order it matters."""
    lines = [
        f"proposed obligations: {len(register.proposals)}",
        f"  class 2 commercial:  {len(register.by_class(2))}",
        f"  class 3 operational: {len(register.by_class(3))}",
        f"  class 4 information: {len(register.by_class(4))}",
        "",
        "Stage D categories (§6), reported separately:",
    ]
    for category in (LIVE, FORMLESS, ORPHAN, DEAD, SHADOW, GHOST):
        lines.append(f"  {category:9} {len(register.by_category(category)):4}"
                     f"  — {CATEGORY_NOTE[category][:60]}")
    lines += [
        "",
        f"set aside, with reasons: {len(register.set_aside)} series",
        f"class 1 statutory rows referenced: {len(register.statutory)}",
    ]
    return lines
