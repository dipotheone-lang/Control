"""Bilingual verdict reply rendering — charter §7.5, language rules §4.

Rules enforced here, not left to prose:
- Subject lines English only (RTL subjects corrupt Outlook threading).
- Both languages in full, English then Arabic; the Arabic is authoritative
  for formal notices and the footer says so.
- Western Arabic numerals (0-9) in BOTH languages — §4 overrides the
  Eastern-numeral example in the §7.5 template because Eastern numerals
  break Excel paste; equivalence of numbers across the two halves is a
  tested property (v4.3, finding V12).
- Dates DD-MMM-YYYY. Technical tokens (form codes, cell refs, file names)
  stay in Latin script inside Arabic text.
- Address the defect, never the person: no praise, no reprimand.

Plain-language mode (§4) for tier-1 site recipients: short sentences,
the defect, the fix, the deadline, numbered, no compliance vocabulary.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from .calendar import WorkingCalendar
from .evaluate import Evaluation, Finding, ObligationSpec

VERDICT_EN = {
    "ACCEPTED": "ACCEPTED",
    "ACCEPTED_WITH_OBSERVATIONS": "ACCEPTED WITH OBSERVATIONS",
    "RETURNED_FOR_REVISION": "RETURNED FOR REVISION",
    "NOT_ACCEPTED": "NOT ACCEPTED",
    "UNREADABLE": "UNREADABLE — MANUAL REVIEW REQUIRED",
    "RECEIVED_ON_TIME": "RECEIVED ON TIME",
    "RECEIVED_LATE": "RECEIVED LATE",
    "NOT_RECEIVED": "NOT RECEIVED",
}

VERDICT_AR = {
    "ACCEPTED": "مقبول",
    "ACCEPTED_WITH_OBSERVATIONS": "مقبول مع ملاحظات",
    "RETURNED_FOR_REVISION": "مُعاد للمراجعة",
    "NOT_ACCEPTED": "غير مقبول",
    "UNREADABLE": "غير مقروء — مطلوب مراجعة يدوية",
    "RECEIVED_ON_TIME": "مستلم في الموعد",
    "RECEIVED_LATE": "مستلم متأخراً",
    "NOT_RECEIVED": "غير مستلم",
}

FOOTER = """════════════════════════
CONTROL | Automated Compliance System | United Brothers Co.
كنترول | نظام الالتزام الآلي | شركة الإخوة المتحدة

