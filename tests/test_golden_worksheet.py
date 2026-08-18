"""The golden set's round trip — §13.1, D-03, findings V2 and V3.

The harness could run cases whose expected verdict was already known,
but nothing produced those verdicts: the CEO's half of the protocol had
no path in or out. These tests are about the properties that make the
round trip a real test rather than a ceremony.

The load-bearing one is D-03. If Control's verdict reaches the sheet in
any form — a column, a default, a hint — the CEO is judging Control's
answer instead of the document, and the gate becomes a test the engine
cannot fail.
"""

import csv
from datetime import date
from pathlib import Path

import pytest
import yaml

from control import golden_worksheet as gw
from control.__main__ import main

CASE = {
    "case_id": "GS-001",
    "spec": {
        "obligation_id": "OB-DAILY-SITE",
        "name": "Daily site report",
        "form_code": "UB-SITE-01",
        "current_revision": "3",
        "due": "2026-07-05T17:00:00",
        "mandatory_fields": ["manpower"],
        "manual_rules": [{
            "clause": "7.2", "requirement": "manpower recorded",
            "check": "field_present", "field": "manpower",
        }],
    },
    "doc": {
        "received_at": "2026-07-05T16:10:00",
        "attachment_name": "site-05-07.xlsx",
        "form_code": "UB-SITE-01", "revision": "3",
        "fields": {"manpower": 14},
    },
}


def write_pending(directory: Path, *ids: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for case_id in ids:
        record = yaml.safe_load(yaml.safe_dump(CASE))
        record["case_id"] = case_id
        (directory / f"{case_id}.yaml").write_text(
            yaml.safe_dump(record, sort_keys=False), encoding="utf-8")


@pytest.fixture
def root(tmp_path):
    golden = tmp_path / "tests" / "golden-set"
    write_pending(golden / "pending", "GS-001", "GS-002")
    return tmp_path, golden


def run(control_root, *extra):
    return main(["golden", "--control-root", str(control_root),
                 "--today", "2026-08-18", *extra])


# ---- D-03: the sheet never carries Control's answer -------------------

def test_the_worksheet_offers_no_verdict_and_no_hint_of_one(root):
    control_root, golden = root
    assert run(control_root, "--issue") == 0
    sheet = golden / "worksheets" / "batch-01.csv"

    text = sheet.read_text(encoding="utf-8-sig")
    for verdict in gw.VALID_VERDICTS:
        assert verdict not in text, f"{verdict} on the sheet anchors the CEO (D-03)"

    with sheet.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["VERDICT"] for r in rows] == ["", ""]
    assert [r["FAILED_CHECKS"] for r in rows] == ["", ""]


def test_the_sheet_carries_the_evidence_needed_to_judge(root):
    control_root, golden = root
    run(control_root, "--issue")
    with (golden / "worksheets" / "batch-01.csv").open(
            encoding="utf-8-sig", newline="") as f:
        row = next(csv.DictReader(f))
    assert row["document"] == "site-05-07.xlsx"
    assert "05-Jul-2026" in row["received"]
    assert "UB-SITE-01 rev 3" == row["governing_form"]


# ---- V3: the clause-mapping subsample ---------------------------------

def test_the_clause_is_withheld_so_the_ceo_names_their_own(root):
    control_root, golden = root
    run(control_root, "--issue")
    with (golden / "worksheets" / "batch-01.csv").open(
            encoding="utf-8-sig", newline="") as f:
        clauses = [r["governing_clause"] for r in csv.DictReader(f)]
    assert all(c == gw.CLAUSE_WITHHELD for c in clauses)


def test_the_subsample_accumulates_across_batches(root):
    """Ten items in total, not ten every week."""
    control_root, golden = root
    run(control_root, "--issue")
    write_pending(golden / "pending", *[f"GS-1{n:02d}" for n in range(12)])
    run(control_root, "--issue")

    ledger = gw.load_ledger(golden / "worksheets" / "batches.yaml")
    assert len(ledger[0].clause_withheld) == 2         # all that was available
    assert len(ledger[1].clause_withheld) == 8         # tops the sample up to 10
    total = sum(len(b.clause_withheld) for b in ledger)
    assert total == gw.CLAUSE_SUBSAMPLE_MIN


