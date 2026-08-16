from datetime import datetime

from control.anomaly import (
    s1_award_concentration,
    s1_bank_detail_change,
    s1_duplicate_invoice,
    s1_out_of_hours,
    s1_round_number_clustering,
    s1_sequence_anomalies,
    s1_statistical_outlier,
    s2_authority,
    s3_implausible_perfection,
    s4_reconcile,
)


def test_bank_detail_change_is_highest_priority():
    f = s1_bank_detail_change("Steel Co", "EG-NEW-ACCT", ["EG-OLD-ACCT"])
    assert f.priority == "HIGHEST" and "No action taken" in f.detail
    assert s1_bank_detail_change("Steel Co", "EG-OLD-ACCT", ["EG-OLD-ACCT"]) is None
    assert s1_bank_detail_change("Steel Co", "EG-X", []) is None  # nothing on record


def test_duplicate_invoice_window():
    invoices = [
        {"supplier": "Steel Co", "value": 50000.0, "date": datetime(2026, 5, 1), "ref": "INV-1"},
        {"supplier": "Steel Co", "value": 50000.0, "date": datetime(2026, 7, 1), "ref": "INV-2"},
        {"supplier": "Steel Co", "value": 50000.0, "date": datetime(2026, 11, 1), "ref": "INV-3"},
    ]
    flags = s1_duplicate_invoice(invoices)
    assert len(flags) == 1                     # 1->2 within 90 days; 2->3 is 123 days
    assert flags[0].refs == ["INV-1", "INV-2"]


def test_round_number_clustering():
    assert s1_round_number_clustering([5000.0, 10000.0, 20000.0, 3000.0, 7500.0]) is not None
    assert s1_round_number_clustering([5123.0, 10001.0, 20002.0, 3000.0, 7500.0]) is None
    assert s1_round_number_clustering([5000.0, 10000.0]) is None  # below min_count


def test_sequence_gaps_and_reversals():
    flags = s1_sequence_anomalies([("PO-A", 1001), ("PO-B", 1002), ("PO-C", 1005), ("PO-D", 1004)])
    codes = [f.code for f in flags]
    assert codes == ["SEQUENCE_GAP", "SEQUENCE_REVERSAL"]


def test_award_concentration():
    awards = [
        {"supplier": "Steel Co", "ref": "AW-1", "competing_quotes": 0},
        {"supplier": "Steel Co", "ref": "AW-2", "competing_quotes": 0},
        {"supplier": "Steel Co", "ref": "AW-3", "competing_quotes": 0},
    ]
    f = s1_award_concentration(awards)
    assert f and f.refs == ["AW-1", "AW-2", "AW-3"]
    awards[1]["competing_quotes"] = 2          # a competed award breaks the run
    assert s1_award_concentration(awards) is None


def test_out_of_hours_silent_until_o11():
    late = datetime(2026, 8, 13, 23, 30)
    assert s1_out_of_hours(late, None) is None
    assert s1_out_of_hours(late, {"start": None, "end": None}) is None    # O-11 open
    hours = {"start": "08:00", "end": "17:00", "confirmed_by_ceo": True}
    assert s1_out_of_hours(late, hours) is not None
    assert s1_out_of_hours(datetime(2026, 8, 13, 10, 0), hours) is None


def test_out_of_hours_needs_the_confirmation_not_just_the_numbers():
    """This signal observes when named people work. An unconfirmed
    config edit must not be able to switch that on (§8.3, O-11)."""
    late = datetime(2026, 8, 13, 23, 30)
    unconfirmed = {"start": "09:00", "end": "17:00", "confirmed_by_ceo": False}
    assert s1_out_of_hours(late, unconfirmed) is None
    assert s1_out_of_hours(late, {"start": "09:00", "end": "17:00"}) is None


def test_repo_sla_config_closes_o11_at_nine_to_five():
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parent.parent / "config" / "sla.yaml"
    hours = yaml.safe_load(path.read_text(encoding="utf-8"))[
        "working_calendar"]["working_hours"]
    assert hours["start"] == "09:00" and hours["end"] == "17:00"
    assert hours["confirmed_by_ceo"] is True
    # Recorded honestly: the CEO set these, not HR, and the IWR still
    # needs to agree with them (O-06).
    assert hours["set_by"] == "ahmed@ubcsis.com"
    assert hours["hr_countersign_pending"] is True

    # The signal is live against the real config.
    assert s1_out_of_hours(datetime(2026, 8, 13, 22, 15), hours) is not None
    assert s1_out_of_hours(datetime(2026, 8, 13, 11, 0), hours) is None


def test_statistical_outlier_respects_minimum_sample():
    kw = dict(mean=100.0, stdev=10.0, z_threshold=3.0)
    assert s1_statistical_outlier("price", 150.0, sample_size=30, min_sample=12, **kw)
    assert s1_statistical_outlier("price", 150.0, sample_size=3, min_sample=12, **kw) is None
    assert s1_statistical_outlier("price", 120.0, sample_size=30, min_sample=12, **kw) is None


def test_s2_authority_matrix():
    limits = {"ghareeb@ubcsis.com": 200000.0}
    flags = s2_authority(originator="info@ubcsis.com", approver="info@ubcsis.com",
                         value=50000.0, delegated_limits={}, ref="PO-9")
    codes = {f.code for f in flags}
    assert "APPROVER_IS_ORIGINATOR" in codes and "LIMIT_NOT_SET" in codes

    flags = s2_authority(originator="info@ubcsis.com", approver="ghareeb@ubcsis.com",
                         value=250000.0, delegated_limits=limits, ref="PO-10")
    assert [f.code for f in flags] == ["LIMIT_EXCEEDED"]

    flags = s2_authority(originator="info@ubcsis.com", approver="ghareeb@ubcsis.com",
                         value=150000.0, delegated_limits=limits,
                         second_approval_present=False,
                         second_approval_required_above=100000.0, ref="PO-11")
    assert [f.code for f in flags] == ["SECOND_APPROVAL_MISSING"]

    assert s2_authority(originator="info@ubcsis.com", approver="ghareeb@ubcsis.com",
                        value=50000.0, delegated_limits=limits) == []


def test_s3_implausible_perfection():
    f = s3_implausible_perfection("HSE incidents", [0.0] * 12)
    assert f and "zero record" in f.detail and "verification" in f.detail
    assert s3_implausible_perfection("progress", [80.0] * 8).code == "IMPLAUSIBLE_PERFECTION"
    assert s3_implausible_perfection("progress", [80.0, 82.0, 85.0, 90.0, 91.0, 95.0]) is None
    assert s3_implausible_perfection("progress", [80.0] * 3) is None  # too short


def test_s4_reconciliation_materiality():
    kw = dict(floor_abs=10000.0, floor_pct=5.0)
    f = s4_reconcile("site progress value", 1000000.0, "invoiced value", 800000.0, **kw)
    assert f and "+200000" in f.detail
    assert s4_reconcile("a", 1000000.0, "b", 995000.0, **kw) is None      # below abs floor? 5000<10000
    assert s4_reconcile("a", 1000000.0, "b", 985000.0, **kw) is None      # 1.5% < 5%
