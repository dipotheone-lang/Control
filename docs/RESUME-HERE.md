# RESUME HERE — state as at 26-Aug-2026

`docs/RUNBOOK.md` says how to run each thing. This file says **where the
build actually is and what the next action is**, so a new session — a
new PowerShell window or a new Claude Code session — can pick up without
rediscovering it.

`CLAUDE.md` is the authority. Nothing in this file overrides it.

---

## The two paths, confirmed on the machine

| | |
|---|---|
| `CONTROL_ROOT` | `C:\Users\Lape Top Suez\Documents\Control` — the repo checkout |
| `UB_ROOT` | `E:\UBCSIS Co Date Jan 2026` |

**`E:\UBCSIS Co Date Jan 2026\CONTROL` does not exist.** Charter §5.1
sets `CONTROL_ROOT=<UB_ROOT>/CONTROL`; in practice the repo checkout is
serving as `CONTROL_ROOT` and everything works. This divergence is
recorded rather than fixed — moving it is a decision, not a cleanup, and
it affects where D-11 backups land. Do not "correct" it silently.

Environment as at 26-Aug-2026: Windows 11, Python 3.13.14, Tesseract
5.4.0 with `ara`/`eng`/`osd` at `C:\Program Files\Tesseract-OCR`
(off PATH — `control.ocr` locates it without trusting PATH), tessdata at
`C:\Users\Lape Top Suez\AppData\Local\tessdata`. `doctor` reports all
five Python dependencies present.

**Claude Code cannot run on this laptop.** The CPU lacks AVX and the
Bun runtime segfaults on startup. Alternative install methods download
the same native binary. Work is done in a remote session and pulled
down; the laptop runs `python -m control` in PowerShell.

---

## What is done

**The obligation register is approved.** Six class 3 obligations,
assigned from the archive on 26-Aug-2026 and stamped by the CEO. §6
makes that approval the act that ends Phase 0's register gate, and it is
closed.

| id | what | owner | due |
|---|---|---|---|
| `OPS-TO-001` | Weekly Site Progress Report (F-CSO-23) | shymaa@ | sunday 10:00 |
| `OPS-TO-002` | Monthly Project Report (F-CSO-24) | a.elsayed@ | day 5 |
| `OPS-HSE-001` | Monthly HSE Audit Checklist (F-HSE-28) | hse@ | day 7 |
| `OPS-HRA-001` | Monthly Payroll Register (F-HRA-08) | hr@ | day 25 |
| `OPS-PROC-001` | Monthly Subcontractor Performance (F-CSO-09) | info@ | day 10 |
| `OPS-FA-001` | Monthly finance ledger | accounts@ | day 12 |

**Not one of those deadlines was observed.** Every row carries
`date_basis: assigned_by_control` and an `open_question`. The cadences
come from the manual or the archive; the days are Control's, chosen to
spread the load. Correcting one is editing one line in
`config/obligations.yaml` and re-running. The CEO's instruction was
explicit: *"you assign as per archives and past experience and will
improve on the go while running."*

Gate state at the last run:

- **Phase 0 gate** — 2 closed (obligation register, reporting lines),
  2 open (authority matrix on the D-06 interim, statutory calendar
  unverified by any advisor).
- **Phase 1 gate** — 1 closed (absence register), 5 open, 1 blocked.
  The block is the golden set: **D-03 puts those verdicts with the CEO
  alone**, unanchored, and nothing has been built to judge.

---

## The next action

Stage C over the folders that hold contracts, guarantees and delegated
limits. This is the highest-value output in the build — §6 calls
`COMMERCIAL-EXPOSURE.md` *"likely the highest-value single output"* and
says to read it first, because it will contain dates needing action
before the system is finished.

    python -m control contracts --control-root "C:\Users\Lape Top Suez\Documents\Control" --source "E:\UBCSIS Co Date Jan 2026\6. Clients Legal Documents,E:\UBCSIS Co Date Jan 2026\7. Suppliers Legal Documents,E:\UBCSIS Co Date Jan 2026\11. Vendor Registration Request,E:\UBCSIS Co Date Jan 2026\13. Delegations,E:\UBCSIS Co Date Jan 2026\14. Construction Management Files" --ocr --confidential-dates

Why those five folders: guarantees and notice periods in `6.` and `7.`;
client prequalifications in `11.` (§2.2 — a lapsed accreditation
produces silent revenue decline, you stop being invited rather than
rejected); delegated limits in `13.`, which is the evidence O-02 needs
before its 16-Sep-2026 review; contracts in `14.`

Why both flags. D-14 records that 47% of legal documents are
photographs of text, 81% for supplier legal documents — so without
`--ocr` the guarantee expiries this exists to catch are precisely the
ones no text layer reaches. `--confidential-dates` is D-05: without it
folder `6.` yields nothing, because every client there is under NDA and
§12.1 keeps Control out. Under D-14 the OCR text of a confidential
document **is never retained** — it passes to term extraction
transiently and the stored result keeps only the value, its confidence
and the document reference.

