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
    if digest.silent_count:
        # A gap with no next step is a complaint. This one has a next
        # step, and it is a page rather than a project.
        lines += [
            "  What each of those is waiting on, and who holds the answer:",
            "      python -m control statutory --missing",
            "",
        ]

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


# ---- the missing dates -------------------------------------------------
#
# 8 of the 12 class 1 rules fire no countdown, and 4 of those are waiting
# on a date somebody in the company already holds — renewal dates off the
# certificates, the payroll quarterly cycle. That is the largest gap left
# inside the only class this scope operates on, and it is a page, not a
# scan.
#
# Nothing here is inferred. Every field printed is a field in
# `statutory-calendar.yaml`: the question is `open_question` verbatim,
# the holder is whatever the `rule` line says, and `answered_by` decides
# who is being asked. Control does not parse a name out of prose and it
# does not guess a date — §14.2 puts statutory deadlines in Tier C,
# never applied by the system, and this asks rather than proposes.


def missing_dates(statutory_config: dict | None, today: date) -> tuple:
    """(answerable, unanswerable) — rules with no usable date.

    Split on whether the register records a question against the rule.
    A rule with an `open_question` is waiting on an answer somebody can
    give; one without is waiting on something else, and saying which is
    which is the difference between a page that gets acted on and a list
    that gets skimmed.
    """
    from .loader import parse_due

    answerable, unanswerable = [], []
    for row in (statutory_config or {}).get("obligations") or []:
        due, _ = parse_due(str(row.get("rule") or ""),
                           str(row.get("cadence") or ""), today)
        if due is not None:
            continue
        (answerable if row.get("open_question") else unanswerable).append(row)
    return answerable, unanswerable


def render_missing(statutory_config: dict | None, today: date) -> str:
    answerable, unanswerable = missing_dates(statutory_config, today)
    total = len((statutory_config or {}).get("obligations") or [])
    silent = len(answerable) + len(unanswerable)

    lines = [
        f"CLASS 1 — THE DATES THAT ARE MISSING — {today:%d-%b-%Y}",
        "",
        f"{silent} of {total} statutory obligations fire no countdown. Class 1",
        "is the only class carrying fines, so this is the highest-priority",
        "gap in the system (§1.1, O-03).",
        "",
        f"{len(answerable)} of them are waiting on an answer somebody already",
        "holds. Each is one line in config/statutory-calendar.yaml.",
        "",
    ]

    for row in answerable:
        obligation_id = str(row.get("id") or "")
        lines += [
            f"  {obligation_id} — {row.get('name') or obligation_id}",
            f"      question:  {row.get('open_question')}",
            f"      register:  rule: {row.get('rule')}",
        ]
        if row.get("answered_by"):
            # `answered_by` routes the obligation's *subject* away from
            # the tax advisor (advisor.py). Printing it as "answered by"
            # under a missing *date* said the wrong thing: on
            # STAT-PDPL-REGS the subject is counsel's and the date is an
            # internal scheduling choice, and the page read as though
            # counsel had to be asked for a calendar entry.
            lines.append(f"      routing:   subject sits with "
                         f"{row['answered_by']}, not the tax advisor")
        lines += [
            f"      owner:     {row.get('owner') or 'NOT PROVIDED'}"
            f"   preparer: {row.get('preparer') or 'NOT PROVIDED'}",
            f"      to close:  replace the `rule:` line for {obligation_id} "
            "with the date or",
            "                 cadence, and re-run. Nothing else changes.",
            "",
        ]

    if unanswerable:
        lines += [
            f"{len(unanswerable)} are silent for a different reason, and no "
            "question is",
            "recorded against them. They are listed so nobody reads their "
            "silence",
            "as somebody handling them:",
            "",
        ]
        for row in unanswerable:
            lines.append(f"  {row.get('id')} — {row.get('name')}")
            lines.append(f"      register:  rule: {row.get('rule')}")
            # The mechanism separates three situations this list would
            # otherwise blur: an obligation with no deadline by design,
            # one counted from an event that has not happened, and one
            # simply waiting on a date nobody has set.
            lines.append(f"      mechanism: {row.get('mechanism') or 'NOT RECORDED'}"
                         + ("   (mechanism_available: unknown)"
                            if row.get("mechanism_available") == "unknown"
                            else ""))
            if row.get("note"):
                lines.append(f"      note:      {' '.join(str(row['note']).split())}")
            lines.append("")
        lines += [
            "  A rule with no usable date and no `open_question` is chased by",
            "  nothing. Where that is by design the mechanism above says so.",
            "  Where the rule still reads as pending, the missing question is",
            "  itself the gap — and adding one is a register edit, not a",
            "  statutory decision.",
            "",
        ]

    lines += [
        "Every line above is quoted from config/statutory-calendar.yaml.",
        "Control does not infer a holder from prose and does not propose a",
        "date: §14.2 puts statutory deadlines in Tier C, never applied by",
        "the system. This asks.",
        "",
        "────────────────────────────────────────",
        f"الفئة 1 — التواريخ الناقصة — {_arabic_date(today)}",
        "",
        f"عدد {silent} من أصل {total} من الالتزامات القانونية لا يوجد لها عد "
        "تنازلي.",
        "الفئة 1 هي الفئة الوحيدة التي تترتب عليها غرامات، وهذه أعلى الفجوات "
        "أولوية في النظام.",
        "",
        f"منها عدد {len(answerable)} في انتظار إجابة متوفرة لدى أحد العاملين "
        "بالشركة:",
        "",
    ]
    for row in answerable:
        # The question text is quoted, not translated. It is a value in
        # the register, and §4 keeps register values in Latin script
        # inside Arabic text for exactly this reason — a translated
        # question and the field it refers to would stop matching.
        lines += [
            f"  {row.get('id')} — {row.get('name')}",
            f"      المطلوب: {row.get('open_question')}",
            f"      المسؤول: {row.get('owner') or 'غير محدد'}",
            "",
        ]
    if unanswerable:
        lines += [
            f"وعدد {len(unanswerable)} صامتة لأسباب أخرى ولم يُسجَّل بشأنها "
            "سؤال محدد، وهي مدرجة",
            "أعلاه حتى لا يُفهم صمتها على أنه متابعة جارية.",
            "",
        ]
    lines += [
        "════════════════════════════════════════",
        "CONTROL | Automated Compliance System | United Brothers Co.",
        "كنترول | نظام الالتزام الآلي | شركة الإخوة المتحدة",
        "",
        "This page is produced from the statutory calendar. It sends nothing",
        "and reads no mailbox (D-15). النص العربي هو النص المعتمد.",
    ]
    return "\n".join(lines)


