"""The HSE split — execution order B5, decisions D-17 and D-18.

Two documents arrive from the same function and need opposite
treatment. A monthly statistics return is a class 3 operational report
and gets all seven checks. An individual incident report is
special-category health data (D-17) and is never read (D-18), so it
gets the §12.1.3 reduced set — the same treatment a client-confidential
item gets, for a completely different reason.

The tests are about the asymmetry and about the reason surviving into
the output. Treating an aggregate as restricted costs a check; treating
an incident as an aggregate processes health data with no basis for it,
and reading incident content is a §7 stop condition. So every doubt
resolves toward restricted, and a report line must not tell the reader
an injury record is covered by an NDA.
"""

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from control.classify import Classifier, InboundMessage
from control.hse import HSE_INCIDENT, HseScope, cc_exclusion_note

REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@pytest.fixture
def scope():
    return HseScope.from_config(yaml.safe_load(
        (REPO_CONFIG / "hse.yaml").read_text(encoding="utf-8")))


# ---- the split ---------------------------------------------------------

@pytest.mark.parametrize("subject,attachment", [
    ("HSE incident report - week 33", "incident-2026-08.pdf"),
    ("Near miss at the Sukari site", "report.pdf"),
    ("Lost time injury notification", "lti.xlsx"),
    ("تقرير حادث", "x.pdf"),
    ("First aid case", "fa.docx"),
    ("Root cause analysis", "rca.pdf"),
])
def test_an_individual_incident_record_is_never_read(scope, subject, attachment):
    verdict = scope.classify(subject, [attachment])
    assert verdict.restricted
    assert "special-category health data (D-17)" in verdict.reason
    assert "never opened (D-18)" in verdict.reason


@pytest.mark.parametrize("subject,attachment", [
    ("Monthly HSE statistics - July", "hse-monthly-2026-07.xlsx"),
    ("HSE KPI dashboard", "kpi.xlsx"),
    ("Man-hours return", "manhours.xlsx"),
    ("التقرير الشهري - إحصائيات", "stats.xlsx"),
])
def test_aggregate_statistics_get_the_full_check_set(scope, subject, attachment):
    verdict = scope.classify(subject, [attachment])
    assert not verdict.restricted
    assert "D-17 does not reach counts" in verdict.reason


def test_an_incident_marker_overrides_an_aggregate_one(scope):
    """The asymmetry, stated as a test. A monthly return that also names
    an incident is treated as an incident record."""
    verdict = scope.classify("Monthly HSE statistics and injury log",
                             ["hse-monthly.xlsx"])
    assert verdict.restricted


def test_an_unmatched_hse_item_is_restricted_not_evaluated(scope):
    """§12.1.1's asymmetry, applied to health data: a misclassification
    toward restricted costs a check, the other way costs a lawful
    basis."""
    verdict = scope.classify("HSE update", ["notes.pdf"])
    assert verdict.restricted
    assert "matching neither" in verdict.reason
    assert "processes health data with no basis" in verdict.reason


def test_missing_config_restricts_everything_and_says_it_is_not_a_control(scope):
    """No config is not permission. But nor is a restrictive default a
    working split, and the report must not imply it is."""
    verdict = HseScope.from_config(None).classify("Monthly HSE statistics", [])
    assert verdict.restricted
    assert "hse.yaml is missing" in verdict.reason
    assert "not a working control" in verdict.reason


def test_matching_is_on_metadata_only(scope):
    """Deciding whether a document may be read by reading it is not a
    control. Only the subject and the filenames are consulted."""
    import inspect

    source = inspect.getsource(HseScope.classify)
    assert "subject" in source and "attachments" in source
    for forbidden in ("open(", "read(", "extract", "ocr"):
        assert forbidden not in source


# ---- the reason survives into the treatment ---------------------------

