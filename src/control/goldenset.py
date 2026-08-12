"""Golden-set harness — charter §13.1, decision D-03, and the §14.5
regression gate.

Case files are YAML in a golden-set directory. Each carries the
submission data, the governing spec, and the CEO's expected outcome.
The harness:

- runs the engine against every case and reports agreement, with
  disagreements item by item and the engine's own diagnosis
- counts false-positive opportunities PER CHECK, not per document
  (v4.3 finding V2): each case exercises up to seven checks
- applies the Phase 2 gate: ZERO false RETURNED_FOR_REVISION or
  NOT_ACCEPTED verdicts
- generates the CEO worksheets UNANCHORED (D-03): document, form,
  clause, blank verdict — the engine's verdict never appears
- grows the set: every upheld dispute and overridden verdict becomes a
  permanent case (§13.1)
- provides the §14.5 regression gate: an adaptation is rejected if any
  previously passing case fails, false positives rise, or coverage falls
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from .calendar import WorkingCalendar
from .evaluate import (
    Materiality,
    ObligationSpec,
    OpeningRule,
    SubmissionDoc,
    TotalRule,
    evaluate,
)

ACCEPT_VERDICTS = {"ACCEPTED", "ACCEPTED_WITH_OBSERVATIONS"}
RETURN_VERDICTS = {"RETURNED_FOR_REVISION", "NOT_ACCEPTED"}
CHECKS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")

# Check results that count as "flagged" for FP accounting.
_CHECK_FAIL = {
    "C2": {"SUPERSEDED_REVISION", "UNCONTROLLED_FORMAT", "NO_ATTACHMENT"},
    "C3": {"INCOMPLETE"},
    "C4": {"ARITHMETIC_ERROR"},
    "C5": {"VARIANCE_UNEXPLAINED", "SUSPECTED_COPY_FORWARD"},
    "C6": {"NON_CONFORMANCE"},
    "C7": {"QUALITY_DEFECTS"},
    "C1": {"LATE"},
}


@dataclass
class GoldenCase:
    case_id: str
    source: str                    # initial | dispute-upheld | override
    spec: ObligationSpec
    doc: SubmissionDoc
    expected_verdict: str
    expected_failed_checks: list[str]
    prior_fields: dict | None = None
    materiality: Materiality | None = None
    ceo_notes: str = ""
    path: Path | None = None


@dataclass
class CaseOutcome:
    case: GoldenCase
    actual_verdict: str
    actual_failed_checks: list[str]
    verdict_agrees: bool
    false_return: bool             # engine returned what the CEO accepted
    check_false_positives: list[str]
    check_misses: list[str]
    diagnosis: str = ""


@dataclass
class GoldenSetResult:
    outcomes: list[CaseOutcome]

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def agreement_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(1 for o in self.outcomes if o.verdict_agrees) / self.total

    @property
    def false_returns(self) -> int:
        return sum(1 for o in self.outcomes if o.false_return)

    @property
    def fp_opportunities(self) -> int:
        # Per check, not per document (V2).
        return sum(len(CHECKS) for _ in self.outcomes)

    @property
    def check_false_positive_count(self) -> int:
        return sum(len(o.check_false_positives) for o in self.outcomes)

    @property
    def gate_passed(self) -> bool:
        """§13.1 (v4.3): zero false returns before Phase 2."""
        return self.false_returns == 0

    def failing_case_ids(self) -> set[str]:
        return {o.case.case_id for o in self.outcomes if not o.verdict_agrees}


# -- case loading -----------------------------------------------------------

def _spec_from(raw: dict) -> ObligationSpec:
    return ObligationSpec(
        obligation_id=raw["obligation_id"],
        name=raw["name"],
        form_code=raw["form_code"],
        current_revision=str(raw["current_revision"]),
        due=datetime.fromisoformat(raw["due"]),
        mandatory_fields=list(raw.get("mandatory_fields", [])),
        totals=[TotalRule(t["stated_field"], list(t["component_fields"]))
                for t in raw.get("totals", [])],
        openings=[OpeningRule(o["opening_field"], o["prior_closing_field"])
                  for o in raw.get("openings", [])],
    )


def _doc_from(raw: dict) -> SubmissionDoc:
    return SubmissionDoc(
        received_at=datetime.fromisoformat(raw["received_at"]),
        attachment_name=raw.get("attachment_name"),
        form_code=raw.get("form_code"),
        revision=None if raw.get("revision") is None else str(raw.get("revision")),
        fields=dict(raw.get("fields", {})),
        unreadable=bool(raw.get("unreadable", False)),
        confidential=bool(raw.get("confidential", False)),
    )


def load_cases(directory: Path) -> list[GoldenCase]:
    cases = []
    for path in sorted(Path(directory).glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        mat = raw.get("materiality")
        cases.append(GoldenCase(
            case_id=raw["case_id"],
            source=raw.get("source", "initial"),
            spec=_spec_from(raw["spec"]),
            doc=_doc_from(raw["doc"]),
            expected_verdict=raw["expected"]["verdict"],
            expected_failed_checks=list(raw["expected"].get("failed_checks", [])),
            prior_fields=raw.get("prior_fields"),
            materiality=Materiality(**mat) if mat else None,
            ceo_notes=raw.get("ceo_notes", ""),
            path=path,
        ))
    return cases


# -- running ----------------------------------------------------------------

def _failed_checks(check_results: dict) -> list[str]:
    failed = []
    for check in CHECKS:
        result = check_results.get(check, "")
        if any(result.startswith(f) for f in _CHECK_FAIL.get(check, set())):
            failed.append(check)
    return failed


def run_golden_set(cases: list[GoldenCase],
                   cal: WorkingCalendar | None = None) -> GoldenSetResult:
    cal = cal or WorkingCalendar()
    outcomes = []
    for case in cases:
        evaluation = evaluate(case.spec, case.doc, cal,
                              prior_fields=case.prior_fields,
                              materiality=case.materiality)
        actual_failed = _failed_checks(evaluation.check_results)
        expected_set, actual_set = set(case.expected_failed_checks), set(actual_failed)
        false_positives = sorted(actual_set - expected_set)
        misses = sorted(expected_set - actual_set)
        verdict_agrees = evaluation.verdict == case.expected_verdict
        false_return = (evaluation.verdict in RETURN_VERDICTS
                        and case.expected_verdict in ACCEPT_VERDICTS)
        diagnosis = ""
        if not verdict_agrees:
            parts = []
            if false_positives:
                parts.append(f"engine flagged {', '.join(false_positives)} where the CEO saw no defect")
            if misses:
                parts.append(f"engine missed {', '.join(misses)}")
            if not parts:
                parts.append("verdict mapping disagreement with matching checks — "
                             "review §7.4 mapping for this case")
            diagnosis = "; ".join(parts)
        outcomes.append(CaseOutcome(
            case=case, actual_verdict=evaluation.verdict,
            actual_failed_checks=actual_failed, verdict_agrees=verdict_agrees,
            false_return=false_return, check_false_positives=false_positives,
            check_misses=misses, diagnosis=diagnosis,
        ))
    return GoldenSetResult(outcomes)


def report(result: GoldenSetResult) -> str:
    lines = [
        f"GOLDEN SET — {result.total} cases",
        f"verdict agreement: {result.agreement_rate:.0%}",
        f"false returns (gate: must be 0): {result.false_returns}",
        f"check-level false positives: {result.check_false_positive_count} "
        f"of {result.fp_opportunities} opportunities",
        f"GATE: {'PASSED' if result.gate_passed else 'FAILED'}",
    ]
    disagreements = [o for o in result.outcomes if not o.verdict_agrees]
    if disagreements:
        lines.append("")
        lines.append("DISAGREEMENTS, ITEM BY ITEM")
        for o in disagreements:
            lines.append(
                f"  {o.case.case_id}: expected {o.case.expected_verdict}, "
                f"engine said {o.actual_verdict} — {o.diagnosis}"
            )
    return "\n".join(lines)


# -- CEO worksheets (unanchored, D-03) --------------------------------------

def ceo_worksheets(cases: list[GoldenCase], batch_size: int = 10) -> list[str]:
    """Markdown worksheets in batches. The engine's verdict NEVER appears
    — anchoring the human to the machine's answer would produce a test
    the machine cannot fail (D-03)."""
    batches = []
    for start in range(0, len(cases), batch_size):
        chunk = cases[start:start + batch_size]
        lines = [f"# Golden-set worksheet — batch {start // batch_size + 1}",
                 "", "Judge each item independently. 5–8 minutes per item.", ""]
        for case in chunk:
            lines += [
                f"## {case.case_id}",
                f"- Document: {case.doc.attachment_name or '(no attachment)'} "
                f"received {case.doc.received_at:%d-%b-%Y %H:%M}",
                f"- Obligation: {case.spec.name} ({case.spec.obligation_id}), "
                f"due {case.spec.due:%d-%b-%Y %H:%M}",
                f"- Governing form: {case.spec.form_code} rev {case.spec.current_revision}",
                "- Verdict: ____________________",
                "- If not accepted, which checks failed (C1–C7) and why: ____________________",
                "",
            ]
        batches.append("\n".join(lines))
    return batches


# -- growth (§13.1: the set grows continuously) -----------------------------

def add_case(directory: Path, case_id: str, source: str, spec: ObligationSpec,
             doc: SubmissionDoc, expected_verdict: str,
             expected_failed_checks: list[str], ceo_notes: str = "") -> Path:
    if source not in ("initial", "dispute-upheld", "override"):
        raise ValueError(f"unknown case source {source!r}")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", case_id):
        raise ValueError("case_id must be filesystem-safe")
    record = {
        "case_id": case_id,
        "source": source,
        "ceo_notes": ceo_notes,
        "spec": {
            "obligation_id": spec.obligation_id, "name": spec.name,
            "form_code": spec.form_code, "current_revision": spec.current_revision,
            "due": spec.due.isoformat(),
            "mandatory_fields": spec.mandatory_fields,
            "totals": [{"stated_field": t.stated_field,
                        "component_fields": t.component_fields} for t in spec.totals],
            "openings": [{"opening_field": o.opening_field,
                          "prior_closing_field": o.prior_closing_field}
                         for o in spec.openings],
        },
        "doc": {
            "received_at": doc.received_at.isoformat(),
            "attachment_name": doc.attachment_name,
            "form_code": doc.form_code, "revision": doc.revision,
            "fields": doc.fields, "unreadable": doc.unreadable,
            "confidential": doc.confidential,
        },
        "expected": {"verdict": expected_verdict,
                     "failed_checks": expected_failed_checks},
    }
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{case_id}.yaml"
    if path.exists():
        raise FileExistsError(f"case {case_id} already exists — cases are never overwritten")
    path.write_text(yaml.safe_dump(record, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return path


# -- §14.5 regression gate --------------------------------------------------

def regression_gate(baseline: GoldenSetResult,
                    candidate: GoldenSetResult) -> tuple[bool, list[str]]:
    """Reject an adaptation if false positives rise, coverage falls, or
    any previously passing case fails."""
    reasons = []
    newly_failing = candidate.failing_case_ids() - baseline.failing_case_ids()
    if newly_failing:
        reasons.append(f"previously passing case(s) now fail: {', '.join(sorted(newly_failing))}")
    if candidate.check_false_positive_count > baseline.check_false_positive_count:
        reasons.append(
            f"check-level false positives rose "
            f"{baseline.check_false_positive_count} -> {candidate.check_false_positive_count}"
        )
    if candidate.total < baseline.total:
        reasons.append(f"coverage fell: {baseline.total} -> {candidate.total} cases")
    return (not reasons, reasons)
