"""The advisor brief, generated — execution order step 5.

*"Send the **completed** statutory table for correction, not blank
rows. Request the full filing archive in the same message. Lead with
the payroll cycle and the corporate return date."*

This reverses the original brief's method, deliberately. That draft was
written when nothing was known and said so: *"Nothing below is a
proposed answer. Supplying a plausible date for the advisor to correct
would anchor the answer."* Sound when there was nothing to supply.

Since then the CEO has stated twelve rules and the archive has been
counted, so blank rows would now be withholding what we know and asking
a paid professional to rediscover it. The anchoring risk is real and is
handled by naming it: every row says where its value came from, and the
covering note asks the advisor to correct rather than to agree.

**This is generated rather than written**, for the same reason §11
gives: a number that cannot be traced to a row does not appear. The
stated column comes from `statutory-calendar.yaml` and the observed
column from the filing archive, so neither can drift from what the
system actually holds, and neither can be typed in by hand.
"""

from dataclasses import dataclass
from datetime import date

from .extraction import (
    CADENCE_GRANULARITY, STATED_CADENCE_PERIODS, can_speak_to,
)

# Step 5: "Lead with the payroll cycle and the corporate return date."
LEAD_WITH = ("STAT-PAYROLL-REM", "STAT-PAYROLL-RET", "STAT-CIT")


@dataclass(frozen=True)
class Row:
    obligation_id: str
    name: str
    stated: str
    provenance: str
    decision: str
    observed: str


def _observed_line(record, cadence: str) -> str:
    """What the archive shows, in one line, or why it shows nothing."""
    if record is None:
        return "no filing evidence found"
    if not record.periods:
        return (f"{record.documents} document(s), none naming a period")

    kind = record.granularity
    interior = record.interior_years(kind)
    if not interior:
        return (f"{len(record.periods)} {kind} period(s), no year covered "
                "in full")
    if not can_speak_to(kind, cadence):
        return (f"filings named by {kind}; one may contain several returns, "
                "so the count says nothing about cadence")

    spread = ", ".join(f"{year}: {count}"
                       for year, count in sorted(interior.items()))
    expected = STATED_CADENCE_PERIODS.get(cadence)
    line = f"{len(record.periods)} periods named by {kind}; {spread}"
    if expected is not None and interior:
        counts = set(interior.values())
        if counts == {expected}:
            line += f" — consistent with {cadence}"
        elif any(c > expected for c in counts):
            line += (f" — MORE than {cadence} allows; see the disagreement "
                     "section of the extraction brief")
        elif 0 in counts:
            line += " — a year inside the span holds no filing at all"
        else:
            line += f" — FEWER than {cadence} would produce"
    return line


def build_rows(statutory_config: dict | None, observed: dict
               ) -> tuple[list[Row], list[str]]:
    """The rows a tax advisor can answer, and the ones left out.

    Two of the twelve are data-protection matters that happen to be
    class 1 obligations. Asking a tax advisor about the PDPL executive
    regulations wastes their time, and — worse — dilutes the rows that
    matter by making the brief look like a form to be worked through
    rather than four questions that cost money to get wrong.

    They are named as excluded rather than silently dropped, so the
    twelve in the register and the ten in the brief reconcile.
    """
    rows = []
    excluded = []
    for entry in (statutory_config or {}).get("obligations") or []:
        obligation_id = str(entry.get("id") or "")
        if str(entry.get("answered_by") or "advisor").lower() != "advisor":
            excluded.append(
                f"{entry.get('name') or obligation_id} — for "
                f"{entry.get('answered_by')}, not a tax matter")
            continue
        cadence = str(entry.get("cadence") or "").lower()
        rows.append(Row(
            obligation_id=obligation_id,
            name=str(entry.get("name") or obligation_id),
            stated=str(entry.get("rule") or "").strip(),
            provenance=str(entry.get("provenance") or "no provenance recorded"),
            decision=str(entry.get("decision") or ""),
            observed=_observed_line(observed.get(obligation_id), cadence),
        ))
    # Step 5's ordering. The two the CEO wants answered first go first,
    # because a reviewer's attention is highest on the first table they
    # meet and lowest on the twelfth row.
    lead = [r for r in rows if r.obligation_id in LEAD_WITH]
    rest = [r for r in rows if r.obligation_id not in LEAD_WITH]
    return (sorted(lead, key=lambda r: LEAD_WITH.index(r.obligation_id))
            + rest), excluded


