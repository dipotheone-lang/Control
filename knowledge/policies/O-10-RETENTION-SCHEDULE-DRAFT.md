# Records Retention Schedule — DRAFT for counsel

**United Brothers Co. (UBCSIS) — Control obligation engine**
**Charter reference:** §12.5, precondition O-10
**Status:** DRAFT of 31-Aug-2026 — **not in force.** O-10 stays open until
counsel reviews this and a named person records the confirmation.
**Machine-readable version:** `config/retention.yaml` (the operative file
once confirmed; this document is its explanation for a human reader).

---

## Why this exists

Control accumulates a corporate record — obligations, submissions,
verdicts, registers, disputes, and, once the mailbox scope opens,
correspondence metadata about identified people. A record with no defined
end is two problems at once: it breaches the data-protection principle that
personal data is kept no longer than its purpose needs, and it leaves the
company unable to say what it holds or why.

Two legal forces pull in opposite directions on almost every class:

- **A floor.** Egyptian commercial and tax law impose minimum retention on
  commercial books and their supporting documents — commonly five years.
  Below the floor, deletion is itself a breach.
- **A ceiling.** Egypt's Personal Data Protection Law No. 151 of 2020 —
  executive regulations issued 1 November 2025, full enforcement expected
  around October 2026 — requires personal data to be kept no longer than
  the purpose requires. Above the ceiling, retention is the breach.

This schedule sets a period between the two for each class, and flags the
classes where they genuinely conflict for counsel to resolve.

---

## The schedule

| Record class | Keep | Governed by | Personal data |
|---|---|---|---|
| Audit log (hash chain) | 7 years, whole | Evidentiary; cannot be partially trimmed | Yes |
| Obligations, submissions, findings | 7 years | Commercial floor + margin | Yes |
| Class 2 commercial registers | 7 years | Contractual/commercial | No |
| Financial records | 7 years | Tax/commercial floor | No |
| HR — people, absence | During employment + 5 years after leaving | Labour law | Yes |
| Disputes | 6 years | Labour-matter evidence | Yes |
| Anomaly / fraud flags | 3 years | Signals, not findings; PDPL-sensitive | Yes |
| **Mailbox metadata** | **2 years** | **PDPL minimisation — tightest ceiling** | **Yes** |
| Outbox / sent / approvals | 7 years | Evidentiary | Yes |
| Learning records | 5 years | Change record (§14) | No |
| Backups | per `backup.yaml` (365 days, min 7) | Inherits contents' sensitivity | Yes |
| Discovery output | none — deleted (D-61) | Never archived | Yes |

---

## How deletion works — the control, not the calendar

§12.5 requires deletion to be **deliberate and logged**. Nothing here runs
on a silent timer:

1. When a class reaches its period, Control **lists the candidates** for a
   human to authorise — it does not delete on its own.
2. Every authorised deletion writes to the **hash-chained audit log** with
   the reason and the authoriser — the same evidence shape as the D-61
   discovery purge, so a deletion leaves the same trace as data that was
   never collected.
3. A class is **never deleted from live storage while its only copy is an
   unverified backup** (§13.3) — the backup is proven restorable first.

---

## What counsel needs to decide

Three questions this draft cannot answer for itself:

1. **The commercial floor.** Is five years correct for commercial books and
   supporting documents under current Egyptian tax and commercial law, and
   does the seven-year figure used here sit comfortably above it?
2. **The HR periods.** What limitation periods under the **2025 Labour Law**
   set how long an ex-employee's records may be kept after they leave?
3. **The two sensitive classes** — anomaly/fraud flags and mailbox metadata.
   These carry the most PDPL exposure and the least commercial justification.
   The periods here (3 years and 2 years) err short deliberately; counsel to
   confirm they are short enough, and to confirm that **mailbox metadata may
   not begin to accumulate at all until O-07 — the lawful basis and the
   employee notification — is closed.** A short retention is not a substitute
   for a lawful basis to hold the data in the first place.

---

## What this draft does not do

- It does **not** close O-10. That needs counsel and a recorded human
  confirmation.
- It does **not** touch D-01. Client-confidential document *contents* are
  never stored under any of these periods — the confidential classes hold
  metadata only, and this schedule governs how long that metadata lives, not
  whether the body may be read. The body may not.
- It does **not** open the mailbox scope. That is O-07 and O-08, separate
  preconditions; a retention schedule says how long data may be kept once
  lawfully held, not that it may be collected.
