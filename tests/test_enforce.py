from datetime import date

import pytest

from control.calendar import WorkingCalendar
from control.enforce import (
    Absence,
    Enforcer,
    Person,
    TENDER_SCHEDULE,
    TrackedItem,
)

CEO, COO, CFO = "ahmed@ubcsis.com", "ghareeb@ubcsis.com", "accounts@ubcsis.com"

ROSTER = {
    "a.elsayed@ubcsis.com": Person("a.elsayed@ubcsis.com", COO, 2),
    "hadeer@ubcsis.com": Person("hadeer@ubcsis.com", CFO, 1),
    "info@ubcsis.com": Person("info@ubcsis.com", CEO, 3),  # Ahmed Hassan
}


@pytest.fixture
def enf():
    return Enforcer(WorkingCalendar(), ROSTER, ceo=CEO, coo=COO, cfo=CFO)


def item(**kw):
    base = dict(item_id="OPS-WPR-001", obligation_class=3, name="Weekly progress",
                owner="a.elsayed@ubcsis.com", due=date(2026, 8, 13))  # Thursday
    base.update(kw)
    return TrackedItem(**base)


# -- class 1/2 deadline engine -------------------------------------------

def test_class1_schedule_and_day_of_goes_to_ceo_cfo(enf):
    it = item(item_id="STAT-VAT", obligation_class=1, name="VAT return",
              owner="hadeer@ubcsis.com", due=date(2026, 8, 20))
    assert enf.plan_class12(it, date(2026, 8, 13))[0].dedupe_key == "STAT-VAT:T-7"
    assert enf.plan_class12(it, date(2026, 8, 14)) == []  # 6 days out: not in schedule
    day_of = enf.plan_class12(it, date(2026, 8, 20))[0]
    assert day_of.recipients == [CEO, CFO]
    assert day_of.never_suppress


def test_class12_fires_on_weekend(enf):
    # T-1 lands on Friday (non-working): class 1/2 ignore the calendar.
    it = item(item_id="TND-9", obligation_class=2, name="Tender", owner="donia@ubcsis.com",
              due=date(2026, 8, 15))  # Saturday
    a = enf.plan_class12(it, date(2026, 8, 14))  # Friday
    assert a and a[0].dedupe_key == "TND-9:T-1"


def test_class2_overdue_stays_daily(enf):
    it = item(item_id="TND-9", obligation_class=2, name="Tender", owner="donia@ubcsis.com",
              due=date(2026, 8, 10))
    a1 = enf.plan_class12(it, date(2026, 8, 12))[0]
    a2 = enf.plan_class12(it, date(2026, 8, 13))[0]
    assert a1.dedupe_key != a2.dedupe_key  # daily, distinct keys
    assert CEO in a1.recipients


def test_tender_schedule_includes_t2(enf):
    it = item(item_id="TND-114", obligation_class=2, name="RFQ 114 submission",
              owner="donia@ubcsis.com", due=date(2026, 8, 20), schedule=TENDER_SCHEDULE)
    assert enf.plan_class12(it, date(2026, 8, 18))[0].dedupe_key == "TND-114:T-2"


# -- class 3 ladder ------------------------------------------------------

def test_pre_reminder_and_deadline(enf):
    assert enf.plan_class3(item(), date(2026, 8, 12))[0].kind == "PRE_REMINDER"
    assert enf.plan_class3(item(), date(2026, 8, 13))[0].kind == "DEADLINE"


def test_monthly_gets_48h_lead(enf):
    it = item(monthly=True)
    assert enf.plan_class3(it, date(2026, 8, 11))[0].kind == "PRE_REMINDER"
    assert enf.plan_class3(it, date(2026, 8, 12)) == []