def render(rows: list[Row], statutory_config: dict | None,
           today: date, excluded: list[str] | None = None) -> str:
    config = statutory_config or {}
    source = config.get("source", "source not recorded")

    lines = [
        "# Statutory calendar — brief for the tax advisor",
        "",
        f"**Prepared:** {today:%d-%b-%Y} · **Closes:** open decision "
        "**O-03** (charter §2.1)",
        "**Send from:** Ahmed Diab, CEO — this leaves the company from a "
        "person, never from Control (§10)",
        "",
        "---",
        "",
        "## What is being asked",
        "",
        "Please **correct or confirm** each row below. The dates in the "
        "*We state* column are the CEO's, recorded from memory on "
        f"{config.get('ceo_stated_on', 'an unrecorded date')} "
        f"({source}). They are not verified by anyone qualified, and the "
        "system marks them so.",
        "",
        "**An earlier version of this brief sent blank rows**, on the "
        "reasoning that a proposed answer anchors the person correcting "
        "it. That was right when nothing was known. It is now wrong: "
        "withholding what we already hold asks you to rediscover it at "
        "our expense.",
        "",
        "So the anchoring risk is handled by naming it instead. **The "
        "failure mode here is agreeing with a row because it looks "
        "plausible.** Every row states where its value came from, and "
        "none of them came from anyone qualified.",
        "",
        "The *Our archive shows* column is not a second opinion. It is a "
        "count of what the company actually filed, taken from filenames "
        "in the document archive — evidence about practice, not about "
        "law. Where it disagrees with the stated rule, the rule is the "
        "more likely thing to be wrong, but that is your judgement and "
        "not ours.",
        "",
        "**Please also send the full filing archive** for the last three "
        "years — returns and acknowledgements — so the practice column "
        "can be checked against records rather than against filenames.",
        "",
        "---",
        "",
        "## The two we would like answered first",
        "",
    ]

    for row in rows[:len(LEAD_WITH)]:
        lines += [
            f"### {row.name}",
            "",
            f"- **We state:** {row.stated}"
            + (f"  ({row.decision})" if row.decision else ""),
            f"- **Our archive shows:** {row.observed}",
            "- **Your correction:**",
            "",
        ]

    lines += [
        "The payroll cycle is first because getting it wrong is not one "
        "wrong date. If the return and the remittance are monthly rather "
        "than quarterly, the register is short about eight obligations a "
        "year and every one of them is a class 1 filing.",
        "",
        "---",
        "",
        "## The full table",
        "",
        "| # | Obligation | We state | Provenance | Our archive shows | "
        "Your correction |",
        "|---|---|---|---|---|---|",
    ]
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"| {index} | {row.name} | {row.stated} | {row.provenance} | "
            f"{row.observed} | |")

    lines += [
        "",
        "For each row we need: the filing deadline, the payment deadline "
        "where it differs, the period basis, how the deadline moves when "
        "it falls on a weekend or public holiday, and any lead time the "
        "preparer needs before the statutory date.",
        "",
        "That last item matters more than it looks. If a return is due on "
        "the 10th and the data cannot be closed before the 8th, the "
        "operative deadline for the company is the 8th, and that is what "
        "the system should alert on.",
        "",
        "### Not in this table, and why",
        "",
    ] + ([f"- {item}" for item in (excluded or [])]
         or ["- Nothing. Every class 1 obligation on record is above."]) + [
        "",
        "The register holds "
        f"{len((statutory_config or {}).get('obligations') or [])} class 1 "
        f"obligations; {len(rows)} of them are tax matters and are above. "
        "The count is stated so the two numbers reconcile rather than "
        "one of them quietly being the other.",
        "",
        "---",
        "",
        "## Three questions beyond the table",
        "",
        "1. **Anything missing?** This list comes from the charter and "
        "from the CEO, not from a review of this company's actual "
        "registrations. Are there filings owed that are not listed — "
        "industry-specific, or arising from the contracting licences?",
        "",
        "2. **Any deadline changing in the next 12 months?** A rule that "
        "is correct today and changes in March is worse than one known "
        "to be changing.",
        "",
        "3. **What is the penalty for missing each one?** Control reports "
        "the consequence of a miss alongside the deadline in its CEO "
        "escalation, and it should state the real figure rather than a "
        "generic warning.",
        "",
        "---",
        "",
        "## What happens with the answers",
        "",
        "They go into `config/statutory-calendar.yaml` with "
        "`verified_by_advisor: true`, the verification date, and "
        "`next_annual_verification` set to January.",
        "",
        "Until then every one of these rules is marked `ceo_stated`, and "
        "the weekly management report says so in as many words. **The "
        "system will not promote a rule to verified without a named "
        "person having confirmed it** — that is a hard stop, not a "
        "convention.",
        "",
        "**The learning engine may never modify a statutory deadline** "
        "(§14.2 Tier C). These dates change only when you say so, and "
        "the January re-verification is itself tracked as an obligation.",
        "",
        "---",
        "",
        "## Sign-off",
        "",
        "| | Name | Date |",
        "|---|---|---|",
        "| Completed by | | |",
        "| Firm | | |",
        "| Received by | Mohamed Abdelsadiq, Acting CFO | |",
        "| Loaded into the calendar by | | |",
        "",
        "**O-03 closes when every row carries a confirmed deadline and "
        "`verified_by_advisor` is set true.**",
        "",
        "---",
        "",
        "## ──────── العربية ────────",
        "",
        "تحية طيبة وبعد،",
        "",
        "نرجو **تصحيح أو تأكيد** كل بند في الجدول أعلاه. المواعيد الواردة "
        "في عمود *We state* مقررة من الرئيس التنفيذي من واقع خبرته، ولم "
        "يتم التحقق منها من جهة مختصة، والنظام يؤشر عليها بذلك.",
        "",
        "**وأخطر ما قد يحدث هنا هو الموافقة على بند لأنه يبدو معقولاً.** "
        "فكل بند يوضح مصدر قيمته، ولا يوجد بند واحد ورد من جهة مختصة.",
        "",
        "أما عمود *Our archive shows* فهو ليس رأياً ثانياً، بل هو حصر لما "
        "قامت الشركة بتقديمه فعلاً، مستخرجاً من أسماء الملفات في الأرشيف "
        "— أي دليل على الممارسة لا على القانون.",
        "",
        "ونرجو كذلك موافاتنا بأرشيف الإقرارات الكامل عن السنوات الثلاث "
        "الماضية — الإقرارات وإيصالات التقديم — للتحقق من عمود الممارسة "
        "من واقع السجلات لا من أسماء الملفات.",
        "",
        "ونخص بالذكر بندين نرجو البدء بهما: **دورة ضريبة كسب العمل** "
        "و**موعد الإقرار الضريبي السنوي للشركة**.",
        "",
        "وتفضلوا بقبول فائق الاحترام،",
        "",
        "أحمد دياب — الرئيس التنفيذي",
        "شركة الإخوة المتحدة للمقاولات والتوريدات والخدمات الصناعية",
        "",
        "*النص العربي هو النص المعتمد.*",
    ]
    return "\n".join(lines)
