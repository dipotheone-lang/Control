from datetime import datetime

import pytest

from control.calendar import WorkingCalendar
from control.db import init_db
from control.watchdog import SlaRule, Watchdog, _deadline, parse_sla_config

CAL = WorkingCalendar()

RULES = {
    "client_rfq_tender": SlaRule("client_rfq_tender", "4h", "1d",
                                 "donia@ubcsis.com", "info@ubcsis.com"),
    "client_complaint": SlaRule("client_complaint", "2h", "same-day",
                                "ghareeb@ubcsis.com", "ahmed@ubcsis.com"),
    "supplier": SlaRule("supplier", "1d", "2d",
                        "info@ubcsis.com", "ghareeb@ubcsis.com"),
    "unclassified": SlaRule("unclassified", "1d", "2d",
                            "ghareeb@ubcsis.com", "ahmed@ubcsis.com"),
}
MANAGERS = {"donia@ubcsis.com": "info@ubcsis.com",
            "ghareeb@ubcsis.com": "ahmed@ubcsis.com"}


@pytest.fixture
def wd(tmp_path):
    conn = init_db(tmp_path / "control.db")
    yield Watchdog(conn, RULES, CAL, MANAGERS)
    conn.close()


RECEIVED = datetime(2026, 8, 13, 9, 0)  # Thursday morning


def test_deadline_parsing():
    assert _deadline(RECEIVED, "4h", CAL) == datetime(2026, 8, 13, 13, 0)
    assert _deadline(RECEIVED, "same-day", CAL) == datetime(2026, 8, 13, 23, 59)
    # 1 working day from Thursday -> Sunday (Fri/Sat weekend)
    assert _deadline(RECEIVED, "1d", CAL) == datetime(2026, 8, 16, 9, 0)


def test_observed_reply_closes(wd):
    wd.register_inbound("T1", "client_rfq_tender", RECEIVED)
    wd.observe_reply("T1", datetime(2026, 8, 13, 10, 0))
    assert wd.open_threads() == []
    assert wd.cc_compliance()["CLOSED_OBSERVED_REPLY"] == 1


def test_declared_close_logs_declarant(wd):
    wd.register_inbound("T2", "client_rfq_tender", RECEIVED)
    wd.declare_closed("T2", "donia@ubcsis.com", datetime(2026, 8, 13, 11, 0))
    row = wd.conn.execute(
        "SELECT declarant FROM external_threads WHERE thread_id='T2'"
        " ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] == "donia@ubcsis.com"
    assert wd.cc_compliance()["CLOSED_DECLARED"] == 1


def test_first_breach_notifies_owner_only_with_observation_wording(wd):
    wd.register_inbound("T3", "client_rfq_tender", RECEIVED)
    actions = wd.check(datetime(2026, 8, 13, 14, 0))  # past 4h, before 1d
    assert len(actions) == 1
    a = actions[0]
    assert a.recipients == ["donia@ubcsis.com"]
    assert a.dedupe_key == "WD:T3:FIRST"
    assert "no reply visible to Control" in a.note
    assert "no reply sent" not in a.note


def test_final_breach_adds_manager_and_marks_breached(wd):
    wd.register_inbound("T4", "client_rfq_tender", RECEIVED)
    actions = wd.check(datetime(2026, 8, 17, 9, 0))  # past 1d final
    a = actions[0]
    assert a.recipients == ["donia@ubcsis.com", "info@ubcsis.com"]
    assert a.dedupe_key == "WD:T4:FINAL"
    assert wd.cc_compliance()["BREACHED"] == 1
    # A late observed reply still closes a breached thread
    wd.observe_reply("T4", datetime(2026, 8, 17, 12, 0))
    assert wd.cc_compliance()["CLOSED_OBSERVED_REPLY"] == 1


def test_no_notice_before_sla(wd):
    wd.register_inbound("T5", "client_rfq_tender", RECEIVED)
    assert wd.check(datetime(2026, 8, 13, 10, 0)) == []


def test_unknown_category_falls_to_unclassified(wd):
    wd.register_inbound("T6", "weird-category", RECEIVED)
    current = wd._current("T6")
    assert current["category"] == "unclassified"


def test_recipients_always_internal(wd):
    wd.register_inbound("T7", "client_complaint", RECEIVED)
    actions = wd.check(datetime(2026, 8, 14, 9, 0))
    for a in actions:
        for r in a.recipients:
            assert r.endswith("@ubcsis.com")   # never the external party


def test_cc_compliance_shares(wd):
    wd.register_inbound("A", "supplier", RECEIVED)
    wd.register_inbound("B", "supplier", RECEIVED)
    wd.register_inbound("C", "supplier", RECEIVED)
    wd.observe_reply("A", datetime(2026, 8, 13, 12, 0))
    wd.declare_closed("B", "info@ubcsis.com", datetime(2026, 8, 13, 12, 0))
    m = wd.cc_compliance()
    assert m["CLOSED_OBSERVED_REPLY"] == 1 and m["CLOSED_DECLARED"] == 1
    assert m["OPEN"] == 1
    assert m["observed_share"] == 0.5


def test_repo_sla_yaml_parses():
    from pathlib import Path

    import yaml

    sla_path = Path(__file__).resolve().parent.parent / "config" / "sla.yaml"
    config = yaml.safe_load(sla_path.read_text(encoding="utf-8"))
    rules = parse_sla_config(config["external_sla"])
    assert rules["client_complaint"].first == "2h"
    assert rules["unclassified"].owner == "ghareeb@ubcsis.com"