def test_an_incident_record_takes_the_reduced_set_under_its_own_decision():
    """The same reduced set as a confidential item, named differently.
    §12.1.4's stated limitation is about client confidentiality and
    would be simply untrue of an injury record."""
    from datetime import datetime as dt

    from control.calendar import WorkingCalendar
    from control.evaluate import ObligationSpec, SubmissionDoc, evaluate

    spec = ObligationSpec(obligation_id="HSE-INC-001", name="Incident report",
                          form_code="FRM-INC-01", current_revision="2",
                          due=dt(2026, 8, 20, 17, 0))
    doc = SubmissionDoc(received_at=dt(2026, 8, 20, 9, 0),
                        attachment_name="FRM-INC-01 incident.pdf",
                        restricted_basis=HSE_INCIDENT)
    result = evaluate(spec, doc, WorkingCalendar())
    assert result.verdict == "RECEIVED_ON_TIME"
    assert result.check_results["C3"] == "NOT ASSESSED — SPECIAL CATEGORY (D-17, D-18)"
    assert "CONFIDENTIAL" not in result.check_results["C3"]


def test_a_client_confidential_item_keeps_its_own_wording():
    from datetime import datetime as dt

    from control.calendar import WorkingCalendar
    from control.evaluate import ObligationSpec, SubmissionDoc, evaluate

    spec = ObligationSpec(obligation_id="X", name="X", form_code="FRM-X",
                          current_revision="1", due=dt(2026, 8, 20, 17, 0))
    doc = SubmissionDoc(received_at=dt(2026, 8, 20, 9, 0),
                        attachment_name="FRM-X.xlsx", confidential=True)
    result = evaluate(spec, doc, WorkingCalendar())
    assert result.check_results["C3"] == "NOT ASSESSED — CONFIDENTIAL SCOPE"


def test_the_flag_and_the_basis_cannot_disagree():
    """A bool and a string that can contradict each other is a defect
    waiting to be found in production, so neither is set alone."""
    from datetime import datetime as dt

    from control.evaluate import SubmissionDoc

    basis_only = SubmissionDoc(received_at=dt(2026, 8, 20, 9, 0),
                               restricted_basis=HSE_INCIDENT)
    assert basis_only.confidential is True

    flag_only = SubmissionDoc(received_at=dt(2026, 8, 20, 9, 0),
                              confidential=True)
    assert flag_only.restricted_basis == "CONFIDENTIAL_CLIENT"

    neither = SubmissionDoc(received_at=dt(2026, 8, 20, 9, 0))
    assert neither.confidential is False and neither.restricted_basis == ""


def test_the_body_is_never_opened_for_a_restricted_item():
    """§12.1.2 and D-18. The content argument is present and ignored."""
    from control.attachments import build_submission_doc

    doc = build_submission_doc(
        "incident.xlsx", b"PK\x03\x04 not really a workbook",
        datetime(2026, 8, 20, 9, 0),
        mapping={"B12": "Sheet1!B12"},
        restricted_basis=HSE_INCIDENT)
    assert doc.fields == {}
    assert doc.unreadable is False       # not "tried and failed" — never tried
    assert doc.restricted_basis == HSE_INCIDENT


# ---- the classifier applies it only to HSE traffic --------------------

def _classifier(scope):
    return Classifier(
        roster_emails={"hse@ubcsis.com", "info@ubcsis.com"},
        hse_scope=scope, hse_senders={"hse@ubcsis.com"})


def test_an_incident_from_hse_is_marked_restricted(scope):
    result = _classifier(scope).classify(InboundMessage(
        sender="Mostafa <hse@ubcsis.com>",
        subject="Incident report - lost time", first_line="",
        attachments=["FRM-INC-01.pdf"]))
    assert result.confidential is True
    assert result.restricted_basis == HSE_INCIDENT
    assert any("special-category health data" in f for f in result.flags)


def test_an_aggregate_from_hse_is_not_restricted(scope):
    result = _classifier(scope).classify(InboundMessage(
        sender="Mostafa <hse@ubcsis.com>",
        subject="Monthly HSE statistics", first_line="",
        attachments=["hse-monthly.xlsx"]))
    assert result.confidential is False
    assert result.restricted_basis == ""
    assert any("does not reach counts" in f for f in result.flags)


