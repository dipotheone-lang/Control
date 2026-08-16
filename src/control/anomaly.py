"""Substantive checks S1–S4 — charter §7.3.

Flags, never accusations: every flag is a factual observation routed to
the CEO (and CFO where financial). Flags never change a verdict and
never appear in the submitter's reply — routing enforces that; this
module only produces them.

Signals stay honest about their preconditions:
- the out-of-hours signal is silent until working hours are set
  (sla.yaml, decision O-11 — §8.3)
- statistical outliers are silent below the minimum sample size
  (§7.2 minimum-sample rule; three invoices are not a distribution)
- S2 delegated-limit checks with no configured limit flag the missing
  limit itself (O-02) instead of pretending to verify
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Flag:
    signal: str            # S1 | S2 | S3 | S4
    code: str
    detail: str
    subject_ref: str = ""
    priority: str = "NORMAL"       # HIGHEST reserved for bank-detail changes
    refs: list[str] = field(default_factory=list)


def record_flag(conn, flag: Flag) -> None:
    conn.execute(
        "INSERT INTO anomalies (signal, detail, subject_ref, flagged_to, source)"
        " VALUES (?, ?, ?, 'CEO', 'LIVE')",
        (flag.signal, f"[{flag.code}] {flag.detail}", flag.subject_ref),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# S1 — anomaly and fraud signals
# ---------------------------------------------------------------------------

def s1_bank_detail_change(supplier: str, presented_account: str,
                          known_accounts: list[str]) -> Flag | None:
    """The highest-priority flag in the system. Never act on the change —
    flag it, and payment proceeds only after callback verification on a
    known number (§7.3, §10)."""
    if not known_accounts or presented_account in known_accounts:
        return None
    return Flag(
        signal="S1", code="BANK_DETAIL_CHANGE", priority="HIGHEST",
        subject_ref=supplier,
        detail=(
            f"Supplier {supplier}: presented account differs from every account "
            f"on record. No action taken. Verify by callback on a known number "
            "before any payment. Most common SME payment fraud in Egypt."
        ),
    )


def s1_duplicate_invoice(invoices: list[dict], window_days: int = 90) -> list[Flag]:
    """Same supplier + same value twice within the window.
    invoices: [{supplier, value, date: datetime, ref}]"""
    flags = []
    by_key: dict[tuple, list[dict]] = {}
    for inv in invoices:
        by_key.setdefault((inv["supplier"], inv["value"]), []).append(inv)
    for (supplier, value), group in by_key.items():
        group = sorted(group, key=lambda i: i["date"])
        for a, b in zip(group, group[1:]):
            if b["date"] - a["date"] <= timedelta(days=window_days):
                flags.append(Flag(
                    signal="S1", code="DUPLICATE_INVOICE", subject_ref=supplier,
                    detail=(f"Supplier {supplier}: value {value} appears twice "
                            f"within {window_days} days"),
                    refs=[a["ref"], b["ref"]],
                ))
    return flags


def s1_round_number_clustering(values: list[float], *, min_count: int = 5,
                               share_threshold: float = 0.6,
                               round_to: float = 1000.0) -> Flag | None:
    if len(values) < min_count:
        return None
    round_count = sum(1 for v in values if v and v % round_to == 0)
    share = round_count / len(values)
    if share >= share_threshold:
        return Flag(
            signal="S1", code="ROUND_NUMBER_CLUSTERING",
            detail=(f"{round_count} of {len(values)} values are multiples of "
                    f"{round_to:g} ({share:.0%})"),
        )
    return None


def s1_sequence_anomalies(sequence: list[tuple[str, int]]) -> list[Flag]:
    """Gaps or reversals in PR/PO/invoice numbering.
    sequence: [(ref, number)] in the order recorded."""
    flags = []
    for (ref_a, a), (ref_b, b) in zip(sequence, sequence[1:]):
        if b < a:
            flags.append(Flag(
                signal="S1", code="SEQUENCE_REVERSAL",
                detail=f"{ref_b} ({b}) recorded after {ref_a} ({a})",
                refs=[ref_a, ref_b],
            ))
        elif b > a + 1:
            flags.append(Flag(
                signal="S1", code="SEQUENCE_GAP",
                detail=f"{b - a - 1} missing number(s) between {ref_a} ({a}) and {ref_b} ({b})",
                refs=[ref_a, ref_b],
            ))
    return flags


def s1_award_concentration(awards: list[dict], *, run_length: int = 3) -> Flag | None:
    """Consecutive awards to one supplier without competing quotations.
    awards: [{supplier, ref, competing_quotes: int}] in award order."""
    run: list[dict] = []
    for award in awards:
        if run and award["supplier"] == run[-1]["supplier"] and award["competing_quotes"] == 0:
            run.append(award)
        elif award["competing_quotes"] == 0:
            run = [award]
        else:
            run = []
        if len(run) >= run_length:
            return Flag(
                signal="S1", code="AWARD_CONCENTRATION",
                subject_ref=award["supplier"],
                detail=(f"{len(run)} consecutive awards to {award['supplier']} "
                        "with no competing quotations on file"),
                refs=[a["ref"] for a in run],
            )
    return None


def s1_out_of_hours(submitted_at: datetime, working_hours: dict | None) -> Flag | None:
    """Silent until working hours are configured and confirmed (O-11, §8.3).

    The confirmation is part of the precondition, not paperwork around
    it. This signal produces observations about when named people work;
    an unconfirmed config edit must not be able to switch that on.
    """
    if not working_hours or not working_hours.get("start") or not working_hours.get("end"):
        return None
    if not working_hours.get("confirmed_by_ceo"):
        return None
    start = datetime.strptime(working_hours["start"], "%H:%M").time()
    end = datetime.strptime(working_hours["end"], "%H:%M").time()
    t = submitted_at.time()
    if start <= t <= end:
        return None
    return Flag(
        signal="S1", code="OUT_OF_HOURS",
        detail=f"Submission timestamped {submitted_at:%d-%b-%Y %H:%M}, outside "
               f"working hours {working_hours['start']}–{working_hours['end']}",
    )


def s1_statistical_outlier(metric: str, value: float, *, mean: float, stdev: float,
                           sample_size: int, min_sample: int,
                           z_threshold: float = 3.0) -> Flag | None:
    """§7.2 minimum-sample rule: INSUFFICIENT baselines never flag."""
    if sample_size < min_sample or stdev <= 0:
        return None
    z = abs(value - mean) / stdev
    if z < z_threshold:
        return None
    return Flag(
        signal="S1", code="STATISTICAL_OUTLIER", subject_ref=metric,
        detail=(f"{metric}: value {value:g} is {z:.1f} standard deviations from "
                f"its own history (mean {mean:g}, n={sample_size})"),
    )


# ---------------------------------------------------------------------------
# S2 — authority
# ---------------------------------------------------------------------------

def s2_authority(*, originator: str, approver: str | None, value: float,
                 delegated_limits: dict, second_approval_present: bool = True,
                 second_approval_required_above: float | None = None,
                 ref: str = "") -> list[Flag]:
    flags = []
    if approver is None:
        flags.append(Flag("S2", "NO_APPROVER",
                          f"No approver recorded on {ref or 'document'}", ref))
    elif approver == originator:
        flags.append(Flag("S2", "APPROVER_IS_ORIGINATOR",
                          f"{originator} appears as both originator and approver"
                          f" on {ref or 'document'}", ref))
    if approver:
        limit = delegated_limits.get(approver)
        if limit is None:
            # O-02 open: the missing limit is the finding (v4.3/V5 —
            # itemise everything until authority.yaml is populated).
            flags.append(Flag("S2", "LIMIT_NOT_SET",
                              f"No delegated limit configured for {approver} "
                              "(O-02) — itemised to CEO by default", ref))
        elif value > limit:
            flags.append(Flag("S2", "LIMIT_EXCEEDED",
                              f"Value {value:g} exceeds {approver}'s delegated "
                              f"limit {limit:g}", ref))
    if (second_approval_required_above is not None
            and value > second_approval_required_above
            and not second_approval_present):
        flags.append(Flag("S2", "SECOND_APPROVAL_MISSING",
                          f"Value {value:g} requires a second approval "
                          f"(threshold {second_approval_required_above:g})", ref))
    return flags


# ---------------------------------------------------------------------------
# S3 — implausible perfection
# ---------------------------------------------------------------------------

def s3_implausible_perfection(metric: str, series: list[float], *,
                              min_length: int = 6) -> Flag | None:
    """Flat series and unbroken zero-incident records are a verification
    request, not compliance credit."""
    if len(series) < min_length:
        return None
    if all(v == series[0] for v in series):
        kind = ("unbroken zero record" if series[0] == 0
                else f"identical value {series[0]:g}")
        return Flag(
            signal="S3", code="IMPLAUSIBLE_PERFECTION", subject_ref=metric,
            detail=(f"{metric}: {kind} across {len(series)} consecutive periods "
                    "— verification requested, not credited"),
        )
    return None


# ---------------------------------------------------------------------------
# S4 — cross-source reconciliation
# ---------------------------------------------------------------------------

def s4_reconcile(name_a: str, value_a: float, name_b: str, value_b: float, *,
                 floor_abs: float, floor_pct: float, ref: str = "") -> Flag | None:
    delta = value_a - value_b
    if abs(delta) < floor_abs:
        return None
    base = max(abs(value_a), abs(value_b))
    if base and abs(delta) / base * 100 < floor_pct:
        return None
    return Flag(
        signal="S4", code="CROSS_SOURCE_DIVERGENCE", subject_ref=ref,
        detail=(f"{name_a} ({value_a:g}) vs {name_b} ({value_b:g}): "
                f"divergence {delta:+g} beyond materiality"),
    )
