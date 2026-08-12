import re
from datetime import datetime

from control.calendar import WorkingCalendar
from control.evaluate import ObligationSpec, SubmissionDoc, TotalRule, evaluate
from control.render import PostedInfo, correction_due, render_verdict_reply

CAL = WorkingCalendar()
DUE = datetime(2026, 8, 13, 12, 0)

SPEC = ObligationSpec(
    obligation_id="OPS-WPR-001",
    name="Weekly progress report",
    form_code="FRM-WPR",
    current_revision="3",
    due=DUE,
    mandatory_fields=["B2"],
    totals=[TotalRule("B10", ["B4", "B5"])],
)


def _returned_eval():
    doc = SubmissionDoc(
        received_at=datetime(2026, 8, 16, 9, 0),
        attachment_name="FRM-WPR.xlsx",
        form_code="FRM-WPR",
        revision="3",
        fields={"B2": 1.0, "B4": 1.0, "B5": 2.0, "B10": 4.0},
    )
    return doc, evaluate(SPEC, doc, CAL)


def test_subject_is_english_only():
    doc, ev = _returned_eval()
    reply = render_verdict_reply(ev, SPEC, "Elsayed", "2026-W32", doc.received_at)
    assert reply["subject"] == (
        "[CONTROL] RETURNED FOR REVISION — Weekly progress report — 2026-W32 — Elsayed"
    )
    assert not re.search(r"[؀-ۿ]", reply["subject"])


def test_both_languages_full_and_arabic_authoritative():
    doc, ev = _returned_eval()
    body = render_verdict_reply(ev, SPEC, "Elsayed", "2026-W32", doc.received_at)["body"]
    assert "════════ ENGLISH ════════" in body
    assert "──────── العربية ────────" in body
    assert "القرار: مُعاد للمراجعة" in body
    assert "النص العربي هو النص المعتمد" in body
    assert "DISPUTE" in body and "اعتراض" in body


def test_western_numerals_everywhere_and_number_equivalence():
    doc, ev = _returned_eval()
    body = render_verdict_reply(ev, SPEC, "Elsayed", "2026-W32", doc.received_at)["body"]
    # §4: no Eastern Arabic numerals anywhere
    assert not re.search(r"[٠-٩]", body)
    # V12 structural equivalence: same multiset of numbers in both halves
    en_half, ar_half = body.split("──────── العربية ────────")
    nums = lambda s: sorted(re.findall(r"\d+(?:\.\d+)?", s))
    ar_half_wo_footer = ar_half.split("════════════════════════")[0]
    en_wo_marker = en_half.split("════════ ENGLISH ════════")[1]
    assert nums(en_wo_marker) == nums(ar_half_wo_footer)


def test_dates_dd_mmm_yyyy_and_timeliness_terms():
    doc, ev = _returned_eval()
    body = render_verdict_reply(ev, SPEC, "Elsayed", "2026-W32", doc.received_at)["body"]
    assert "Received: 16-Aug-2026 09:00" in body
    assert "1 working days past due" in body
    assert "متأخر — 1 يوم عمل بعد الموعد" in body


def test_required_action_block_on_return():
    doc, ev = _returned_eval()
    due = correction_due(doc.received_at, CAL)
    body = render_verdict_reply(
        ev, SPEC, "Elsayed", "2026-W32", doc.received_at, correction_due_at=due
    )["body"]
    assert "REQUIRED ACTION" in body and "الإجراء المطلوب" in body
    assert "18-Aug-2026" in body  # received Sunday -> 2 working days -> Tuesday


def test_posted_block_only_when_accepted():
    doc = SubmissionDoc(
        received_at=datetime(2026, 8, 13, 9, 0),
        attachment_name="FRM-WPR.xlsx", form_code="FRM-WPR", revision="3",
        fields={"B2": 1.0, "B4": 1.0, "B5": 2.0, "B10": 3.0},
    )
    ev = evaluate(SPEC, doc, CAL)
    assert ev.verdict == "ACCEPTED"
    posted = PostedInfo("registers_progress", "2026-W32", 12, "32 weeks on record")
    body = render_verdict_reply(ev, SPEC, "Elsayed", "2026-W32", doc.received_at, posted=posted)["body"]
    assert "POSTED TO REGISTER" in body and "تم القيد في السجل" in body

    _, returned = _returned_eval()
    body2 = render_verdict_reply(returned, SPEC, "Elsayed", "2026-W32",
                                 datetime(2026, 8, 16, 9, 0), posted=posted)["body"]
    assert "POSTED TO REGISTER" not in body2


def test_plain_mode_drops_compliance_vocabulary():
    doc, ev = _returned_eval()
    body = render_verdict_reply(ev, SPEC, "Elsayed", "2026-W32", doc.received_at, plain=True)["body"]
    assert "Problem:" in body and "Fix:" in body
    assert "المشكلة:" in body and "التصحيح:" in body
    assert "Required:" not in body


def test_correction_due_is_two_working_days():
    # Received Sunday 16-Aug -> next working day Mon 17 counts as day 1?
    # Charter: correction due in 2 working days. Received Sun -> due Tue 17:00.
    due = correction_due(datetime(2026, 8, 16, 9, 0), CAL)
    assert due == datetime(2026, 8, 18, 17, 0)