def test_the_word_incident_elsewhere_is_not_a_health_record(scope):
    """An incident in a procurement thread is not special-category data,
    and restricting it would return correct work unassessed for a reason
    that does not apply."""
    result = _classifier(scope).classify(InboundMessage(
        sender="Ahmed <info@ubcsis.com>",
        subject="Incident with the supplier delivery",
        first_line="", attachments=["note.xlsx"]))
    assert result.confidential is False
    assert result.restricted_basis == ""


# ---- the continuity CC ------------------------------------------------

def test_an_incident_notice_never_reaches_the_consumer_mailbox():
    from control.outbox import CC_EXCLUDED_CLASSES

    assert HSE_INCIDENT in CC_EXCLUDED_CLASSES


def test_the_unconfirmed_tightening_is_disclosed(scope):
    """D-04's list predates D-17. Control applies the exclusion because
    §14.1 permits tightening without approval — and says that it did,
    because a control applied quietly is indistinguishable from one
    nobody decided on."""
    note = cc_exclusion_note(scope)[0]
    assert "D-04's exclusion list was written before D-17" in note
    assert "tightening applied and disclosed, not a decision taken" in note
    assert "asked to confirm" in note


def test_no_note_when_there_is_nothing_to_disclose():
    assert cc_exclusion_note(HseScope.from_config(None)) == []


# ---- the config carries its own reason --------------------------------

def test_the_config_records_why_it_may_not_be_relaxed():
    """The execution order §3.2 asks for exactly this: "Record the
    reason in config so it is not relaxed casually." A marker list with
    no reasoning attached is a list somebody edits on a Tuesday."""
    text = (REPO_CONFIG / "hse.yaml").read_text(encoding="utf-8")
    assert "requires a CEO decision, not a configuration change" in text
    assert "stop condition" in text
    data = yaml.safe_load(text)
    assert data["incident_reports"] == "metadata_only"
    assert data["aggregate_reports"] == "evaluated"
    assert data["decision"] == "D-17, D-18"


def test_the_disclosure_and_the_limitation_reach_the_weekly_report(tmp_path,
                                                                  capsys):
    """Dead code is the pattern this project keeps finding: a control
    that exists, is tested, and is never called. Both the tightening
    disclosure and the scope boundary have to be on the page."""
    import shutil

    from control.__main__ import main

    control_root = tmp_path / "UB" / "CONTROL"
    for name in ("data", "logs", "outbox/pending-approval", "outbox/sent",
                 "reports/management"):
        (control_root / name).mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_CONFIG, control_root / "config")

    main(["report", "--control-root", str(control_root), "--ub-root",
          str(control_root.parent), "--run-mode", "DRY_RUN",
          "--learning-mode", "OBSERVE", "--as-of", "2026-08-20"])
    out = capsys.readouterr().out
    assert "tightening applied and disclosed, not a decision taken" in out
    assert "special-category health data (D-17)" in out
    assert "never read (D-18)" in out
    assert "بيانات صحية ذات طبيعة خاصة" in out


def test_a_missing_hse_config_says_the_statistics_are_unchecked_too(tmp_path,
                                                                    capsys):
    """The fail-safe default is safe, not free. Restricting everything
    also stops the monthly return being checked, and a report that only
    said "restricted" would read as a control working."""
    import shutil

    from control.__main__ import main

    control_root = tmp_path / "UB" / "CONTROL"
    for name in ("data", "logs", "outbox/pending-approval", "outbox/sent",
                 "reports/management"):
        (control_root / name).mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_CONFIG, control_root / "config")
    (control_root / "config" / "hse.yaml").unlink()

    main(["report", "--control-root", str(control_root), "--ub-root",
          str(control_root.parent), "--run-mode", "DRY_RUN",
          "--learning-mode", "OBSERVE", "--as-of", "2026-08-20"])
    out = capsys.readouterr().out
    assert "hse.yaml is missing" in out
    assert "monthly statistics return is not being checked either" in out
