"""The statutory horizon, as a page somebody reads — D-15, §2.1, §4.

Scope B was decided with two things outstanding: the tax advisor has not
confirmed the twelve rules (O-03), and Graph is not provisioned (D-08).
The CEO's instruction was to proceed without waiting for either.

Neither actually blocks the work, and saying why matters more than the
command does.

**Graph is only needed to send.** An alert nobody can read is useless
whether it was emailed or drafted, and an alert on a page is useful
whether or not it was. The cycle already writes drafts to
`outbox/pending-approval` as JSON, which is a record and not something a
person reads on a Tuesday morning. This is the same information as a
page.

**Unverified dates still alert.** §2.1 is explicit: unverified rules are
marked `UNVERIFIED — CONFIRM WITH ADVISOR` and still alert, erring
early. What is forbidden is presenting them as verified, so every row
carries its provenance and the header says it once in words nobody has
to interpret.

Bilingual, English then Arabic, in full (§4). Western Arabic numerals in
both, dates `DD-MMM-YYYY`, and the Arabic is authoritative for anything
formal — this is a working page rather than a notice, but the same
typography rules apply because a page that changes format when it
becomes formal teaches people to read two things.
"""

from dataclasses import dataclass, field
from datetime import date

# Alert points for class 1, from §2.1: T-7, T-3, T-1, and the day
# itself, when it goes to the CEO and CFO immediately.
_ALERT_POINTS = (7, 3, 1, 0)

_MONTHS_AR = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
    7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر",
    12: "ديسمبر",
}


@dataclass
class Row:
    item_id: str
    name: str
    owner: str
    due: date
    days: int
    verified: bool
    alerting: bool


@dataclass
class Digest:
    rows: list = field(default_factory=list)       # inside the horizon
    notes: list = field(default_factory=list)      # gap messages from the loader
    tracked_count: int = 0                         # dated, any horizon
    silent_count: int = 0                          # firing no countdown at all
    verified_count: int = 0
    total_rules: int = 0


def build(statutory_config: dict | None, today: date, horizon_days: int = 30
          ) -> Digest:
    """The class 1 horizon, from the engine's own builder.

    `build_statutory` decides what has a usable date and what does not,
    and this reads its answer rather than forming a second one. A digest
    that disagreed with the engine about what is tracked would be worse
    than no digest — the same trap the status page fell into once.
    """
    from .loader import build_statutory

    tracked, gaps = build_statutory(statutory_config, today)
    rows = (statutory_config or {}).get("obligations") or []
    verified = {str(r.get("id")) for r in rows if r.get("verified_by_advisor")}

    # Count the rules, not the messages. The loader emits per-row lines
    # plus an aggregate line plus a provenance line, so `len(gaps)` is a
    # count of sentences — and a heading reading "NOT COUNTING DOWN — 2"
    # over one undated rule would be a number that means something other
    # than what it says, which is the failure this whole page exists to
    # prevent (§1.1).
    digest = Digest(notes=gaps, total_rules=len(rows),
                    tracked_count=len(tracked),
                    silent_count=len(rows) - len(tracked),
                    verified_count=len(verified))
    for item in tracked:
        days = (item.due - today).days
        if days > horizon_days:
            continue
        digest.rows.append(Row(
            item_id=item.item_id, name=item.name, owner=item.owner,
            due=item.due, days=days,
            verified=item.item_id in verified,
            # §2.1's schedule. Reported so the page says which rows are
            # live today rather than leaving the reader to subtract.
            alerting=days <= max(_ALERT_POINTS),
        ))
    digest.rows.sort(key=lambda r: r.due)
    return digest


def _arabic_date(value: date) -> str:
    return f"{value.day} {_MONTHS_AR[value.month]} {value.year}"


