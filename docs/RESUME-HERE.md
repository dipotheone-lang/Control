# RESUME HERE — state as at 30-Aug-2026

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

Environment as at 30-Aug-2026: Windows 11, Python 3.13.14, Tesseract
5.4.0 with `ara`/`eng`/`osd` at `C:\Program Files\Tesseract-OCR`
(off PATH — `control.ocr` locates it without trusting PATH), tessdata at
`C:\Users\Lape Top Suez\AppData\Local\tessdata`. `doctor` reports all
five Python dependencies present, and now also connects to Outlook and
names the mailboxes the profile exposes — the previous check confirmed a
Python package was installed, which is a different fact.

**Classic Outlook is required.** The "new Outlook" app has no COM
interface at all; `File → Options` is the tell. D-08 permits this route
in DISCOVERY and DRY_RUN only, and refuses it at startup in SUPERVISED
and LIVE, because a transport needing a powered laptop with Outlook open
cannot hold a Phase 2 schedule.

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
  The block is the golden set, and it was misattributed until 30-Aug:
  the gate named the CEO's time when nothing in the system had ever
  built a pending case to judge. `golden --build` is that step. His time
  becomes the constraint at `--issue`, not before.

---

## The next action — one command

Everything a machine can do now runs in one command. Open classic
Outlook and leave it signed in, then:

    python -m control phase1 --control-root "C:\Users\Lape Top Suez\Documents\Control" --ub-root "E:\UBCSIS Co Date Jan 2026" --ocr

Nine steps: config, mailbox scan, Stage D register proposal, extraction
brief, advisor brief, **Stage C contracts**, **golden-set cases**, a full
DRY_RUN cycle, the weekly report, the gap register, and the gate. Each is
skipped rather than fatal when its input is absent, and the summary says
which. It ends by printing the gate, which names every open item and the
one person who can close it.

### The commands worth knowing separately

| Command | What it answers |
|---|---|
| `doctor` | Is this machine ready — and **does Outlook actually answer**, with which mailboxes in the profile |
| `contracts --ocr --confidential-dates` | Guarantee expiries, notice periods, accreditations → `COMMERCIAL-EXPOSURE.md` and `PROPOSED-CLASS2-REGISTERS.yaml` |
| `registers --import-file` | Turns those proposals into rows that actually alert (60/30/14/7 days) |
| `diagnose-dates` | Why terms carry no date — runs off cached text, seconds not hours |
| `golden --build` then `--issue` | Pending cases from the archive, then a batch of 10 for the CEO |
| `authority --source ".../13. Delegations"` | Candidate delegated limits for the O-02 review |
| `gate` | The two gates, measured, with owners |

## What Stage C found, and the shape of it

957 documents scanned. **The finding is about the estate, not the
extractor**, and it took four fixes and three measurements to establish:

- `14. Construction Management Files` is 801 of the 957 and produced 525
  terms with **one usable date** — project files and blank templates
  naming a retention because the boilerplate does, with no date because
  nothing has been agreed. It is excluded from the runner's Stage C scope
  for that reason.
- **424 of 524 terms sit in documents with no date anywhere.** No
  clause-window change can ever date those.
- The **client-confidential contracts are the opposite case**: 11 in the
  legal folders produced 29 terms and 47 readable dates and paired none
  of them. The dates parse and the terms are found; only the width
  between them is left. `diagnose-dates` now reports that distance in
  buckets so the window is set from the number rather than guessed —
  three guesses have already been wrong.
- OCR: 92 of 157 trusted, 55 below the §5.5 floor, confidence 30.7 to
  94.6 with a median of 71.4. **The floor sits at the default 60 and is
  a decision waiting** — §5.5 makes it a governance number to be set from
  this estate's own distribution, and §14.4 forbids learning from
  lowering it.

## What is blocked, and on whom

None of this is code. It is why Phase 1 does not close.

| Item | Owner | Note |
|---|---|---|
| Golden set | **A decision, not 3–4 hours** | Nothing built pending cases until 30-Aug; `golden --build` does. But Stage D found LIVE 0, so a case today exercises **C1 only** — no controlled form for C2, no clause for C6, no field mapping for C3/C4/C5/C7. A set that tests C1 alone passes a gate counting false positives per check without testing what the gate is for. **Register the layouts in use as controlled forms, or build the set from live Phase 1 submissions.** Then D-03: CEO alone, unanchored, batches of 10 |
| Usage policy circulated + 11 acknowledgements | Mohamed Ali, issued by the CEO | §12.4. Must state the D-07 extended mailbox scope explicitly (O-08) |
| PDPL lawful basis + employee notification | CEO, with Mohamed Ali | O-07. Also gates D-07 Option C |
| Retention schedule per record class | Counsel | O-10. Also gates D-07 |
| IWR amendment adopted | Mohamed Ali | O-06, against the 2025 Labour Law |
| Confidential scope confirmation | CEO | O-04. 7 of 12 clients unconfirmed; each treated as confidential meanwhile |
| Statutory calendar verified | Tax advisor — none engaged | O-03. 12 rules CEO-stated, none advisor-verified. `python -m control advisor-brief` generates the brief |
| Authority thresholds | CEO | O-02, review due **16-Sep-2026**. D-06's interim was to observe a month of commitment volume; Phase 0 recorded none, so the review would arrive with the evidence it started with. `control authority` reads candidate limits out of `13. Delegations` instead. §14.2 Tier C — it proposes, never applies, and never names a holder |
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
anything.

Stage C carried four defects between 26 and 30-Aug, each of which put
wrong dates or missing guarantees into the file §6 says to act on first:
a date borrowed from the neighbouring clause; a line wrap read as a
clause end, which severed 468 of 470 terms from their dates; a cache
keyed on the wrong rules, which served 957 documents from a superseded
engine; and two date formats this estate writes — `31.12.2027` and
`2026/11/30` — that no pattern parsed. All fixed, all with regression
tests over line-wrapped text, because every contract in the old suite
was written one tidy sentence per line and real documents are not.