def test_a_case_with_no_recorded_clause_is_not_used_for_the_check():
    """Withholding a clause that was never recorded measures nothing."""
    bare = {"case_id": "GS-X", "spec": {"manual_rules": []}, "doc": {}}
    assert gw.choose_clause_subsample([bare], already=set()) == set()


def test_clause_agreement_survives_how_people_write_clause_numbers():
    assert gw.clause_matches("clause 7.2", "7.2")
    assert gw.clause_matches("§7.2", "7.2")
    assert not gw.clause_matches("7.2", "9.4")


def test_the_clause_error_rate_is_reported_as_its_own_number():
    lines = gw.clause_mapping_report([
        {"case_id": "A", "ceo": "7.2", "control": "7.2", "agrees": True},
        {"case_id": "B", "ceo": "4.1", "control": "9.9", "agrees": False},
    ])
    assert "1/2 agreed (50%)" in lines[0]
    assert any("B" in line and "4.1" in line for line in lines[1:])
    assert any("not yet a measurement" in line for line in lines)


# ---- reading the answers back ----------------------------------------

def fill(sheet: Path, **answers) -> None:
    with sheet.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row.update(answers.get(row["case_id"], {}))
    with sheet.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=gw.HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def test_answers_become_permanent_cases(root):
    control_root, golden = root
    run(control_root, "--issue")
    sheet = golden / "worksheets" / "batch-01.csv"
    fill(sheet, **{
        "GS-001": {"VERDICT": "ACCEPTED", "CLAUSE_YOU_USED": "7.2"},
        "GS-002": {"VERDICT": "RETURNED_FOR_REVISION", "FAILED_CHECKS": "C3, C4",
                   "CLAUSE_YOU_USED": "4.1"},
    })
    assert run(control_root, "--apply", str(sheet)) == 0

    stored = yaml.safe_load((golden / "GS-002.yaml").read_text(encoding="utf-8"))
    assert stored["expected"] == {"verdict": "RETURNED_FOR_REVISION",
                                  "failed_checks": ["C3", "C4"]}
    assert not (golden / "pending" / "GS-002.yaml").exists()


def test_an_answered_batch_is_marked_returned(root):
    control_root, golden = root
    run(control_root, "--issue")
    sheet = golden / "worksheets" / "batch-01.csv"
    fill(sheet, **{"GS-001": {"VERDICT": "ACCEPTED"},
                   "GS-002": {"VERDICT": "ACCEPTED"}})
    run(control_root, "--apply", str(sheet))
    assert gw.load_ledger(golden / "worksheets" / "batches.yaml")[0].returned == date(2026, 8, 18)


def test_a_half_filled_sheet_applies_the_half_that_is_finished(root):
    control_root, golden = root
    run(control_root, "--issue")
    sheet = golden / "worksheets" / "batch-01.csv"
    fill(sheet, **{"GS-001": {"VERDICT": "ACCEPTED"}})
    assert run(control_root, "--apply", str(sheet)) == 0

    assert (golden / "GS-001.yaml").exists()
    assert (golden / "pending" / "GS-002.yaml").exists()
    # Not returned: the batch is still out.
    assert gw.load_ledger(golden / "worksheets" / "batches.yaml")[0].outstanding


def test_a_return_with_no_check_named_is_refused(tmp_path):
    sheet = tmp_path / "b.csv"
    _sheet(sheet, [{"case_id": "GS-001", "VERDICT": "NOT_ACCEPTED"}])
    _, problems = gw.read_batch(sheet)
    assert any("needs at least one of C1–C7" in p for p in problems)


def test_an_acceptance_with_failed_checks_is_refused(tmp_path):
    """One of the two is a slip, and Control does not pick which."""
    sheet = tmp_path / "b.csv"
    _sheet(sheet, [{"case_id": "GS-001", "VERDICT": "ACCEPTED",
                    "FAILED_CHECKS": "C4"}])
    _, problems = gw.read_batch(sheet)
    assert any("one of the two is a slip" in p for p in problems)


def test_an_unknown_verdict_is_refused_by_name_and_line(tmp_path):
    sheet = tmp_path / "b.csv"
    _sheet(sheet, [{"case_id": "GS-001", "VERDICT": "LOOKS FINE"}])
    _, problems = gw.read_batch(sheet)
    assert "line 2 (GS-001)" in problems[0]
    assert "'LOOKS FINE'" in problems[0]