def render(digest: Digest, today: date, horizon_days: int = 30) -> str:
    lines = [
        f"STATUTORY HORIZON — {today:%d-%b-%Y}",
        f"Next {horizon_days} days. Class 1 only (D-15).",
        "",
    ]

    if digest.verified_count == 0:
        lines += [
            "!! NO RULE HERE HAS BEEN CONFIRMED BY A TAX ADVISOR (O-03).",
            "   Every date below is CEO-stated. They alert early, which is the",
            "   chartered behaviour (§2.1) — but nobody qualified has checked",
            "   them, and time passing does not check them. Treat a date as a",
            "   prompt to verify, not as the deadline itself.",
            "",
        ]

    if not digest.rows:
        lines += ["Nothing due in this window.", ""]
        if digest.silent_count:
            lines += [
                "That is an empty window, not a clear one: "
                f"{digest.silent_count} of {digest.total_rules} rule(s) fire "
                "no countdown at all.",
                "",
            ]
        if digest.tracked_count:
            lines += [
                f"{digest.tracked_count} rule(s) are counting down, all of "
                "them beyond this window.",
                "",
            ]
    else:
        lines += ["  DUE      DATE          OBLIGATION", ""]
        for row in digest.rows:
            when = "TODAY" if row.days == 0 else f"T-{row.days}"
            mark = "*" if row.alerting else " "
            flag = "" if row.verified else "   [UNVERIFIED]"
            lines.append(f" {mark}{when:>6}   {row.due:%d-%b-%Y}   "
                         f"{row.name}{flag}")
            lines.append(f"          owner {row.owner}")
        lines += [
            "",
            "  * = inside the §2.1 alert schedule (T-7, T-3, T-1, and the day",
            "      itself, when it goes to the CEO and CFO immediately).",
            "",
        ]

    if digest.silent_count:
        lines += [
            f"WHAT IS NOT COUNTING DOWN — {digest.silent_count} "
            f"of {digest.total_rules}",
            "",
            "Class 1 is the only class carrying fines, so these are the",
            "highest-priority gap in the system, not a footnote (§1.1):",
            "",
        ]
    elif digest.notes:
        lines += ["NOTES ON THIS REGISTER", ""]
    for note in digest.notes:
        lines.append(f"  - {note}")
    if digest.notes:
        lines.append("")

    lines += [
        "────────────────────────────────────────",
        f"الالتزامات القانونية — {_arabic_date(today)}",
        f"خلال {horizon_days} يوماً القادمة. الفئة 1 فقط (القرار D-15).",
        "",
    ]
    if digest.verified_count == 0:
        lines += [
            "تنبيه: لم يتم اعتماد أي من هذه المواعيد من المستشار الضريبي "
            "(البند O-03).",
            "جميع التواريخ أدناه مذكورة من الرئيس التنفيذي، ويتم التنبيه بها "
            "مبكراً وفقاً للبند 2.1،",
            "ولكن لم يراجعها مختص. يُرجى التعامل معها كتنبيه للمراجعة وليس "
            "كموعد نهائي مؤكد.",
            "",
        ]
    if not digest.rows:
        lines.append("لا توجد التزامات مستحقة خلال هذه الفترة.")
    else:
        for row in digest.rows:
            when = "اليوم" if row.days == 0 else f"خلال {row.days} يوم"
            flag = "" if row.verified else "  [غير مؤكد]"
            lines.append(f"  {_arabic_date(row.due)}  ({when})  "
                         f"{row.name}{flag}")
            lines.append(f"      المسؤول: {row.owner}")
    if digest.silent_count:
        # §4 requires the same content in both halves. The loader's gap
        # sentences are English prose, but the number they are about must
        # not be English-only — a reader of the Arabic half would
        # otherwise see an empty horizon and no reason to doubt it.
        lines += [
            "",
            f"لا يوجد عد تنازلي لعدد {digest.silent_count} من أصل "
            f"{digest.total_rules} من الالتزامات القانونية المسجلة، "
            "وهي أعلى الفجوات أولوية في النظام (البند O-03).",
        ]
    lines += [
        "",
        "════════════════════════════════════════",
        "CONTROL | Automated Compliance System | United Brothers Co.",
        "كنترول | نظام الالتزام الآلي | شركة الإخوة المتحدة",
        "",
        "This page is produced from the statutory calendar. It sends nothing",
        "and reads no mailbox (D-15). النص العربي هو النص المعتمد.",
    ]
    return "\n".join(lines)
