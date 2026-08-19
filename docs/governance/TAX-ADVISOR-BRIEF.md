# Statutory calendar — brief for the tax advisor

**This document is now generated.** Produce the current version with:

    python -m control advisor-brief --control-root <CONTROL_ROOT> --ub-root <UB_ROOT>

It is written to `discovery/TAX-ADVISOR-BRIEF.md`.

---

## Why it was moved out of this file

The hand-written version was drafted when nothing was known, and it
said so on every row: `UNVERIFIED — CONFIRM WITH ADVISOR`, twelve blank
cells, and an explicit refusal to propose answers on the grounds that a
proposal anchors the person correcting it.

Two things then changed, and both of them made a static document the
wrong shape.

**The CEO stated twelve rules** in the execution order of 18-Aug-2026,
and step 5 reversed the method: *"Send the completed statutory table
for correction, not blank rows."* Blank rows now withhold what we hold
and ask a paid professional to rediscover it.

**The archive was counted.** The brief carries a column showing what
the company actually filed — how many periods, at what spacing, and
whether that is consistent with the stated cadence. That column cannot
be maintained by hand: it changes every time the archive is rescanned,
and a stale number in a document sent to an advisor is worse than no
number.

So §11's hard rule applies to this document as much as to a management
report: if a figure cannot be traced to a row that traces to a
document, it does not appear. Generating it is how that is guaranteed
rather than hoped for.

## What the generated version keeps from this one

- The three questions beyond the table — anything missing, anything
  changing in the next twelve months, and the penalty per obligation
- The distinction between the filing deadline and the operative one:
  if a return is due on the 10th and the data cannot close before the
  8th, the company's real deadline is the 8th
- The anchoring warning, now stated as the failure mode rather than
  avoided by leaving cells empty: **agreeing with a row because it
  looks plausible** is what this brief is trying not to produce

## What it adds

- The two rows the CEO wants answered first, before the table
- Provenance on every row — all `ceo_stated`, none verified
- The practice column, with what it cannot tell you said as plainly as
  what it can
- The two data-protection rows routed to counsel instead, named rather
  than silently dropped so twelve in the register and ten in the brief
  reconcile
- A bilingual covering note, the Arabic authoritative (§4)

**O-03 closes when every row carries a confirmed deadline and
`verified_by_advisor` is set true — by a named human, never by the
system (execution order §7).**
