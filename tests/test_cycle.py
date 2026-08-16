import io
import shutil
from datetime import date, datetime
from pathlib import Path

import openpyxl
import pytest

from control.calendar import WorkingCalendar
from control.cycle import Class3State, SubmissionSpec, run_cycle
from control.enforce import Enforcer, Person, TrackedItem
from control.evaluate import ObligationSpec, TotalRule
from control.startup import run_startup
from control.transport import FetchedMessage, MockTransport

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
CEO, COO, CFO = "ahmed@ubcsis.com", "ghareeb@ubcsis.com", "accounts@ubcsis.com"


def _xlsx(cells: dict[str, object]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for ref, value in cells.items():
        ws[ref] = value
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def env(tmp_path):
    ub_root = tmp_path / "UB"
    control_root = ub_root / "CONTROL"
    (control_root / "data").mkdir(parents=True)
    (control_root / "logs").mkdir()
    shutil.copytree(REPO_CONFIG, control_root / "config")
    # These tests run a SUPERVISED cycle, which D-08 does not permit on
    # the interim Outlook route. A Phase 2 world is a Graph world, so
    # the fixture builds one rather than weakening the gate.
    transport = control_root / "config" / "transport.yaml"
    transport.write_text(
        transport.read_text(encoding="utf-8").replace(
            "route: outlook_com", "route: graph", 1),
        encoding="utf-8")
    startup = run_startup(control_root, ub_root, "SUPERVISED", "OBSERVE", 2, "2026-08-13")
    return startup, control_root


SPEC = ObligationSpec(
    obligation_id="OPS-WPR-001", name="Weekly progress", form_code="FRM-WPR",
    current_revision="3", due=datetime(2026, 8, 13, 12, 0),
    mandatory_fields=["B2"], totals=[TotalRule("B10", ["B4", "B5"])],
)
SPECS = {"OPS-WPR-001": SubmissionSpec(
    spec=SPEC, mapping={"B2": "Sheet1!B2", "B4": "Sheet1!B4",
                        "B5": "Sheet1!B5", "B10": "Sheet1!B10"},
    surname="Elsayed", period="2026-W33",
)}

ROSTER = {"a.elsayed@ubcsis.com": Person("a.elsayed@ubcsis.com", COO, 2)}


def _enforcer():
    return Enforcer(WorkingCalendar(), ROSTER, ceo=CEO, coo=COO, cfo=CFO)


def _submission_msg(content: bytes, filename="FRM-WPR_w33.xlsx"):
    return FetchedMessage(
        message_id="<s1@ubcsis.com>", sender="a.elsayed@ubcsis.com",
        received_at=datetime(2026, 8, 13, 9, 0), subject="Weekly progress W33",
        attachments=[(filename, content)],
    )


def test_clean_submission_end_to_end(env):
    startup, control_root = env
    transport = MockTransport([_submission_msg(_xlsx({"B2": 5, "B4": 1.0, "B5": 2.0, "B10": 3.0}))])
    report = run_cycle(startup, transport, control_root, specs=SPECS,
                       enforcer=_enforcer(), today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
    assert report.verdicts["<s1@ubcsis.com>"] == "ACCEPTED"
    # SUPERVISED: verdict replies draft, never send (§10)
    assert transport.outgoing == []
    assert len(report.drafted) == 1
    ok, detail = startup.audit.verify()
    assert ok, detail


def test_fraud_signal_sends_to_ceo_cfo_never_sender(env):
    startup, control_root = env
    fraud = FetchedMessage(
        message_id="<f1@x>", sender="accounts@siemens-emergy.com",
        received_at=datetime(2026, 8, 13, 9, 0),
        subject="Updated bank account for invoice 2214",
    )
    transport = MockTransport([fraud])
    report = run_cycle(startup, transport, control_root, specs=SPECS,
                       enforcer=_enforcer(), today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
    assert report.security_events == ["<f1@x>"]
    assert len(transport.outgoing) == 1
    sent = transport.outgoing[0]
    assert sent["to"] == [CEO, CFO]
    assert "accounts@siemens-emergy.com" not in str(sent["to"] + sent["cc"])
    assert "contact.ubcsis@gmail.com" not in sent["cc"]  # D-04 exclusion


def test_macro_attachment_quarantined_not_accepted(env):
    startup, control_root = env
    poisoned = _submission_msg(b"PK\x03\x04macro", filename="FRM-WPR_w33.xlsm")
    transport = MockTransport([poisoned])
    report = run_cycle(startup, transport, control_root, specs=SPECS,
                       enforcer=_enforcer(), today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
    assert len(report.quarantined) == 1
    assert Path(report.quarantined[0]).exists()
    assert report.verdicts["<s1@ubcsis.com>"] == "NOT_ACCEPTED"


def test_dispute_recorded_pending(env):
    startup, control_root = env
    dispute = FetchedMessage(
        message_id="<d1@ubcsis.com>", sender="a.elsayed@ubcsis.com",
        received_at=datetime(2026, 8, 13, 9, 0), first_line="DISPUTE - deadline moved",
    )
    run_cycle(startup, MockTransport([dispute]), control_root, specs=SPECS,
              enforcer=_enforcer(), today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
    import sqlite3
    conn = sqlite3.connect(startup.db_path)
    n = conn.execute("SELECT COUNT(*) FROM disputes WHERE state='PENDING'").fetchone()[0]
    conn.close()
    assert n == 1


def test_enforcement_class1_sends_and_class3_drafts(env):
    startup, control_root = env
    items = [
        TrackedItem("STAT-VAT", 1, "VAT return", "hadeer@ubcsis.com", date(2026, 8, 13)),
        TrackedItem("OPS-WPR-001", 3, "Weekly progress", "a.elsayed@ubcsis.com",
                    date(2026, 8, 10)),  # 3 wd late on Thu 13th -> L1+L2
    ]
    transport = MockTransport()
    report = run_cycle(startup, transport, control_root, specs=SPECS,
                       tracked_items=items,
                       class3_state={"OPS-WPR-001": Class3State()},
                       enforcer=_enforcer(), today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
    # class 1 day-of sends in SUPERVISED, to CEO+CFO
    assert any(o["to"] == [CEO, CFO] for o in transport.outgoing)
    # class 3 escalations draft in SUPERVISED
    assert report.drafted
    # second run same day: everything deduped
    report2 = run_cycle(startup, MockTransport(), control_root, specs=SPECS,
                        tracked_items=items,
                        class3_state={"OPS-WPR-001": Class3State()},
                        enforcer=_enforcer(), today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
    assert report2.sent == [] and report2.drafted == []
    assert report2.skipped_duplicates >= 3


def test_submitted_item_stops_enforcement(env):
    startup, control_root = env
    items = [TrackedItem("OPS-WPR-001", 3, "Weekly progress",
                         "a.elsayed@ubcsis.com", date(2026, 8, 10))]
    report = run_cycle(startup, MockTransport(), control_root, specs=SPECS,
                       tracked_items=items,
                       class3_state={"OPS-WPR-001": Class3State(submitted=True)},
                       enforcer=_enforcer(), today=date(2026, 8, 13), ceo=CEO, cfo=CFO)
    assert report.sent == [] and report.drafted == []