# ---- the ask -----------------------------------------------------------
#
# The missing-dates page is an audit page: it tells the CEO what is
# silent and why. It is the wrong thing to forward to the person holding
# the answer — §-references, engine vocabulary, English only.
#
# This is the other half. One page per holder, in both languages (§4),
# plain and short (§4 plain-language mode: the defect, the fix, the
# deadline, numbered, no compliance vocabulary), naming only what that
# person can answer.
#
# Routing is by the `answer_held_by` field, never by reading a name out
# of the `rule` prose. A rule with no holder recorded is listed under
# nobody rather than guessed at — the whole point of the field is that a
# name in a sentence is not a routable address.


def _by_holder(statutory_config: dict | None, today: date) -> tuple:
    """(holder -> rows, rows with no holder recorded)."""
    answerable, _ = missing_dates(statutory_config, today)
    held: dict = {}
    unrouted = []
    for row in answerable:
        holder = str(row.get("answer_held_by") or "").strip().lower()
        if not holder:
            unrouted.append(row)
            continue
        held.setdefault(holder, []).append(row)
    return held, unrouted


@dataclass
class AskMessage:
    """One register-gap request, addressed and ready to send (D-62)."""
    holder: str                 # the answer_held_by address
    holder_name: str
    subject: str
    body: str
    rule_ids: list
    cc: list                    # the obligations' owners, deduplicated


def _names(people: dict | None) -> dict:
    names = {}
    for entry in (people or {}).get("people") or []:
        email = str(entry.get("email") or "").strip().lower()
        if email:
            names[email] = str(entry.get("name") or email)
    return names


