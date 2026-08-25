"""Evaluation engine — charter §7.1 checks, §7.4 verdicts, §12.1.3 reduced set.

Operates on extracted submission data, not raw files: the extraction layer
(with its OCR confidence floor, §5.5) produces a SubmissionDoc; this module
judges it. All seven checks always run and report together — one complete
list, never a drip-feed (§7.1).

Verdict rules (§7.4):
- any C2–C6 failure  -> RETURNED_FOR_REVISION (not posted)
- minor C7 only      -> ACCEPTED_WITH_OBSERVATIONS (posted, flagged)
- all pass           -> ACCEPTED
- no attachment      -> NOT_ACCEPTED (item stays open)
- unreadable         -> UNREADABLE (manual review, not evaluated)
- C1 lateness is recorded and reported but never changes the verdict —
  the enforcement ladder owns lateness, the verdict owns content.

Confidential items (§12.1.3): only C1 and filename-only C2 run; the
verdict set collapses to RECEIVED_ON_TIME / RECEIVED_LATE / NOT_RECEIVED /
NOT ASSESSED — CONFIDENTIAL SCOPE. Control never returns a confidential
item for revision: it has not read it and cannot have grounds.

Every finding carries required / observed / action — a finding without an
action line is not a finding (§7.5).
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from .calendar import WorkingCalendar

_PLACEHOLDERS = re.compile(r"(?i)^\s*(tbd|tba|n/?a|xx+|\?+|-+|null|none|قيد التحديد)\s*$")


@dataclass
class TotalRule:
    """C4: stated total field recomputed from its components."""
    stated_field: str
    component_fields: list[str]


@dataclass
class OpeningRule:
    """C5: this period's opening must equal prior period's closing."""
    opening_field: str
    prior_closing_field: str


@dataclass
class ManualRule:
    """C6: a chartered requirement with its clause. The predicate returns
    True when the submission conforms."""
    clause: str
    requirement: str
    predicate: Callable[[dict], bool]


@dataclass
class Materiality:
    """§7.2: absolute floor and percentage, whichever binds. `sufficient`
    mirrors the minimum-sample rule — an INSUFFICIENT baseline keeps the
    statistical variance check silent."""
    floor_abs: float
    floor_pct: float
    sufficient: bool = True

    def is_material(self, delta: float, base: float) -> bool:
        if not self.sufficient:
            return False
        if abs(delta) < self.floor_abs:
            return False
        if base == 0:
            return True
        return abs(delta) / abs(base) * 100 >= self.floor_pct


@dataclass
class ObligationSpec:
    obligation_id: str
    name: str
    form_code: str
    current_revision: str
    due: datetime
    mandatory_fields: list[str] = field(default_factory=list)
    totals: list[TotalRule] = field(default_factory=list)
    openings: list[OpeningRule] = field(default_factory=list)
    manual_rules: list[ManualRule] = field(default_factory=list)


@dataclass
class SubmissionDoc:
    received_at: datetime
    attachment_name: str | None = None
    form_code: str | None = None       # None => uncontrolled format
    revision: str | None = None
    fields: dict = field(default_factory=dict)
    unreadable: bool = False
    # `confidential` switches on the §12.1.3 reduced check set;
    # `restricted_basis` says under which decision. Two documents get
    # the identical treatment for opposite reasons — an NDA (D-01) and
    # special-category health data (D-17/D-18) — and a report line
    # citing the wrong one describes a restriction that does not exist.
    confidential: bool = False
    restricted_basis: str = ""

    def __post_init__(self):
        # The pair cannot be allowed to disagree, so neither is set
        # independently of the other.
        if self.restricted_basis:
            self.confidential = True
        elif self.confidential:
            self.restricted_basis = "CONFIDENTIAL_CLIENT"


@dataclass
class Finding:
    check: str
    result: str
    required: str
    observed: str
    action: str
    reference: str = ""


@dataclass
class Evaluation:
    verdict: str
    timeliness: str
    findings: list[Finding] = field(default_factory=list)
    check_results: dict = field(default_factory=dict)

    @property
    def defects(self) -> list[Finding]:
        return [f for f in self.findings if f.result not in ("ON_TIME", "EARLY")]


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and (not value.strip() or _PLACEHOLDERS.match(value)):
        return True
    return False


def _timeliness(due: datetime, received: datetime, cal: WorkingCalendar) -> tuple[str, str]:
    if received.date() > due.date():
        days = cal.working_days_between(due.date(), received.date())
        return f"LATE ({days} working days)", "LATE"
    if received.date() < due.date():
        return "EARLY", "EARLY"
    if received > due:
        return "LATE (0 working days)", "LATE"
    return "ON_TIME", "ON_TIME"


def evaluate(
    spec: ObligationSpec,
    doc: SubmissionDoc,
    cal: WorkingCalendar,
    prior_fields: dict | None = None,
    materiality: Materiality | None = None,
) -> Evaluation:
    if doc.confidential:
        return _evaluate_confidential(spec, doc, cal)

    findings: list[Finding] = []
    results: dict[str, str] = {}

    # C1 — timeliness (recorded; never changes the verdict)
    timeliness_text, c1 = _timeliness(spec.due, doc.received_at, cal)
    results["C1"] = c1
    if c1 == "LATE":
        findings.append(Finding(
            check="C1", result=timeliness_text,
            required=f"Submission due {spec.due:%d-%b-%Y %H:%M}",
            observed=f"Received {doc.received_at:%d-%b-%Y %H:%M}",
            action="Submit by the due time in future periods.",
        ))

    # UNREADABLE and NO_ATTACHMENT short-circuit content checks — there is
    # no content to check, and pretending otherwise would fabricate (§1.1).
    if doc.unreadable:
        results["C2"] = results["C3"] = results["C4"] = results["C5"] = \
            results["C6"] = results["C7"] = "NOT_EVALUATED"
        return Evaluation("UNREADABLE", timeliness_text, findings, results)

    if doc.attachment_name is None:
        results["C2"] = "NO_ATTACHMENT"
        findings.append(Finding(
            check="C2", result="NO_ATTACHMENT",
            required=f"Form {spec.form_code} rev {spec.current_revision} attached",
            observed="No attachment",
            action=f"Resubmit with the completed {spec.form_code} attached.",
        ))
        return Evaluation("NOT_ACCEPTED", timeliness_text, findings, results)

    # C2 — form control (name old vs current revision explicitly)
    if doc.form_code is None:
        results["C2"] = "UNCONTROLLED_FORMAT"
        findings.append(Finding(
            check="C2", result="UNCONTROLLED_FORMAT",
            required=f"Controlled form {spec.form_code} rev {spec.current_revision}",
            observed=f"Uncontrolled document {doc.attachment_name!r}",
            action=f"Resubmit on {spec.form_code} rev {spec.current_revision}.",
        ))
    elif doc.form_code != spec.form_code:
        results["C2"] = "UNCONTROLLED_FORMAT"
        findings.append(Finding(
            check="C2", result="UNCONTROLLED_FORMAT",
            required=f"Form {spec.form_code}",
            observed=f"Form {doc.form_code}",
            action=f"Use {spec.form_code} rev {spec.current_revision} for this obligation.",
        ))
    elif doc.revision != spec.current_revision:
        results["C2"] = "SUPERSEDED_REVISION"
        findings.append(Finding(
            check="C2", result="SUPERSEDED_REVISION",
            required=f"{spec.form_code} rev {spec.current_revision} (current)",
            observed=f"{spec.form_code} rev {doc.revision} (superseded)",
            action=f"Transfer the data to rev {spec.current_revision} and resubmit.",
        ))
    else:
        results["C2"] = "CORRECT_FORM"

    # C3 — completeness: each empty mandatory field by exact name
    empty = [f for f in spec.mandatory_fields if _is_empty(doc.fields.get(f))]
    if empty:
        results["C3"] = "INCOMPLETE"
        findings.append(Finding(
            check="C3", result="INCOMPLETE",
            required=f"All mandatory fields completed: {', '.join(spec.mandatory_fields)}",
            observed=f"Empty or placeholder: {', '.join(empty)}",
            action=f"Complete {', '.join(empty)} and resubmit.",
        ))
    else:
        results["C3"] = "COMPLETE"

    # C4 — internal consistency: recompute every total
    c4_fail = False
    for rule in spec.totals:
        stated = doc.fields.get(rule.stated_field)
        components = [doc.fields.get(f) for f in rule.component_fields]
        if stated is None or any(not isinstance(v, (int, float)) for v in components):
            continue  # missing pieces are C3's finding, not arithmetic
        computed = sum(components)
        if abs(computed - float(stated)) > 1e-9:
            c4_fail = True
            delta = float(stated) - computed
            findings.append(Finding(
                check="C4", result="ARITHMETIC_ERROR",
                required=f"{rule.stated_field} = sum({', '.join(rule.component_fields)})",
                observed=f"stated {stated} / computed {computed} / delta {delta:+g}",
                action=f"Correct {rule.stated_field} or its components and resubmit.",
            ))
    results["C4"] = "ARITHMETIC_ERROR" if c4_fail else "CONSISTENT"

    # C5 — historical consistency
    results["C5"] = "CONSISTENT"
    if prior_fields is not None:
        mismatches = []
        for rule in spec.openings:
            opening = doc.fields.get(rule.opening_field)
            prior_closing = prior_fields.get(rule.prior_closing_field)
            if opening is None or prior_closing is None:
                continue
            if isinstance(opening, (int, float)) and isinstance(prior_closing, (int, float)):
                delta = float(opening) - float(prior_closing)
                if abs(delta) > 1e-9 and (
                    materiality is None or materiality.is_material(delta, float(prior_closing))
                ):
                    mismatches.append((rule, opening, prior_closing, delta))
        if mismatches:
            results["C5"] = "VARIANCE_UNEXPLAINED"
            for rule, opening, prior_closing, delta in mismatches:
                findings.append(Finding(
                    check="C5", result="VARIANCE_UNEXPLAINED",
                    required=f"{rule.opening_field} equals prior closing {rule.prior_closing_field}",
                    observed=f"opening {opening} / prior closing {prior_closing} / delta {delta:+g}",
                    action="Explain the variance or correct the opening balance.",
                ))
        else:
            compared = [
                (name, value) for name, value in doc.fields.items()
                if name in prior_fields and isinstance(value, (int, float))
            ]
            if len(compared) >= 3 and all(prior_fields[n] == v for n, v in compared):
                results["C5"] = "SUSPECTED_COPY_FORWARD"
                findings.append(Finding(
                    check="C5", result="SUSPECTED_COPY_FORWARD",
                    required="Period data reflecting this period's activity",
                    observed=f"All {len(compared)} comparable numeric fields identical to prior period",
                    action="Confirm the values are genuinely unchanged or resubmit with this period's data.",
                ))

    # C6 — manual conformance, clause quoted
    c6_fail = False
    for rule in spec.manual_rules:
        try:
            conforms = bool(rule.predicate(doc.fields))
        except Exception:
            conforms = False
        if not conforms:
            c6_fail = True
            findings.append(Finding(
                check="C6", result="NON_CONFORMANCE",
                required=rule.requirement,
                observed="Submission does not satisfy the clause",
                action="Correct the submission to conform and resubmit.",
                reference=rule.clause,
            ))
    results["C6"] = "NON_CONFORMANCE" if c6_fail else "CONFORMS"

    # C7 — data quality: placeholders in any field (beyond the mandatory set)
    dirty = [
        name for name, value in doc.fields.items()
        if isinstance(value, str) and _PLACEHOLDERS.match(value)
        and name not in empty
    ]
    if dirty:
        results["C7"] = "QUALITY_DEFECTS"
        findings.append(Finding(
            check="C7", result="QUALITY_DEFECTS",
            required="No placeholder values",
            observed=f"Placeholders in: {', '.join(sorted(dirty))}",
            action="Replace placeholders with actual values.",
        ))
    else:
        results["C7"] = "CLEAN"

    # §7.4 verdict mapping — C1 and C7 never trigger a return.
    returned = (
        results["C2"] in ("SUPERSEDED_REVISION", "UNCONTROLLED_FORMAT")
        or results["C3"] == "INCOMPLETE"
        or results["C4"] == "ARITHMETIC_ERROR"
        or results["C5"] in ("VARIANCE_UNEXPLAINED", "SUSPECTED_COPY_FORWARD")
        or results["C6"] == "NON_CONFORMANCE"
    )
    if returned:
        verdict = "RETURNED_FOR_REVISION"
    elif results["C7"] == "QUALITY_DEFECTS":
        verdict = "ACCEPTED_WITH_OBSERVATIONS"
    else:
        verdict = "ACCEPTED"
    return Evaluation(verdict, timeliness_text, findings, results)


def _evaluate_confidential(
    spec: ObligationSpec, doc: SubmissionDoc, cal: WorkingCalendar
) -> Evaluation:
    """§12.1.3 reduced check set — metadata only, never a return."""
    results: dict[str, str] = {}
    findings: list[Finding] = []

    timeliness_text, c1 = _timeliness(spec.due, doc.received_at, cal)
    results["C1"] = c1

    if doc.attachment_name is None:
        verdict = "NOT_RECEIVED"
    elif c1 == "LATE":
        verdict = "RECEIVED_LATE"
    else:
        verdict = "RECEIVED_ON_TIME"

    # C2 filename-only: form code and revision if present in the filename.
    if doc.attachment_name:
        name = doc.attachment_name.lower()
        if spec.form_code.lower() in name:
            results["C2"] = "CORRECT_FORM (filename only)"
        else:
            results["C2"] = "NOT VERIFIABLE"
    else:
        results["C2"] = "NOT VERIFIABLE"

    label = _NOT_ASSESSED.get(doc.restricted_basis, _NOT_ASSESSED[""])
    for check in ("C3", "C4", "C5", "C6", "C7"):
        results[check] = label

    return Evaluation(verdict, timeliness_text, findings, results)


# The same reduced set, named by the decision that imposed it. §12.1.4's
# stated limitation is about client confidentiality and would be simply
# untrue of an injury record.
_NOT_ASSESSED = {
    "": "NOT ASSESSED — CONFIDENTIAL SCOPE",
    "CONFIDENTIAL_CLIENT": "NOT ASSESSED — CONFIDENTIAL SCOPE",
    "HSE_INCIDENT": "NOT ASSESSED — SPECIAL CATEGORY (D-17, D-18)",
}