def test_ladder_stages_and_recipients(enf):
    it = item()
    # Sunday 16th = 1 working day late -> L1 owner + manager
    acts = enf.plan_class3(it, date(2026, 8, 16))
    assert [a.kind for a in acts] == ["L1"]
    assert acts[0].cc == [COO]
    # Tuesday 18th = 3 wd late -> L1+L2 emitted (dedupe filters sent ones)
    kinds = [a.kind for a in enf.plan_class3(it, date(2026, 8, 18))]
    assert kinds == ["L1", "L2"]
    # Thursday 20th = 5 wd late -> L3 includes CEO
    l3 = [a for a in enf.plan_class3(it, date(2026, 8, 20)) if a.kind == "L3"][0]
    assert CEO in l3.recipients and COO in l3.recipients


def test_financial_l2_goes_to_cfo(enf):
    it = item(item_id="FIN-TB", financial=True, owner="hadeer@ubcsis.com")
    l2 = [a for a in enf.plan_class3(it, date(2026, 8, 18)) if a.kind == "L2"][0]
    assert CFO in l2.recipients and COO not in l2.recipients


def test_ahmed_hassan_l1_reaches_ceo_and_ladder_continues(enf):
    it = item(item_id="PROC-1", owner="info@ubcsis.com")
    l1 = enf.plan_class3(it, date(2026, 8, 16))[0]
    assert l1.cc == [CEO]  # manager IS the CEO -> first notice advanced (§3.2)
    l3 = [a for a in enf.plan_class3(it, date(2026, 8, 20)) if a.kind == "L3"][0]
    assert COO in l3.recipients  # ladder continues, never shortens (v4.3)


def test_no_class3_on_weekend(enf):
    assert enf.plan_class3(item(), date(2026, 8, 14)) == []  # Friday


def test_dispute_suspends_clock(enf):
    assert enf.plan_class3(item(), date(2026, 8, 18), dispute_active=True) == []


def test_submitted_item_is_silent(enf):
    assert enf.plan_class3(item(), date(2026, 8, 13), submitted=True) == []


def test_reliability_suppresses_pre_reminder_only(enf):
    assert enf.plan_class3(item(), date(2026, 8, 12), reliable=True) == []
    assert enf.plan_class3(item(), date(2026, 8, 13), reliable=True)[0].kind == "DEADLINE"


def test_absence_routes_to_delegate_no_escalation(enf):
    ab = Absence(delegate="shymaa@ubcsis.com")
    d = enf.plan_class3(item(), date(2026, 8, 13), absence=ab)
    assert d[0].recipients == ["shymaa@ubcsis.com"]
    # Past due during leave: escalation suspended entirely (§3.3)
    assert enf.plan_class3(item(), date(2026, 8, 18), absence=ab) == []


def test_absence_without_delegate_is_process_finding(enf):
    acts = enf.plan_class3(item(), date(2026, 8, 13), absence=Absence(delegate=None))
    kinds = {a.kind for a in acts}
    assert "PROCESS_FINDING" in kinds
    finding = next(a for a in acts if a.kind == "PROCESS_FINDING")
    assert "delegation not registered" in finding.note
    deadline = next(a for a in acts if a.kind == "DEADLINE")
    assert deadline.recipients == [COO]  # routed to the manager


def test_class4_single_reminder(enf):
    it = item(item_id="INFO-1", obligation_class=4)
    assert enf.plan_class4(it, date(2026, 8, 13))[0].kind == "DEADLINE"
    assert enf.plan_class4(it, date(2026, 8, 16)) == []  # no escalation, ever


def test_consolidation_separates_immediate(enf):
    it3 = item()
    it1 = item(item_id="STAT-VAT", obligation_class=1, name="VAT",
               owner="hadeer@ubcsis.com", due=date(2026, 8, 13))
    acts = enf.plan_class3(it3, date(2026, 8, 13)) + enf.plan_class12(it1, date(2026, 8, 13))
    buckets = enf.consolidate(acts)
    assert "a.elsayed@ubcsis.com" in buckets
    assert f"!immediate:{CEO}" in buckets  # class 1 day-of bypasses limits