This message reviews the document against the approved form and manual. It is not an
assessment of any individual. To contest a finding, reply with DISPUTE on the first line.
هذه الرسالة تراجع المستند مقابل النموذج والدليل المعتمد، وليست تقييماً لأي فرد.
للاعتراض، يُرجى الرد بكلمة "اعتراض" في السطر الأول. النص العربي هو النص المعتمد."""


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%d-%b-%Y %H:%M")


def _fmt_d(dt: datetime) -> str:
    return dt.strftime("%d-%b-%Y")


def _timeliness_en(t: str) -> str:
    if t.startswith("LATE"):
        n = t.split("(")[1].split()[0]
        return f"{n} working days past due"
    return {"ON_TIME": "ON TIME", "EARLY": "EARLY"}.get(t, t)


def _timeliness_ar(t: str) -> str:
    if t.startswith("LATE"):
        n = t.split("(")[1].split()[0]
        return f"متأخر — {n} يوم عمل بعد الموعد"
    return {"ON_TIME": "في الموعد", "EARLY": "مبكر"}.get(t, t)


def _findings_en(findings: list[Finding]) -> str:
    if not findings:
        return "FINDINGS\nNone."
    lines = ["FINDINGS"]
    for i, f in enumerate(findings, 1):
        ref = f"   [{f.reference}]" if f.reference else ""
        lines += [
            f"{i}. [{f.check}] {f.result}.",
            f"   Required: {f.required}{ref}",
            f"   Observed: {f.observed}",
            f"   Action:   {f.action}",
        ]
    return "\n".join(lines)


def _findings_ar(findings: list[Finding]) -> str:
    # Technical content (field names, values, file refs) stays in Latin
    # script inside the Arabic text (§4); labels and structure are Arabic.
    if not findings:
        return "الملاحظات\nلا توجد."
    lines = ["الملاحظات"]
    for i, f in enumerate(findings, 1):
        ref = f"   [{f.reference}]" if f.reference else ""
        lines += [
            f"{i}. [{f.check}] {f.result}.",
            f"   المطلوب: {f.required}{ref}",
            f"   الوارد: {f.observed}",
            f"   الإجراء التصحيحي: {f.action}",
        ]
    return "\n".join(lines)


def _findings_plain(findings: list[Finding]) -> tuple[str, str]:
    """§4 plain mode: the defect, the fix, the deadline — numbered, no
    compliance vocabulary, both languages."""
    if not findings:
        return "All good. Nothing to fix.", "كل شيء سليم. لا يوجد ما يجب تصحيحه."
    en, ar = [], []
    for i, f in enumerate(findings, 1):
        en.append(f"{i}. Problem: {f.observed}\n   Fix: {f.action}")
        ar.append(f"{i}. المشكلة: {f.observed}\n   التصحيح: {f.action}")
    return "\n".join(en), "\n".join(ar)


@dataclass
class PostedInfo:
    register: str
    period: str
    rows: int
    cumulative: str


def correction_due(received_at: datetime, cal: WorkingCalendar) -> datetime:
    """§7.4: correction due in 2 working days, at end of working day."""
    due_date = cal.add_working_days(received_at.date() + timedelta(days=1), 1)
    return datetime(due_date.year, due_date.month, due_date.day, 17, 0)


def render_verdict_reply(
    evaluation: Evaluation,
    spec: ObligationSpec,
    surname: str,
    period: str,
    received_at: datetime,
    posted: PostedInfo | None = None,
    correction_due_at: datetime | None = None,
    plain: bool = False,
) -> dict:
    verdict_en = VERDICT_EN[evaluation.verdict]
    verdict_ar = VERDICT_AR[evaluation.verdict]
    subject = f"[CONTROL] {verdict_en} — {spec.name} — {period} — {surname}"

    header_en = (
        f"Ref: {spec.obligation_id}\n"
        f"Received: {_fmt_dt(received_at)} | Due: {_fmt_dt(spec.due)} | "
        f"Timeliness: {_timeliness_en(evaluation.timeliness)}"
    )
    header_ar = (
        f"المرجع: {spec.obligation_id}\n"
        f"تاريخ الاستلام: {_fmt_dt(received_at)} | تاريخ الاستحقاق: {_fmt_dt(spec.due)} | "
        f"الالتزام بالموعد: {_timeliness_ar(evaluation.timeliness)}"
    )

    if plain:
        findings_en, findings_ar = _findings_plain(evaluation.findings)
    else:
        findings_en, findings_ar = _findings_en(evaluation.findings), _findings_ar(evaluation.findings)

    action_en, action_ar = "", ""
    if evaluation.verdict in ("RETURNED_FOR_REVISION", "NOT_ACCEPTED") and correction_due_at:
        action_en = (
            "REQUIRED ACTION\n"
            f"Corrected submission due {_fmt_d(correction_due_at)} by {correction_due_at:%H:%M}."
        )
        action_ar = (
            "الإجراء المطلوب\n"
            f"موعد إرسال النسخة المصححة {_fmt_d(correction_due_at)} الساعة {correction_due_at:%H:%M}."
        )

    posted_en, posted_ar = "", ""
    if posted and evaluation.verdict in ("ACCEPTED", "ACCEPTED_WITH_OBSERVATIONS"):
        posted_en = (
            "POSTED TO REGISTER\n"
            f"Register: {posted.register} | Period: {posted.period} | "
            f"Rows: {posted.rows} | Cumulative: {posted.cumulative}"
        )
        posted_ar = (
            "تم القيد في السجل\n"
            f"Register: {posted.register} | Period: {posted.period} | "
            f"Rows: {posted.rows} | Cumulative: {posted.cumulative}"
        )

    en_parts = ["════════ ENGLISH ════════", header_en, "", f"VERDICT: {verdict_en}", "",
                findings_en]
    ar_parts = ["──────── العربية ────────", header_ar, "", f"القرار: {verdict_ar}", "",
                findings_ar]
    for part_en, part_ar in ((action_en, action_ar), (posted_en, posted_ar)):
        if part_en:
            en_parts += ["", part_en]
            ar_parts += ["", part_ar]

    body = "\n".join(en_parts) + "\n\n" + "\n".join(ar_parts) + "\n\n" + FOOTER
    return {"subject": subject, "body": body}
