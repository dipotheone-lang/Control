# Records retention schedule

**Closes:** open decision **O-10** (charter §12.5)
**Also gates:** decision **D-07**, the extended mailbox scope (§3.1a)
**Status:** `DRAFT — NOT LEGAL ADVICE.` Every period below is a proposal
awaiting confirmation by counsel.

---

## 0. Why a schedule, and why before the scope widens

§12.5 requires a retention schedule per record class, exceeding
statutory minimums, with deletion deliberate and logged.

D-07 makes it urgent rather than tidy. Widening ingestion from one
mailbox to eight without a retention rule accumulates personal data
with no defined end — which is why O-10 gates the scope change rather
than trailing behind it.

**Two statutory floors constrain everything below, and neither is
established in this draft:**

- Egyptian commercial and tax law impose minimum retention on
  commercial books and supporting documents — commonly cited as five
  years, `TO BE CONFIRMED PER CLASS`.
- The PDPL constrains the other direction: personal data may not be
  kept longer than the purpose requires.

Where those pull against each other, the commercial floor wins for the
document and the PDPL should shape the personal-data fields attached to
it. Counsel to confirm.

---

## 1. Schedule

Retention runs from the end of the period the record belongs to, unless
stated otherwise.

### Class A — Statutory and financial records

| Record | Where | Proposed | Basis | Status |
|---|---|---|---|---|
| Statutory filing evidence (VAT, WHT, payroll tax, social insurance, ETA e-invoicing) | `submissions`, `data/submissions/` | Statutory minimum + 1 year | Commercial/tax law floor | `TO BE CONFIRMED` |
| Contract register entries | `registers_contracts` | Contract end + statutory minimum | Limitation periods | `TO BE CONFIRMED` |
| Financial instruments — guarantees, bonds, retention | `registers_instruments` | Release or expiry + statutory minimum | As above | `TO BE CONFIRMED` |
| Tender records and outcomes | `registers_tenders` | 5 years from result | Proposal | `TO BE CONFIRMED` |
| Quotations issued and received | `registers_quotations` | 5 years from expiry | Proposal | `TO BE CONFIRMED` |

### Class B — Operational compliance records about identified individuals

These carry the highest PDPL sensitivity: they are records of who did
what, when.

| Record | Where | Proposed | Reasoning |
|---|---|---|---|
| Submission and verdict records (class 3) | `submissions`, `findings` | **24 months** | Long enough for the §11 six-month trend and an annual review with comparison; short enough that a defect from three years ago cannot resurface in a conversation about a person |
| Anomaly observations (S1–S4) | `anomalies` | **24 months**, except any flag under investigation, retained until the investigation closes | Fraud patterns need multi-period visibility; unbounded retention of unconfirmed suspicion does not |
| External SLA thread records | `external_threads` | **24 months** | Sufficient for trend and systemic findings |
| Dispute records and adjudications | `disputes` | **Life of the golden set** — a dispute upheld becomes a permanent test case (§13.1) | The test case is retained; see the note below |
| Absence records | `absence` | Aligned with HR's own retention, `TO BE CONFIRMED` | Should not diverge from the HR system |
| Roster and reporting lines | `people` | Employment + statutory minimum | HR record |

> **Note on disputes.** §13.1 makes every upheld dispute a permanent
> golden-set case, which pulls against deletion. The resolution
> proposed: the *test case* is retained permanently in anonymised form
> — the document, the form, the clause, the correct verdict — while the
> *dispute record* naming the submitter is deleted on the Class B
> schedule. The system keeps what it must learn from and drops what it
> does not need to name. **Counsel to confirm this is sufficient.**

### Class C — System records