def _ask_body(who: str, rows: list) -> str:
    """The bilingual request text for one holder. Used verbatim by both
    the reports/ page and the sent email — one source, so the page is
    always an exact record of what went out (§13.1)."""
    lines = [
        f"{who},",
        "",
        "Control tracks the company's statutory deadlines and alerts",
        "before each one falls due. The items below have no date on",
        "file, so nothing is counting down to them and no alert can",
        "fire.",
        "",
    ]
    for index, row in enumerate(rows, 1):
        lines += [
            f"{index}. {row.get('name')}",
            f"   Needed: {row.get('open_question')}",
            f"   On file now: {row.get('rule')}",
            "",
        ]
    lines += [
        "Please reply with the date or the recurring pattern for each.",
        "A reply like \"1 January, then every three months\" is enough —",
        "it does not need to be exact wording.",
        "",
        "This is a gap in the records, not a question about your work.",
        "",
        "────────────────────────────────────────",
        f"إلى: {who}",
        "",
        f"الأستاذ/ة {who}،",
        "",
        "يقوم نظام كنترول بمتابعة المواعيد القانونية للشركة والتنبيه قبل",
        "حلول كل موعد. البنود التالية لا يوجد لها تاريخ مسجل، وبالتالي لا",
        "يتم العد التنازلي لها ولا يمكن إصدار أي تنبيه بشأنها.",
        "",
    ]
    for index, row in enumerate(rows, 1):
        lines += [
            f"{index}. {row.get('name')}",
            f"   المطلوب: {row.get('open_question')}",
            f"   المسجل حالياً: {row.get('rule')}",
            "",
        ]
    lines += [
        "برجاء الرد بالتاريخ أو بنمط التكرار لكل بند. رد مثل \"1 يناير ثم",
        "كل ثلاثة أشهر\" يكفي، ولا يلزم صياغة محددة.",
        "",
        "هذه فجوة في السجلات وليست استفساراً عن أداء العمل.",
        "",
        "النص العربي هو النص المعتمد.",
    ]
    return "\n".join(lines)


def ask_messages(statutory_config: dict | None, today: date,
                 people: dict | None = None) -> tuple:
    """(messages, unrouted_rows) — the D-62 register-gap requests.

    One message per holder. A row with no `answer_held_by` produces no
    message: a name in prose is not a routable address, and guessing
    one would put a request in the wrong inbox with the system's name
    on it (§1.1).
    """
    names = _names(people)
    held, unrouted = _by_holder(statutory_config, today)
    messages = []
    for holder, rows in sorted(held.items()):
        who = names.get(holder, holder)
        owners: list = []
        for row in rows:
            owner = str(row.get("owner") or "").strip().lower()
            if owner and owner != holder and owner not in owners:
                owners.append(owner)
        messages.append(AskMessage(
            holder=holder,
            holder_name=who,
            subject=("[CONTROL] Statutory dates needed — "
                     f"{len(rows)} item{'' if len(rows) == 1 else 's'}"),
            body=_ask_body(who, rows),
            rule_ids=[str(row.get("id") or "") for row in rows],
            cc=owners,
        ))
    return messages, unrouted


def render_ask(statutory_config: dict | None, today: date,
               people: dict | None = None) -> str:
    """The register-gap requests, as a page — the record of what the
    D-62 sender sends, and the thing to forward by hand on a day the
    transport cannot deliver."""
    names = _names(people)

    held, unrouted = _by_holder(statutory_config, today)
    lines = [
        f"REQUESTS TO SEND — {today:%d-%b-%Y}",
        "",
        "One block per person. Under decision D-62 the daily run sends",
        "each block to its holder — internal ubcsis.com addresses only,",
        "once per week per question, until the register gains the date.",
        "This page is the record of what goes out, and the fallback to",
        "forward by hand on a day the transport cannot deliver.",
        "",
    ]
    if not held and not unrouted:
        lines += ["Nothing outstanding. Every class 1 rule that can carry a "
                  "date has one.", ""]
        return "\n".join(lines)

    for holder, rows in sorted(held.items()):
        who = names.get(holder, holder)
        lines += [
            "════════════════════════════════════════",
            f"TO: {who} <{holder}>",
            "SUBJECT: [CONTROL] Statutory dates needed — "
            f"{len(rows)} item{'' if len(rows) == 1 else 's'}",
            "════════════════════════════════════════",
            "",
            _ask_body(who, rows),
            "",
        ]

    if unrouted:
        lines += [
            "════════════════════════════════════════",
            f"NO HOLDER RECORDED — {len(unrouted)}",
            "",
            "These need an answer and the register does not say whose it",
            "is. Control does not guess a name, so nothing above asks for",
            "them (§1.1). Add `answer_held_by` to the row and re-run:",
            "",
        ]
        for row in unrouted:
            lines.append(f"  {row.get('id')} — {row.get('open_question')}")
        lines.append("")

    return "\n".join(lines)
