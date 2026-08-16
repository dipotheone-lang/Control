> **Superseded for day-to-day use by `docs/RUNBOOK.md`**, which carries the current commands end to end. This file is kept for the background it records.

# CEO DECISION PACK — Phase 0 gate

**For:** Ahmed Diab, CEO — sole authority to amend the charter (§17)
**Prepared by:** Control (automated), from Phase 0 discovery evidence
**Status:** proposals only. Control may propose amendments with evidence;
it may never edit the charter (§17).

---

## Why this exists

Phase 0 ends when three things happen (§6): the obligation register is
approved, the confidential scope is confirmed, and the shared-mailbox
decision is taken. None of them is a technical task. The build is
waiting on you, not the other way round.

Eleven decisions were open at the start of Phase 0. One has closed on
evidence. Two more can now be closed or narrowed with what discovery
found. The rest need people, not data.

---

## What discovery actually found

Measured, not estimated. Every figure traces to scanned mailbox
metadata; no message body was read (§12.1.2).

| Observation | Number | Why it matters |
|---|---|---|
| Correspondence with the Egyptian Tax Authority e-invoicing system (`invoicing.eta.gov.eg`) | 767 messages | Direct evidence of a **Class 1 statutory obligation** operating at volume. Class 1 is the charter's highest priority and the only class that carries fines. |
| Distinct external domains | 486 | Each needs a confidentiality classification (O-04). The charter names seven clients; the mail names hundreds of counterparties. |
| Company correspondence held in a consumer Gmail account (`contact.ubcsis@gmail.com`) | ~10,144 messages | The exposure review finding **V1** predicted this. It is now measured. |
| Messages ever copied to `control@` | 0 in the scanned history | **This measures nothing yet** — `control@` is new. See O-05. |
| Recurring internal report series in `sales@` | none found | `sales@` is a business-development channel, not a controlled-reporting one. |

**The single most important line above is the first one.** A system
built to chase weekly reports would have found nothing of value in
these mailboxes. What it found instead is a statutory filing obligation
and an active commercial cycle — precisely the reframing the expert
panel demanded.

---

## Decisions ready to close

### O-09 — `UB_ROOT` — **CLOSED**

Confirmed as `E:\UBCSIS Co Date Jan 2026`. No further action; recorded
here so the register can be updated.

### O-04 — confidential scope — **narrowed, needs your confirmation**

Discovery found major counterparties that are **not** on the §12.1.1
list, several of them larger by correspondence volume than clients that
are:

| Counterparty | Messages | On the charter's list? |
|---|---|---|
| `enova-me.com` | 445 | No |
| `suezsteel.com` | 404 | No |
| `saint-gobain.com` | 273 | Yes |
| `siemens-energy.com` | 265 | Yes |
| `galaxysurfactants.com` | 220 | Yes (as Galaxy Chemicals) |
| `lafarge.com` | 203 | **No** |
| `eg.ivldhunseri.com` | 152 | **No** |
| Fertiglobe (via supplier registration threads) | — | **No** |

Also notable: **KNAUF, Canal Sugar, Sukari and Air Liquide do not appear
in the top counterparties at all.** That is worth your attention for a
different reason — §2.2 warns that a lapsed prequalification produces
silent revenue decline: you stop being invited rather than being
rejected. Low correspondence with a named client is the shape of that.

**Decision required:** confirm the classification of each domain in
`discovery/CONFIDENTIAL-SCOPE.md`. Every unmatched domain is currently
defaulted to CONFIDENTIAL, which is the correct asymmetry (§12.1.1) but
is a placeholder, not an answer.

### O-05 — shared-mailbox visibility — **do not decide yet**

The evidence the charter expected (§3.1a, Stage H) cannot be produced
from history, because `control@` did not exist during the period
scanned. A 0% CC-coverage figure would be an artefact, and deciding on
it would be deciding on nothing.

**Recommendation:** set a start date, ask staff to copy `control@` from
that date, and measure forward for one month. Control now tracks
CC-compliance as a standing metric for exactly this purpose. Decide
O-05 on that measurement, not on the historical zero.

---

## Decisions that need people, not data

### O-03 — statutory calendar — **highest value, blocked on the advisor**