| Record | Where | Proposed | Reasoning |
|---|---|---|---|
| Hash-chained audit log | `logs/*.jsonl`, `audit_log` | **7 years** | The chain is the evidence that the record is unaltered (§13.3). Truncating it breaks the assurance for everything it covered. A chain break is a critical incident, and deletion is a chain break |
| Learning ledger and adaptations | `learning_ledger`, `learning/` | Life of the system | Needed to explain why a threshold is what it is |
| Statistical baselines | `baselines` | Rolling — superseded values retained 24 months | Aggregate, not personal |
| Knowledge base (project codes, supplier aliases) | `knowledge_base` | Life of the system | Reference data |
| Outbox — sent and drafted messages | `outbox/sent/` | 24 months | Proof of what was sent, aligned with Class B |
| Encrypted backups | `data/backup/` | 12 months rolling | Cold-start capability without an indefinite shadow copy |

> **The audit log is the hard case, and it is flagged rather than
> resolved.** It contains personal data by construction — it records who
> did what — and it is also the integrity control over every other
> record. Deleting from it defeats the hash chain; keeping it for seven
> years is the longest retention in this schedule. **Counsel must rule
> on this specifically.** One option, if 7 years is not defensible: age
> out the log's personal fields while preserving the hashes, so the
> chain still verifies but no longer names anyone. That is a build
> change, not a config change, and it is not built today.

### Class D — Mail metadata from the extended scope (D-07)

The category the scope change creates, and the reason O-10 gates it.

| Record | Proposed | Reasoning |
|---|---|---|
| Message metadata not attached to any tracked obligation or thread | **90 days** | Metadata swept from a shared mailbox and matched to nothing has served its purpose once the sweep completes. Keeping it because it was easy to collect is exactly the accumulation §12.5 exists to prevent |
| Message metadata attached to an obligation or external thread | Class A or B by what it attaches to | It has become part of a record |

---

## 2. Deletion procedure

§12.5: deliberate and logged.

1. Deletion runs on a **scheduled review**, not continuously. A
   quarterly job proposes what falls due; a human approves it.
2. Every deletion writes an audit-log entry naming the record class,
   the count and the authorising person. **The log of a deletion is not
   itself deleted.**
3. Deletion never modifies an existing row. Append-only means the
   deletion is recorded as an event, and the underlying rows are
   removed by an authorised maintenance path outside the normal engine.
4. **Nothing is deleted while a period lock, an open dispute, or a
   legal hold touches it.**

> **Not built yet.** No deletion job exists in the codebase. This is a
> Phase 2 build item, and it is listed here rather than assumed: a
> retention schedule with no mechanism is a document, not a control.
> Building it before deletion first falls due is sufficient; pretending
> it exists is not.

---

## 3. Legal hold

Any record subject to a dispute, an investigation, an audit, or actual
or anticipated litigation is exempt from deletion until released in
writing by the CEO. Holds are logged with a reason and reviewed
quarterly.

---

## 4. Questions for counsel

1. **The statutory floor.** What is the actual minimum retention under
   Egyptian commercial and tax law, per record class? The five-year
   figure in the charter is cited as "commonly" and needs confirming.
2. **PDPL ceiling.** Does the PDPL impose a maximum, or a
   necessity-based test to be documented per class?
3. **The audit log.** Seven years for a hash-chained log naming
   individuals — defensible? If not, is hash-preserving anonymisation
   acceptable, and on what schedule?
4. **Disputes.** Is the anonymised-test-case split at Class B
   sufficient, or must the underlying case be deleted entirely?
5. **Class D, 90 days.** Is that defensible for metadata swept from
   shared mailboxes and matched to nothing?
6. **Employment records.** How should absence and roster retention
   align with the IWR and the 2025 Labour Law? `UNVERIFIED.`
7. **The Gmail archive.** Roughly 10,000 messages sit in
   `contact.ubcsis@gmail.com`, an external consumer account. What
   retention applies, and what should be done with it? The charter's
   standing recommendation is replacement.

---

## 5. Sign-off

| | Name | Date | Signature |
|---|---|---|---|
| Reviewed by counsel | | | |
| Approved by | Ahmed Diab, CEO | | |

**O-10 closes when every `TO BE CONFIRMED` in §1 carries a confirmed
period and this schedule is approved.** The retention periods then go
into `config/retention.yaml` so the engine can act on them rather than
merely cite them.
