from datetime import date

import pytest

from control.db import init_db
from control.enforce import TENDER_SCHEDULE, Enforcer, Person
from control.calendar import WorkingCalendar
from control.registers import (
    add_accreditation,
    add_contract,
    add_instrument,
    add_quotation,
    add_tender,
    all_deadlines,
    horizon,
    notice_periods,
)

TODAY = date(2026, 8, 16)


@pytest.fixture
def conn(tmp_path):
    c = init_db(tmp_path / "control.db")
    yield c
    c.close()


def test_tender_dates_become_class2_deadlines(conn):
    add_tender(conn, tender_ref="RFQ-114", client="Canal Sugar",
               title="Piping package", owner="donia@ubcsis.com",
               clarification_deadline="2026-08-25",
               submission_deadline="2026-09-01",
               bid_bond_due="2026-08-28")
    deadlines = {d.item.item_id: d for d in all_deadlines(conn)}

    submission = deadlines["TND-RFQ-114-submission_deadline"]
    assert submission.item.obligation_class == 2
    assert submission.item.schedule == TENDER_SCHEDULE   # includes T-2
    assert submission.item.owner == "donia@ubcsis.com"
    assert "SUBMISSION DEADLINE" in submission.item.name
    assert "TND-RFQ-114-clarification_deadline" in deadlines


def test_guarantee_expiry_and_release_are_both_tracked(conn):
    add_instrument(conn, instrument_ref="LG-9001",
                   instrument_type="PERFORMANCE_BOND",
                   beneficiary="Siemens Energy", expiry_date="2026-09-30",
                   release_date="2026-10-15", owner="accounts@ubcsis.com",
                   amount=500000.0, currency_code="EGP")
    ids = {d.item.item_id for d in all_deadlines(conn)}
    assert "INS-LG-9001-expiry" in ids
    assert "INS-LG-9001-release" in ids     # uncollected money (§2.2)


def test_released_instrument_stops_alerting(conn):
    add_instrument(conn, instrument_ref="LG-1", instrument_type="BID_BOND",
                   expiry_date="2026-09-01", status="OPEN")
    assert any(d.item.item_id.startswith("INS-LG-1") for d in all_deadlines(conn))
    # Append-only correction: a later row supersedes
    add_instrument(conn, instrument_ref="LG-1", instrument_type="BID_BOND",
                   expiry_date="2026-09-01", status="RELEASED")
    assert not any(d.item.item_id.startswith("INS-LG-1") for d in all_deadlines(conn))


def test_accreditation_uses_the_90_60_30_schedule(conn):
    add_accreditation(conn, client="KNAUF", expiry_date="2026-11-30",
                      renewal_owner="donia@ubcsis.com")
    deadline = all_deadlines(conn)[0]
    assert deadline.item.schedule == (90, 60, 30, 0)
    assert "Accreditation expiry" in deadline.item.name


def test_open_quotations_only(conn):
    add_quotation(conn, quote_ref="Q-500", direction="ISSUED",
                  counterparty="Lafarge", valid_until="2026-08-31",
                  status="OPEN", amount=250000.0, currency_code="EGP")
    add_quotation(conn, quote_ref="Q-501", direction="ISSUED",
                  counterparty="Suez Steel", valid_until="2026-08-31",
                  status="WON")
    refs = {d.item.item_id for d in all_deadlines(conn)}
    assert "QTE-Q-500" in refs
    assert "QTE-Q-501" not in refs


def test_contract_notice_periods_are_reported_not_invented(conn):
    add_contract(conn, contract_ref="UB-2026-014", client="Canal Sugar",
                 notice_period_days=28, end_date="2027-01-31",
                 dlp_end_date="2028-01-31", owner="ghareeb@ubcsis.com")
    ids = {d.item.item_id for d in all_deadlines(conn)}
    # Dates that exist become deadlines
    assert "CTR-UB-2026-014-end_date" in ids
    assert "CTR-UB-2026-014-dlp_end_date" in ids
    # The 28-day claim window has no event date, so no date is invented
    assert not any("notice" in i for i in ids)
    assert notice_periods(conn)[0]["notice_period_days"] == 28


def test_horizon_includes_overdue_items(conn):
    add_instrument(conn, instrument_ref="LG-OLD", instrument_type="LETTER_OF_GUARANTEE",
                   expiry_date="2026-07-01")            # already passed
    add_instrument(conn, instrument_ref="LG-SOON", instrument_type="LETTER_OF_GUARANTEE",
                   expiry_date="2026-08-20")            # inside 30 days
    add_instrument(conn, instrument_ref="LG-FAR", instrument_type="LETTER_OF_GUARANTEE",
                   expiry_date="2027-01-01")            # outside
    refs = {d.item.item_id for d in horizon(conn, TODAY, days=30)}
    assert "INS-LG-OLD-expiry" in refs      # an expired guarantee still matters
    assert "INS-LG-SOON-expiry" in refs
    assert "INS-LG-FAR-expiry" not in refs


def test_horizon_is_sorted_by_urgency(conn):
    add_instrument(conn, instrument_ref="B", instrument_type="BID_BOND",
                   expiry_date="2026-08-30")
    add_instrument(conn, instrument_ref="A", instrument_type="BID_BOND",
                   expiry_date="2026-08-18")
    dues = [d.item.due for d in horizon(conn, TODAY, days=30)]
    assert dues == sorted(dues)


def test_deadlines_feed_the_enforcement_engine(conn):
    """The point of the registers: real alerts, not a spreadsheet."""
    add_tender(conn, tender_ref="RFQ-200", client="Lafarge",
               submission_deadline="2026-08-18", owner="donia@ubcsis.com")
    enforcer = Enforcer(WorkingCalendar(),
                        {"donia@ubcsis.com": Person("donia@ubcsis.com",
                                                    "info@ubcsis.com", 2)},
                        ceo="ahmed@ubcsis.com", coo="ghareeb@ubcsis.com",
                        cfo="accounts@ubcsis.com")
    deadline = next(d for d in all_deadlines(conn)
                    if d.item.item_id.endswith("submission_deadline"))
    actions = enforcer.plan_class12(deadline.item, TODAY)   # T-2
    assert actions and actions[0].dedupe_key.endswith(":T-2")
    assert actions[0].never_suppress is True
