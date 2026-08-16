# Personal data processing — lawful basis and employee notification

**Closes:** open decision **O-07** (charter §12.2)
**Also gates:** decision **D-07**, the extended mailbox scope (§3.1a)
**Status:** `DRAFT — NOT LEGAL ADVICE.` For review by counsel before use.
**Law:** Egypt, Personal Data Protection Law No. 151 of 2020 ("PDPL")

---

## 0. Why this document exists

Control reads mailboxes and generates records about identified
individuals. That is processing personal data under the PDPL, whatever
else it is. §12.2 makes four things mandatory before Phase 2:

1. A documented lawful basis
2. Written employee notification of the processing, its purpose and its
   retention
3. A defined retention and deletion schedule
4. Confirmation with counsel of the current status of the executive
   regulations, and of any registration or DPO requirement

Sections 1–5 below draft (1) and (2). (3) lives in
`RETENTION-SCHEDULE.md`. (4) is a question for counsel and is **not**
answered here — see §7.

---

## 1. Controller

| | |
|---|---|
| Controller | United Brothers Co. for Contracting, Supplies & Industrial Services |
| Address | `TO BE CONFIRMED` |
| Responsible officer | Ahmed Diab, CEO |
| Contact for data subjects | `TO BE CONFIRMED` — a named human, not control@ |

> **Note.** The data-subject contact must not be `control@ubcsis.com`.
> A person exercising a right against an automated system should not
> have to address the automated system. Suggest the COO or HR &
> Admin Manager.

---

## 2. What is processed

### 2.1 Mailboxes read

**Today (Option A):** `control@ubcsis.com` only.

**Under decision D-07 (Option C), once this document and O-08 and O-10
are closed:** the seven shared functional mailboxes —
`sales@`, `procure@`, `info@`, `accounts@`, `hr@`, `hse@`,
`marketing@` — all `@ubcsis.com`.

