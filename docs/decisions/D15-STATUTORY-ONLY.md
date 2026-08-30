# Decision D-15 — statutory-only operation

**Status: ADOPTED, 30-Aug-2026.** In the charter at Appendix B, and in
§16 as a legal state. Charter version 4.11.

Decided by Ahmed Diab. Entered into `CLAUDE.md` by Control on his
express instruction — §17 otherwise reserves every edit to him, and the
Appendix B row records the same split so the provenance of the amendment
is not ambiguous later.

This file is the reasoning behind the row. The row is the decision.

---

## The decision

**Control operates on class 1 statutory obligations only, and reads no
mailbox.** It computes deadlines from `statutory-calendar.yaml`, alerts
the named owner and the CEO on the §2.1 schedule, and does nothing else.

`RUN_MODE=SUPERVISED` with `OPERATING_SCOPE=STATUTORY_ONLY` becomes a
legal state (§16), outside the phase sequence rather than a step in it.

## Why, on the evidence

Three numbers from the status page of 30-Aug-2026.

**No mailbox scan has ever completed on the operating machine.** Not a
quiet mailbox — never run. So the external watchdog (§8.5), submission
evaluation (§7), classification (§9) and the S1–S4 anomaly signals have
never operated on live data. The capability carrying every governance
cost in §12 and the whole adoption risk in §12.4 is unproven, not merely
ungoverned.

**130 of 314 documents in the contract folders are unreadable**, even
with OCR at a median confidence of 71.4. The class 2 commercial
registers — which §6 calls the highest-value output of the build — could
not be populated from the archive by any amount of extraction work. That
is a property of the estate, not of the engine.

**Nothing in §12 is circulated.** Usage policy 0 of 11, IWR 0 of 11,
PDPL notification not issued. Phase 2 as chartered cannot begin, and
closing those four would mean engaging counsel to authorise a capability
that has never demonstrably run here.

Against that, class 1 needs none of it. The deadline engine computes
from a calendar, not an inbox.

## What this delivers

§0 opens with the priority order, and this takes the first item:

> **No statutory deadline is missed** — tax, social insurance,
> e-invoicing, licences.

Four obligations carry a usable date today: VAT, withholding tax, social
insurance, and corporate income tax. The rest of the twelve fire no
countdown and are reported as gaps, unchanged.

## What this gives up, stated plainly

Everything else in §0. No report chasing, no external SLA watchdog, no
verdicts, no anomaly or fraud signals, no commercial registers, no
learning engine, no management reporting beyond the statutory horizon.
The §3.2 segregation-of-duties controls do not operate, because they
need transaction data Control will not be reading.

**The SOD finding does not go away because Control stops looking at it.**
One person still originates revenue, sets price, chooses supplier and
approves cost. That is a standing exposure recorded in the discovery
output, and narrowing the software does not narrow it.

## What stays binding, unchanged

- §1 in full. Never fabricate, cite everything, neutral language, log
  everything hash-chained, write only inside `CONTROL_ROOT`.
- **§10's external gate.** No mail to any external domain, in any mode.
  Statutory alerts go to internal recipients only.
- §5.1's transport requirement and **D-08**: Graph with certificate
  authentication before anything sends on a schedule. Outlook COM stays
  refused in SUPERVISED. This is not waived — a missed class 1 alert is
  the failure this whole scope exists to prevent, and a transport
  needing a powered laptop cannot carry it.
- §2.1: statutory deadlines are confirmed with the tax advisor and
  re-verified every January. Unverified rules alert early and are marked
  `UNVERIFIED`. **O-03 is not closed by this decision** — it becomes the
  only thing between here and operation.
- §5.2's append-only store, §13.3's self-audit, §5.6's startup halt.

## What is not required, and why

**No usage policy, PDPL notification or IWR amendment.** §12.4 governs a
system that measures process compliance of named individuals; §12.2
governs processing personal data from mailboxes. Statutory-only reads no
mailbox and evaluates no person's work. It sends tax deadlines to the
CFO and the CEO.

That reasoning should be put to counsel rather than assumed — it is
recorded here as the basis, not as a conclusion. If counsel disagrees,
the pre-conditions apply and this decision costs nothing already spent.

O-06, O-07, O-08 and O-10 remain open against any future widening. This
decision narrows scope; it does not close them.

## Reversal

Nothing here is discarded. The evaluation engine, the watchdog, the
registers, the learning layer and the governance drafts all remain in
the repository under test. Widening later means closing the §12
pre-conditions and moving the scope back — not rebuilding.

## What it takes to operate

| | Owner |
|---|---|
| Adopt this decision into Appendix B | Ahmed Diab |
| Confirm the twelve statutory rules — `advisor-brief` is generated and waiting | Tax advisor, none engaged (O-03) |
| Provision Graph: Entra app, certificate auth, Application Access Policy scoped to control@ | Tenant admin — `scripts/provision-graph.ps1` |

Control closes none of the three.
