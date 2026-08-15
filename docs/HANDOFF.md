# Handoff brief — for a Claude Code session running on the UBCSIS laptop

You are picking up a build already in progress. This file is the
orientation; the charter (`CLAUDE.md`) is the authority. Read §0–§2 and
§10 of the charter before changing anything.

## Where the project is

Phase 0 (Discovery), Level 0, `RUN_MODE=DISCOVERY`, `LEARNING_MODE=OBSERVE`.
**The engine sends nothing**, by design, and must not be made to.

Built and merged (202 tests, `python -m pytest`):

| Area | Module | Status |
|---|---|---|
| Startup, legal states, halt semantics | `startup.py`, `states.py` | done |
| Append-only store, hash-chained log | `db.py`, `audit.py` | done |
| Classification (§9) | `classify.py` | done |
| Evaluation C1–C7, verdicts (§7) | `evaluate.py` | done |
| Bilingual replies (§7.5, §4) | `render.py` | done |
| Enforcement, ladder, absence (§8) | `enforce.py` | done |
| Anomaly signals S1–S4 (§7.3) | `anomaly.py` | done |
| External watchdog (§8.5) | `watchdog.py` | done |
| Attachment security (§5.4) | `attachments.py` | done |
| Approval gates (§10) | `outbox.py` | done |
| Weekly report (§11) | `report.py` | done |
| Golden set (§13.1) | `goldenset.py` | done |
| Cycle orchestration | `cycle.py` | done |
| Graph transport | `transport.py` | built, tenant not provisioned |
| Outlook COM transport | `outlook.py` | **in use** |
| Discovery scan + analysis | `discovery/` | **in use** |

## How mail is being read, and why it matters

The charter §5.1 specifies Microsoft Graph with certificate auth and a
*mandatory* Exchange Application Access Policy restricting the engine to
`control@ubcsis.com` alone. That path is built but the tenant was never
provisioned — the admin sign-in kept landing on a personal Microsoft
account (Windows WAM), so the project switched to reading Outlook
directly over COM.

**This is a live charter deviation.** COM runs as the signed-in Windows
user and can reach every mailbox in the profile — a *wider* permission
surface than §5.1 allows, touching §12.2 (PDPL). Two guards are in the
code: the store is resolved by address and never falls back to another
mailbox, and sending is disabled unless explicitly enabled and matched
to the expected mailbox.

For Phase 0 (metadata only, sends nothing) this is a defensible trade.
**Before Phase 2 it must either move to Graph or be recorded as a CEO
decision in Appendix B.** Do not let it become permanent by silence.

## Running discovery

```powershell
$env:CONTROL_ROOT = "$env:USERPROFILE\Documents\Control\CONTROL"
python -m control phase0          # scan every mailbox, analyse, generate
python -m control analyse         # re-run analysis alone
python -m control verify          # DB integrity + audit chain
```

Requires classic Outlook running (the "new Outlook" has no COM), and
`pywin32`.

## What the first real run found

- `control@ubcsis.com` is **new** and holds almost nothing. The company's
  history lives in `contact.ubcsis@gmail.com` (~10,000 messages),
  `info@`, `ahmed@`, `hr@`, `sales@`.
- `invoicing.eta.gov.eg` appears in high volume — direct evidence of the
  **Class 1 statutory e-invoicing obligation** (§2.1).
- Several major counterparties appear that are **not** on the charter's
  §12.1.1 confidential list. They need classification under **O-04**.
- ~10,000 messages of company correspondence sit in a consumer Gmail
  account — the exposure review finding **V1** predicted, now quantified.

## Rules that bind you as much as the engine

1. **Never fabricate.** Missing or unreadable → say so. A visible gap is
   a finding; a filled gap is a fabrication (§1.1).
2. **Metadata only** during discovery. Do not read message bodies; the
   scan is deliberately built not to (§12.1.2).
3. **Nothing sends.** The external gate never opens (§10). Phase 0 sends
   nothing at all (§6).
4. **Write only inside `CONTROL_ROOT`.** Everything else is read-only
   (§1.13).
5. **You may not amend the charter.** Only Ahmed Diab does, with a
   version and reason (§17). Propose amendments; never edit.
6. **Findings address the process, never the person** (§1.4).

## What is genuinely outstanding

Human decisions, not code (charter Appendix B): **O-01** reporting lines ·
**O-02** authority thresholds · **O-03** statutory calendar with the tax
advisor · **O-04** confidential scope · **O-05** shared-mailbox option ·
**O-09** `UB_ROOT` path · **O-11** working hours.

Tooling not yet built: Stage C (forms, manuals and **contract date
extraction** — this feeds `COMMERCIAL-EXPOSURE.md`, the charter calls it
the highest-value single output), Stage E backfill, Stage F statistical
baselines, and the folder inventory run against a confirmed `UB_ROOT`.