def test_an_unknown_check_code_is_refused(tmp_path):
    sheet = tmp_path / "b.csv"
    _sheet(sheet, [{"case_id": "GS-001", "VERDICT": "NOT_ACCEPTED",
                    "FAILED_CHECKS": "C3, C9"}])
    _, problems = gw.read_batch(sheet)
    assert "C9" in problems[0]


def test_nothing_is_applied_when_any_line_is_rejected(root):
    """A permanent expected verdict is not the place to interpret."""
    control_root, golden = root
    run(control_root, "--issue")
    sheet = golden / "worksheets" / "batch-01.csv"
    fill(sheet, **{"GS-001": {"VERDICT": "ACCEPTED"},
                   "GS-002": {"VERDICT": "PROBABLY FINE"}})
    assert run(control_root, "--apply", str(sheet)) == 1
    assert not (golden / "GS-001.yaml").exists()


def test_a_case_already_in_the_set_is_never_overwritten(root):
    control_root, golden = root
    run(control_root, "--issue")
    sheet = golden / "worksheets" / "batch-01.csv"
    fill(sheet, **{"GS-001": {"VERDICT": "ACCEPTED"}})
    run(control_root, "--apply", str(sheet))

    write_pending(golden / "pending", "GS-001")
    fill(sheet, **{"GS-001": {"VERDICT": "NOT_ACCEPTED", "FAILED_CHECKS": "C2"}})
    run(control_root, "--apply", str(sheet))

    stored = yaml.safe_load((golden / "GS-001.yaml").read_text(encoding="utf-8"))
    assert stored["expected"]["verdict"] == "ACCEPTED"


def _sheet(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=gw.HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in gw.HEADERS})


# ---- the stall blocker ------------------------------------------------

def test_a_batch_out_beyond_two_weeks_is_a_deployment_blocker():
    batches = [gw.Batch(number=1, case_ids=["a"], issued=date(2026, 8, 1))]
    assert gw.stalled_batches(batches, date(2026, 8, 18))
    lines = gw.ledger_lines(batches, date(2026, 8, 18))
    assert "DEPLOYMENT BLOCKER" in lines[0]
    assert any("cannot be delegated" in line for line in lines)


def test_a_batch_still_within_two_weeks_is_reported_without_alarm():
    batches = [gw.Batch(number=1, case_ids=["a"], issued=date(2026, 8, 14))]
    assert not gw.stalled_batches(batches, date(2026, 8, 18))
    assert "DEPLOYMENT BLOCKER" not in gw.ledger_lines(
        batches, date(2026, 8, 18))[0]


def test_a_returned_batch_is_silent():
    batches = [gw.Batch(number=1, case_ids=["a"], issued=date(2026, 8, 1),
                        returned=date(2026, 8, 5))]
    assert gw.ledger_lines(batches, date(2026, 8, 18)) == []


# ---- the gate ---------------------------------------------------------

def test_an_empty_set_is_not_a_pass(tmp_path, capsys):
    (tmp_path / "tests" / "golden-set").mkdir(parents=True)
    assert run(tmp_path) == 1
    out = capsys.readouterr().out
    assert "An empty set is not a pass" in out


def test_the_gate_runs_once_the_set_has_answers(root, capsys):
    control_root, golden = root
    run(control_root, "--issue")
    sheet = golden / "worksheets" / "batch-01.csv"
    fill(sheet, **{"GS-001": {"VERDICT": "ACCEPTED", "CLAUSE_YOU_USED": "7.2"},
                   "GS-002": {"VERDICT": "ACCEPTED", "CLAUSE_YOU_USED": "9.9"}})
    run(control_root, "--apply", str(sheet))
    capsys.readouterr()

    assert run(control_root) == 0
    out = capsys.readouterr().out
    assert "false returns (gate: must be 0): 0" in out
    assert "GATE: PASSED" in out
    assert "clause mapping: 1/2 agreed" in out
    # A two-case set is not a certified engine, and says so.
    assert "not yet a test of the whole engine" in out


def test_c6_rules_reach_the_engine(root):
    """Without them the clause-mapping check compares against nothing."""
    from control.goldenset import load_cases

    control_root, golden = root
    run(control_root, "--issue")
    sheet = golden / "worksheets" / "batch-01.csv"
    fill(sheet, **{"GS-001": {"VERDICT": "ACCEPTED"}})
    run(control_root, "--apply", str(sheet))

    case = load_cases(golden)[0]
    assert [r.clause for r in case.spec.manual_rules] == ["7.2"]