767 messages with the ETA e-invoicing system prove the obligation
exists and is active. They do **not** establish its deadlines, and the
charter forbids hardcoding a statutory date from assumption (§2.1).

**Action:** the tax advisor confirms filing dates for VAT, withholding
tax, payroll tax, social insurance, ETA e-invoicing, corporate income
tax, and the register/licence renewals. Until then every rule stays
marked `UNVERIFIED — CONFIRM WITH ADVISOR` and alerts early.

This is the cheapest high-value action available. One meeting closes
the charter's top-priority class.

### O-02 — authority thresholds

Still empty. Under §3.2 the compensating controls for the
segregation-of-duties concentration therefore default to itemising
**every** commitment to you weekly. That default is deliberate and
conservative, but it is not a substitute for real limits.

### O-01, O-06, O-07, O-08, O-10, O-11

Reporting lines · IWR amendment · PDPL lawful basis · usage policy ·
retention schedule · working hours. All Phase 1 gate items; none can be
answered from mail. The usage policy (O-08) deserves emphasis: the
panel judged adoption, not capability, to be the binding constraint.

---

## Two new decisions discovery created

### NEW-1 — Stage C cannot read the contracts that matter

§6 requires contractual dates, notice periods, LD terms and guarantee
expiries extracted into the class 2 registers. **Decision D-01 forbids
opening the body of any client-confidential document.** Contracts with
NDA clients are confidential by definition, so the requirement and the
prohibition collide exactly where the money is.

Consequence, stated plainly: **for your NDA clients, Control cannot see
a guarantee expiry, a claim notice window, or an LD cap.** Those
deadlines remain wholly with the responsible department, and a green
dashboard in Control is not assurance over them.

Options:

1. **Accept the gap.** Record in the register that class 2 commercial
   deadlines for NDA clients are managed outside Control.
2. **Amend D-01 narrowly.** Permit extraction of dates and term
   durations only — processed locally, nothing leaving the machine, no
   clause text quoted in any report or reply. This is a charter
   amendment and belongs in Appendix B with a date and a reason.
3. **Extract manually.** A human reads each contract; only the dates
   enter the registers.

Option 2 is the only one that makes `COMMERCIAL-EXPOSURE.md` complete.
It must be your written decision — it must not happen through a change
to code.

### NEW-2 — Control is reading mail by a route the charter does not describe

§5.1 specifies Microsoft Graph with certificate authentication and a
**mandatory** Exchange Application Access Policy restricting the engine
to `control@ubcsis.com` alone. That path is built but the tenant was
never provisioned, so mail is currently read through Outlook on the
laptop.

Outlook automation runs as the signed-in Windows user and can therefore
reach **every mailbox in that profile** — a wider permission surface
than §5.1 allows, touching §12.2 data minimisation. Two guards are
implemented in code: the mailbox is resolved by address and never falls
back to another, and sending is disabled outright.

For a Phase 0 that reads metadata and sends nothing, this is a
defensible trade. **Before Phase 2 it must either move to Graph or be
recorded as a decision in Appendix B.** What it must not do is become
permanent by silence.

---

## The one-page summary

| # | Decision | Status | Blocks |
|---|---|---|---|
| O-09 | `UB_ROOT` | **closed** | — |
| O-03 | Statutory calendar with the advisor | open — **do this first** | Class 1 |
| O-04 | Confidential scope | narrowed, needs confirmation | Phase 0 gate |
| O-05 | Shared-mailbox option | **defer**, measure forward 1 month | Phase 0 gate |
| O-02 | Authority thresholds | open | SOD controls |
| O-01 | Reporting lines | open | Escalation routing |
| O-06/07/08/10 | IWR · PDPL · usage policy · retention | open | Phase 2 |
| O-11 | Working hours | open | S1 out-of-hours signal |
| NEW-1 | D-01 vs contract extraction | **new** | COMMERCIAL-EXPOSURE |
| NEW-2 | Outlook route vs §5.1 Graph | **new** | Phase 2 |

Two actions would move this furthest: **book the tax advisor**, and
**decide NEW-1**. Everything else can proceed in parallel.

---

*Prepared under §17: Control proposes with evidence; the charter is
amended only by its owner, with a version, a date and a reason.*
