> **Historical record, 17-Aug-2026. Do not follow it.**
>
> This was the orientation brief while Control was in Phase 0 discovery.
> Almost every operational statement in it is now false: the phase, the
> run mode, the test count, the paths, the list of what is built, and
> the list of what is outstanding. `docs/RESUME-HERE.md` is the current
> state; `CLAUDE.md` is the authority.
>
> It is kept, trimmed to the two things it records that nothing else
> does: what the first real mailbox scan found, and the charter
> deviation it flagged — which was resolved, in the way it asked for.

# Handoff brief — Phase 0, 17-Aug-2026 (historical)

## What the first real run found

The numbers that shaped every decision since:

- `control@ubcsis.com` is **new** and holds almost nothing. The
  company's history lives in `contact.ubcsis@gmail.com` (~10,000
  messages), `info@`, `ahmed@`, `hr@`, `sales@`.
- `invoicing.eta.gov.eg` appears in high volume — direct evidence of the
  class 1 statutory e-invoicing obligation (§2.1), and the reason
  `STAT-ETA-SUB` and `STAT-ETA-REJ` are live rows rather than dormant
  ones.
- Several major counterparties appear that are **not** on the charter's
  §12.1.1 confidential list. They need classification under **O-04**,
  which is still open.
- ~10,000 messages of company correspondence sit in a consumer Gmail
  account — the exposure review finding **V1** predicted, quantified
  here, and the reason D-09 records what deferring its replacement
  accepts.

## The charter deviation it flagged, and how it ended

This file said, of reading mail over Outlook COM rather than Graph:

> **Before Phase 2 it must either move to Graph or be recorded as a CEO
> decision in Appendix B. Do not let it become permanent by silence.**

It did not become permanent by silence. **D-58 (30-Aug-2026)** records
the decision explicitly: Outlook carries the class 1 alerts, Graph is no
longer waited on, and the cost is written into the row — a transport
needing a powered laptop cannot hold a class 1 schedule, so on the day a
filing falls due with the machine asleep, nobody is told. That was
raised as advice against the decision, decided anyway, and mitigated:
an alert that cannot leave is written `UNDELIVERED`, never marked sent,
and retried on the next run.

The wider objection this file raised — that COM reaches every mailbox in
the Windows profile — is gone rather than accepted. Under
`OPERATING_SCOPE=STATUTORY_ONLY` nothing is fetched at all. The profile
does hold 18 stores, including two on another company's domain; Control
reads none of them.

## The rules, which have not changed

1. **Never fabricate.** Missing or unreadable → say so. A visible gap is
   a finding; a filled gap is a fabrication (§1.1).
2. **Nothing goes outside ubcsis.com.** The external gate never opens
   (§10). The sole scoped exception is the §3.1 continuity CC under
   D-04.
3. **Write only inside `CONTROL_ROOT`.** Everything else is read-only
   (§1.13).
4. **You may not amend the charter.** Only Ahmed Diab does, with a
   version and reason (§17). Propose amendments; never edit.
5. **Findings address the process, never the person** (§1.4).
