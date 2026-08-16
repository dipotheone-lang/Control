"""Dotted-line reporting — O-01, confirmed by the CEO 16-Aug-2026.

Hadeer Mohamed reports to the Acting CFO, but to HR on HR matters.
Escalating an HR item to the CFO would route a personnel question to
the wrong manager; escalating a financial item to HR would do the
reverse.
"""

from datetime import date

import pytest

from control.calendar import WorkingCalendar
from control.enforce import Enforcer, Person, TrackedItem

CEO, COO, CFO, HR = ("ahmed@ubcsis.com", "ghareeb@ubcsis.com",
                     "accounts@ubcsis.com", "hr@ubcsis.com")
HADEER = "hadeer@ubcsis.com"

ROSTER = {
    HADEER: Person(HADEER, CFO, 1, also_manager=HR, also_domain="hr"),
    "shymaa@ubcsis.com": Person("shymaa@ubcsis.com", CEO, 2),
}


@pytest.fixture
def enf():
    return Enforcer(WorkingCalendar(), ROSTER, ceo=CEO, coo=COO, cfo=CFO)


def _item(**kw):
    base = dict(item_id="X", obligation_class=3, name="item", owner=HADEER,
                due=date(2026, 8, 13))          # Thursday
    base.update(kw)
    return TrackedItem(**base)


LATE = date(2026, 8, 16)                         # Sunday, 1 working day late


def test_default_line_is_the_primary_manager(enf):
    l1 = enf.plan_class3(_item(), LATE)[0]
    assert l1.cc == [CFO]


def test_hr_items_escalate_to_hr_not_the_cfo(enf):
    l1 = enf.plan_class3(_item(domain="hr"), LATE)[0]
    assert l1.cc == [HR]
    assert CFO not in l1.cc


def test_an_unrelated_domain_falls_back_to_the_primary_line(enf):
    l1 = enf.plan_class3(_item(domain="procurement"), LATE)[0]
    assert l1.cc == [CFO]


def test_person_without_a_dotted_line_is_unaffected(enf):
    l1 = enf.plan_class3(_item(owner="shymaa@ubcsis.com", domain="hr"), LATE)[0]
    assert l1.cc == [CEO]        # Shymaa reports to the CEO, no second line


def test_manager_for_resolves_directly():
    hadeer = ROSTER[HADEER]
    assert hadeer.manager_for(None) == CFO
    assert hadeer.manager_for("hr") == HR
    assert hadeer.manager_for("finance") == CFO


def test_config_carries_the_dotted_line():
    """The roster file must actually express what the CEO confirmed."""
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parent.parent / "config" / "people.yaml"
    people = yaml.safe_load(path.read_text(encoding="utf-8"))["people"]
    hadeer = next(p for p in people if p["email"] == HADEER)

    assert hadeer["reports_to"] == CFO
    assert hadeer["also_reports_to"] == HR
    assert hadeer["also_reports_to_domain"] == "hr"
    assert hadeer["confirmed"] is True


def test_all_reporting_lines_are_confirmed():
    """O-01 is closed: nothing may still be routing on an inference."""
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parent.parent / "config" / "people.yaml"
    people = yaml.safe_load(path.read_text(encoding="utf-8"))["people"]
    unconfirmed = [p["email"] for p in people if not p.get("confirmed")]
    assert unconfirmed == [], f"still inferred: {unconfirmed}"


def test_corrected_lines_match_the_ceo_answer():
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parent.parent / "config" / "people.yaml"
    people = {p["email"]: p for p in
              yaml.safe_load(path.read_text(encoding="utf-8"))["people"]}

    # Corrected during O-01: both had been inferred as reporting to the COO.
    assert people["shymaa@ubcsis.com"]["reports_to"] == CEO
    assert people["hr@ubcsis.com"]["reports_to"] == CEO
    # Unchanged
    assert people["donia@ubcsis.com"]["reports_to"] == "info@ubcsis.com"
    assert people["marketing@ubcsis.com"]["reports_to"] == "info@ubcsis.com"
    assert people["a.elsayed@ubcsis.com"]["reports_to"] == COO
    assert people["hse@ubcsis.com"]["reports_to"] == COO