It runs long. Per-document results cache to `data\stage-c-cache`, so an
interrupted run resumes. **Do not change the flags between runs** — a
different ruleset is a different reading and invalidates the cache by
design.

### Reading the result

Three numbers in the summary block matter:

- **`unreadable/scanned`** — documents even OCR could not read. §5.5:
  nothing is guessed from them, they go to manual review.
- **The OCR confidence spread.** The floor sits at the default 60.
  §5.5 makes it a governance number that should be set from this
  estate's own documents rather than a number picked without seeing
  them. After this run there is evidence to set it from. **Learning may
  never lower it** (§14.4).
- **The dated terms** in `discovery/COMMERCIAL-EXPOSURE.md`. Expect
  dates that need acting on this month.

Then import what survives review into the class 2 registers and check
the horizon:

    python -m control registers --control-root "C:\Users\Lape Top Suez\Documents\Control"

---

## What is blocked, and on whom

None of this is code. It is why Phase 1 does not close.

| Item | Owner | Note |
|---|---|---|
| Golden set, 30–50 items | **Ahmed Diab alone** (D-03) | 3–4 hours, in batches of 10. Unanchored — Control must not show its verdict first. If a batch stalls beyond two weeks Control raises it as a deployment blocker (§13.1) |
| Usage policy circulated + 11 acknowledgements | Mohamed Ali, issued by the CEO | §12.4. Must state the D-07 extended mailbox scope explicitly (O-08) |
| PDPL lawful basis + employee notification | CEO, with Mohamed Ali | O-07. Also gates D-07 Option C |
| Retention schedule per record class | Counsel | O-10. Also gates D-07 |
| IWR amendment adopted | Mohamed Ali | O-06, against the 2025 Labour Law |
| Confidential scope confirmation | CEO | O-04. 7 of 12 clients unconfirmed; each treated as confidential meanwhile |
| Statutory calendar verified | Tax advisor — none engaged | O-03. 12 rules CEO-stated, none advisor-verified. `python -m control advisor-brief` generates the brief |
| Authority thresholds | CEO | O-02, on the D-06 interim (threshold zero, itemise everything). Review due **16-Sep-2026** |
| Five charter amendments | CEO | PR #65 |
| Graph transport | CEO/admin | D-08 permits Outlook COM in DISCOVERY and DRY_RUN only; it is **refused at startup** in SUPERVISED and LIVE |
| Backup destination | CEO | D-11, the company M365 tenant. Currently NOT CONFIGURED — the audit chain could be truncated undetectably by a hardware failure |
| Public holidays | HR | `sla.yaml` empty. Deadlines do not shift and reminders do not suppress. Must be filled before Phase 2 sends anything |

---

## Standing rules a new session must not break

Full text in `CLAUDE.md`; these are the ones a well-meaning session
breaks first.

1. **The external gate never opens** (§10). No mail to any external
   domain, in any mode. The sole exception is the §3.1 continuity CC
   under D-04, which never carries its excluded content classes.
2. **Never fabricate** (§1.1). *"A visible gap is a finding; a filled
   gap is a fabrication."* An empty result says which kind of empty it
   is.
3. **Write only inside `CONTROL_ROOT`** (§1.13). Everything else is
   read-only. Propose reorganisation; never perform it.
4. **`CLIENT_CONFIDENTIAL_PROCESSING=DISABLED`** (D-01). Contents are
   never read. D-05 and D-14 are the only exceptions and they are
   narrow: dates and durations for the class 2 registers, no clause
   text stored or quoted, nothing to any model or external service.
5. **Control may never edit `CLAUDE.md`** (§17). Amendments are
   proposed in the monthly learning report. Only Ahmed Diab amends it.
6. **Golden-set verdicts are the CEO's alone, unanchored** (D-03).
   Showing Control's verdict first produces a test the machine cannot
   fail, which is not a test.
7. **Company mail is PDPL-regulated personal data and NDA-covered
   client material.** It does not get uploaded to third-party services
   or cloud sessions. The engine goes to the data.
8. **`discovery/` is gitignored** as of 26-Aug-2026, and for a reason:
   `CONTROL_ROOT` is the repo checkout, so Phase 0 writes into a
   directory git was tracking. `file-inventory.csv` lists every path on
   the company drive; `COMMERCIAL-EXPOSURE.md` carries NDA clients'
   contract dates. Do not un-ignore it.

## Where recent work is

Branch `claude/new-session-2sqqcn`, PR #64 (draft). Pull before running
anything — Stage C carried a defect until 26-Aug-2026 that attached a
neighbouring clause's date to undated terms, which put fabricated dates
in the register that §6 tells you to act on first.