**Not read, and named here so the exclusion is on the record:**
`ahmed@ubcsis.com` (a named individual's mailbox) and
`contact.ubcsis@gmail.com` (an external consumer account). Adding
either is a separate decision requiring a new lawful-basis assessment.

**Historical note, stated rather than omitted.** During Phase 0
discovery, conducted read-only and metadata-only under
`RUN_MODE=DISCOVERY`, Control scanned archives of `info@`, `sales@`,
`hr@` and `contact.ubcsis@gmail.com`. Counsel should confirm whether
that historical scan requires its own notification, retrospective or
otherwise. It is raised here rather than left for someone to discover.

### 2.2 Categories of data

| Category | Detail | Source |
|---|---|---|
| Identity and contact | Name, work email, role, reporting line | `config/people.yaml`, `people` table |
| Message metadata | Sender, recipients, timestamp, subject line, attachment filenames, file type and size, thread position | Mailbox |
| Submission records | What was submitted, by whom, when, against which obligation, and the verdict | `submissions`, `findings` |
| Timeliness records | Due date versus received date; working days late | `submissions` |
| Absence records | Registered leave dates and delegate | `config/absence.yaml`, `absence` table |
| Anomaly observations | S1–S4 factual signals, including submissions timestamped outside 09:00–17:00 | `anomalies` |
| Dispute records | Disputes raised and their adjudication | `disputes` |
| External response records | Whether an external thread received a reply within SLA, and who owned it | `external_threads` |
| Audit trail | Every action taken, hash-chained | `logs/*.jsonl`, `audit_log` |

**Message bodies are not read** for items classified client-confidential
(§12.1, decision D-01). For all other items the body is read only to the
extent needed to evaluate the submission against its controlled form.

**No special categories** of personal data are processed by design.
Counsel should confirm whether HSE incident records — which may touch
health data — fall inside the PDPL's special-category definition. HR
mailbox subject lines are redacted at capture for this reason, but that
is a mitigation, not a legal conclusion.

### 2.3 What is deliberately not processed

- Personal mailboxes of named individuals
- Message content of client-confidential items (D-01), with the narrow
  exception of dates and term durations from contracts (D-05)
- Any assessment, score or ranking of an individual's performance.
  Control evaluates documents against forms. §1.4 forbids it from
  characterising conduct, and §12.4(1) states this to staff directly.

---

## 3. Purposes

1. Ensuring statutory filing and payment deadlines are met (class 1)
2. Ensuring commercial deadlines are met — tenders, claim notices,
   guarantee expiries, accreditations (class 2)
3. Verifying that operational reports are complete, arithmetically
   consistent and on the controlled form (class 3)
4. Ensuring external correspondence receives a reply within SLA
5. Surfacing anomaly and fraud signals for management judgement
6. Maintaining an auditable corporate record

**Each purpose is a control objective, not a personnel objective.** The
distinction is not cosmetic: it determines what a legitimate-interests
balancing test weighs, and it is the substance of the commitment made
to employees in the usage policy.

---

## 4. Lawful basis — for counsel to select and justify

The charter does not choose this, and neither does this draft. Three
candidates, with what I understand to weigh for and against each:

### 4.1 Legal obligation

Strongest for the class 1 purpose. The company is required to file and
pay on statutory deadlines; a control ensuring it does so is arguably
processing necessary for compliance with a legal obligation.

*Limit:* it covers the statutory purpose well and the others poorly. It
does not reach class 3 report chasing or SLA monitoring.

### 4.2 Legitimate interests

The most likely basis for purposes 2–6. The interest — not missing
deadlines that forfeit money or breach contracts — is concrete and
documented.

*Requires:* a balancing test on the record, weighing the intrusiveness
of reading work correspondence against that interest. Points that
belong in the balance, and that the system was built to put there:

- Only work mailboxes are read; personal mailboxes are excluded by name
- Shared functional mailboxes are addresses, not individuals
- HR subject lines are redacted at capture
- Client-confidential content is never read at all
- Outputs may never be the sole basis for a disciplinary or pay
  decision (§12.4(3)), and every finding is contestable (§8.4)
- The system audits process defects, not people (§1.6)

*Also requires:* confirmation that Egyptian law recognises legitimate
interests in the form assumed here. `UNVERIFIED.`

### 4.3 Consent

**Recommended against**, and the reason is not squeamishness. Consent
from an employee to their employer is rarely freely given, and consent
that can be withdrawn would leave the deadline engine switchable off by
the person whose deadlines it watches. That is not a control.

**Recommendation for counsel:** legal obligation for class 1, legitimate
interests for the remainder, with a written balancing test. Not consent.

---

## 5. Employee notification — draft text

To be issued by the CEO, in both languages, before the first live
reminder. Both versions say the same thing; the Arabic is authoritative
(§4).

> ### Notice of personal data processing — the Control system
>
> The company operates an automated system called **Control**, which
> monitors deadlines and the completeness of reports.
>
> **What it reads.** Control reads the mailbox `control@ubcsis.com`,
> and the shared functional mailboxes `sales@`, `procure@`, `info@`,
> `accounts@`, `hr@`, `hse@` and `marketing@`. These are shared company
> addresses. **Control does not read anyone's personal mailbox.** For
> mail in the HR mailbox, subject lines are removed before anything is
> stored.
>
> **What it records.** Who submitted which report, when, against which
> deadline, and whether the document matched the approved form. It also
> records whether external messages received a reply within the agreed
> response time.
>
> **What it does not do.** Control does not assess anyone's
> performance, and it does not judge conduct. It compares documents
> against forms and dates against deadlines. Its findings may never be
> the only basis for any disciplinary or pay decision.
>
> **How long records are kept.** See the retention schedule at
> `TO BE CONFIRMED`.
>
> **How to contest a finding.** Reply to any Control message with the
> word **DISPUTE** on the first line. The deadline clock on that item
> stops immediately and the CEO adjudicates.
>
> **Your rights.** You may ask what is recorded about you, ask for a
> correction, and object to the processing. Contact `TO BE CONFIRMED`.
>
> Issued by Ahmed Diab, CEO — `DATE`

> ### إشعار بمعالجة البيانات الشخصية — نظام كنترول
>
> تُشغّل الشركة نظاماً آلياً باسم **كنترول** يتابع المواعيد النهائية
> واكتمال التقارير.
>
> **ما الذي يقرأه النظام.** يقرأ كنترول صندوق البريد
> `control@ubcsis.com`، وصناديق البريد الوظيفية المشتركة `sales@`
> و`procure@` و`info@` و`accounts@` و`hr@` و`hse@` و`marketing@`.
> وهذه عناوين مشتركة تخص الشركة. **ولا يقرأ كنترول صندوق البريد
> الشخصي لأي فرد.** أما بريد الموارد البشرية فتُحذف سطور الموضوع منه
> قبل حفظ أي بيانات.
>
> **ما الذي يسجله النظام.** من قدّم أي تقرير، ومتى، ومقابل أي موعد
> نهائي، وما إذا كان المستند مطابقاً للنموذج المعتمد. كما يسجل ما إذا
> كانت الرسائل الخارجية قد تلقّت رداً خلال المدة المتفق عليها.
>
> **ما الذي لا يفعله النظام.** لا يقيّم كنترول أداء أي فرد، ولا يصدر
> حكماً على السلوك. فهو يقارن المستندات بالنماذج والتواريخ بالمواعيد.
> ولا يجوز أن تكون ملاحظاته الأساس الوحيد لأي قرار تأديبي أو قرار
> يتعلق بالأجر.
>
> **مدة الاحتفاظ بالسجلات.** راجع جدول الاحتفاظ في
> `TO BE CONFIRMED`.
>
> **كيفية الاعتراض على ملاحظة.** يُرجى الرد على أي رسالة من كنترول
> بكلمة **اعتراض** في السطر الأول. يتوقف احتساب المدة على هذا البند
> فوراً، ويتولى الرئيس التنفيذي الفصل فيه.
>
> **حقوقك.** يحق لك الاطلاع على ما هو مسجل عنك، وطلب تصحيحه،
> والاعتراض على المعالجة. للتواصل: `TO BE CONFIRMED`.
>
> صادر عن أحمد دياب، الرئيس التنفيذي — `التاريخ`

**Acknowledgement.** Each employee signs and dates a copy. HR retains
the signed originals; the acknowledgement list is itself an O-06
requirement.

---

## 6. Transfers and processors

- **No cross-border transfer** of message content. Client-confidential
  content passes to no model or external service (D-01, D-05).
- **Sub-processors:** none at present. Control runs locally against
  Outlook (decision D-08) and, from Phase 2, against Microsoft Graph.
- **Microsoft** hosts the mailboxes and is therefore already in the
  picture as a processor for the company's email generally. Counsel
  should confirm whether the existing Microsoft 365 data-processing
  terms cover this use, or whether anything further is required.
- **Backups** are encrypted and held within `CONTROL_ROOT` (§5.2).

---

## 7. Questions for counsel

These are the points I could not resolve from the charter, and must not
resolve by assumption.

1. **Executive regulations.** What is the current status of the PDPL
   executive regulations, and what follows for this processing?
2. **Registration.** Does the company need to register as a controller,
   and does this processing trigger a DPO requirement?
3. **Lawful basis.** Confirm or replace the split proposed at §4.
   If legitimate interests: what form must the balancing test take, and
   must it be filed anywhere?
4. **Notification form.** Does written notice require signed
   acknowledgement, and is the bilingual text at §5 sufficient?
5. **HSE records.** Do incident records touch special-category health
   data, and if so what changes?
6. **Historical scan.** Phase 0 read archives of `info@`, `sales@`,
   `hr@` and a Gmail account, metadata-only. Does that require its own
   notification?
7. **The Gmail account.** `contact.ubcsis@gmail.com` holds roughly
   10,000 messages of company correspondence in a consumer account
   outside company control. The charter recommends replacing it
   monthly. What is the exposure while it exists?
8. **Data subject requests.** What is the required response time, and
   what must a response contain?

---

## 8. Sign-off

| | Name | Date | Signature |
|---|---|---|---|
| Reviewed by counsel | | | |
| Approved by | Ahmed Diab, CEO | | |
| Notification issued | | | |
| Acknowledgements collected by | Mohamed Ali, HR & Admin Manager | | |

**O-07 closes when this document is reviewed, the notification is
issued, and acknowledgements are on file.** Until then Control operates
on Option A and states the limitation in every report.
