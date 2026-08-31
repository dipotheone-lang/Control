# RESUME HERE — state as at 30-Aug-2026

> **The project was narrowed on 30-Aug-2026. Decision D-15, in the charter since 4.11:
> Control operates on class 1 statutory obligations alone and reads no
> mailbox.** Read `docs/decisions/D15-STATUTORY-ONLY.md` before anything
> else here — most of what follows describes capabilities that are built,
> tested, and now out of scope. Nothing is deleted; widening means closing
> the §12 pre-conditions and moving the scope back.
>
> **It is running now.** Double-click `Run Control.cmd` — the statutory
> horizon, on screen in seconds, no mailbox and no Outlook. That is the
> narrowed scope's whole operating output and it needs nothing from
> anybody first.
>
> **It also sends now.** Decision D-58 (30-Aug-2026) ended the wait for
> Graph: class 1 alerts go out through classic Outlook on this laptop.
> The cost is written into the decision — a transport needing a powered
> machine cannot hold a schedule, so on the day a filing falls due with
> the laptop asleep, nobody is told. It is mitigated, not solved: an
> alert that cannot leave is written `UNDELIVERED`, never marked sent,
> and **retried on the next run**, so missing T−7 does not silence T−3,
> T−1 and the day itself.
>
> **What still separates this from a verified system is not code:** O-03,
> the tax advisor confirming the thirteen rules.
> `discovery/TAX-ADVISOR-BRIEF.md` is generated and waiting. The dates
> alert today and say `[UNVERIFIED]` on every line, which is §2.1's
> chartered behaviour — erring early beats silence. Nobody qualified has
> checked them, and time passing does not check them.

## LAUNCHED — 31-Aug-2026

The system is running. What was done, so nobody repeats it:

| | |
|---|---|
| Repository | Up to date. The branch had been tracking `origin/claude/reconcile` and sat 28 commits behind for days while reporting "Already up to date" |
| Config | Every decision adopted into `CONTROL_ROOT`. `doctor` reports nothing differing |
| Class 1 register | **13 rules, 7 counting down, 6 silent.** Payroll split, withholding lead, PDPL anchor all live |
| Backup | OneDrive, encrypted. **Restore test PASS on 31-Aug-2026** — 2,428 files, database OK, hash chain intact across 309 entries |
| Transport | Outlook on this machine (D-58). `control@ubcsis.com` confirmed present among the profile's 18 stores |
| Daily run | `Run Control.cmd` — three steps, seconds, writes three pages to `reports\` |

**The next date that matters is 8 September.** Social insurance reaches
T−7 and the chain gets its first live test: either Outlook sends, or the
alert is written `UNDELIVERED` and retried. Either way the run says
which. Nothing fires before then.

### What is left, and none of it is code

Closed on 31-Aug-2026, evening: the OneDrive online recycle bin was
emptied of the four purged archives, so the D-61 deletion is complete —
the discovery data now exists nowhere. The 07:00 scheduled task is
registered with catch-up. The backup key was rotated after appearing in
a screenshot, the restore test passed under the new key (2,371 files,
chain intact at 328 entries), and the CEO confirmed the new key is
written down off the laptop.

| Item | Who | Effect |
|---|---|---|
| Forward `reports\statutory-ask-*.txt` | you | One ready bilingual message, to Mohamed Ali. His answer on STAT-REG and STAT-LIC takes coverage 7 of 13 → 9 of 13. D-59 closed the rows Hadeer held |
| Verify the 13 rules | a tax advisor — none engaged | O-03. Removes `[UNVERIFIED]` from every line. The two payroll rows first: a wrong monthly date fires twelve wrong alerts a year |
| The Gmail continuity CC | you | D-04. Goes from draft to real traffic on 8 September. Leave, narrow, or replace |
| Business OneDrive for ubcsis.com | admin | Returns the backup to D-11 as written. The personal account is an accepted interim (D-60) |
| `united_brothers_outreach` | — | A weekly job on this laptop, outside this repository, sending from the continuity Gmail. The CEO instructed on 31-Aug-2026 that it be ignored; recorded here so the instruction is visible rather than the job forgotten |

### Defects found on the day, all fixed

Recorded because each was invisible in a different way, and the pattern
is the point: **every one of them looked like success.**

- A branch tracking the wrong remote — "Already up to date" for 28 commits
- A parenthesis in an `echo` inside an `if` block — the script printed the
  horizon, died on `. was unexpected at this time.`, and the cycle,
  the missing-dates page and the requests never ran
- An `UNDELIVERED` alert counted as a duplicate — a closed laptop on T−7
  would have silenced T−3, T−1 and the deadline itself
- A closed Outlook aborting the whole run instead of retrying
- Drift blind to nested mappings — D-13's narrowing was in the template,
  not in force, and the report said "nothing differing"
- Drift offering to erase the restore test it had just recorded
- `E:` recorded as surviving the laptop; it is a partition of the same
  physical disk (D-60 withdraws the claim)

---

`docs/RUNBOOK.md` says how to run each thing. This file says **where the
build actually is and what the next action is**, so a new session — a
new PowerShell window or a new Claude Code session — can pick up without
rediscovering it.

`CLAUDE.md` is the authority. Nothing in this file overrides it.

---

## THREE paths, not two — corrected 31-Aug-2026

| | |
|---|---|
| **repository** | `C:\Users\Lape Top Suez\Documents\Control` — where `git pull` lands |
| **`CONTROL_ROOT`** | `C:\Users\Lape Top Suez\Documents\UnitedBrothers\CONTROL` — what Control actually reads and writes |
| **`UB_ROOT`** | `E:\UBCSIS Co Date Jan 2026` |

**This file said for days that CONTROL_ROOT was the repo checkout. It is
not**, and the error was expensive in exactly the way §1.1 warns about:
a wrong fact that nothing contradicted. It surfaced only when a runner
printed both paths side by side on 31-Aug-2026.

**The consequence, which is the thing to remember:** `git pull` updates
the repository's `config/`. Control reads the *other* `config/`. A
decision committed here does not reach the running system until it is
adopted — `python -m control doctor` reports the distance and
`python -m control init --adopt` closes what it safely can.

`E:\UBCSIS Co Date Jan 2026\CONTROL` still does not exist, so §5.1's
`CONTROL_ROOT=<UB_ROOT>/CONTROL` is still not what the machine does.
That divergence is recorded rather than fixed — moving it is a decision,
not a cleanup, and it affects where D-11 backups land. Do not "correct"
it silently.

The separation is, on balance, right: Phase 0 output and daily reports
land outside git, which is what the `discovery/` and `reports/` ignore
rules exist to guarantee even if this ever changes back.

Environment as at 30-Aug-2026: Windows 11, Python 3.13.14, Tesseract
5.4.0 with `ara`/`eng`/`osd` at `C:\Program Files\Tesseract-OCR`
(off PATH — `control.ocr` locates it without trusting PATH), tessdata at
`C:\Users\Lape Top Suez\AppData\Local\tessdata`. `doctor` reports all
five Python dependencies present, and now also connects to Outlook and
names the mailboxes the profile exposes — the previous check confirmed a
Python package was installed, which is a different fact.

**Classic Outlook is required.** The "new Outlook" app has no COM
interface at all; `File → Options` is the tell. D-08 permitted this route
in DISCOVERY and DRY_RUN only — **superseded by D-58 (30-Aug-2026)**,
which lets Outlook carry the class 1 alerts under `STATUTORY_ONLY`
because that scope fetches nothing. The permission is conditional on the
scope, not the run mode: `OPERATING_SCOPE=FULL` in SUPERVISED still
halts on the route exactly as D-08 wrote it.

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

## The next action — double-click, no terminal

Double-click **`Run Control.cmd`** in the repository folder. It reads
`config/statutory-calendar.yaml` and nothing else — no mailbox, no drive
scan, no OCR — so Outlook can be closed and E: unplugged, and it takes
seconds rather than hours.

Three steps: update, the horizon, the run.

**The horizon** is the page — the class 1 deadlines for the next 30 days
in both languages, saved to `reports\statutory-YYYY-MM-DD.txt`, followed
by what the narrowed scope is *not* doing. That last part is deliberate:
a page listing two deadlines and nothing else reads like a quiet company
unless the reader is told what was never looked at.

**The run** is the record — `cycle` at SUPERVISED level 2, which is §16's
own row for D-15. The deadline engine plans the §2.1 alerts (T−7, T−3,
T−1 and the day itself), writes them, and posts to the database and the
hash-chained log.

**Nothing is sent, and the run says so.** With no transport provisioned,
an alert §10 requires to be SENT is written to
`outbox\pending-approval` marked `UNDELIVERED_NO_TRANSPORT` and reported
as `NOT DELIVERED`. That is the honest state rather than a failure of
the run — but it does mean nobody has been alerted, which is why the
line is the loudest one in the output.

Two conditions that would stop a wider run are stepped past here and
reported as `PROCEEDED PAST`: an unreachable `UB_ROOT` (nothing in this
scope reads the drive) and D-08's route gate (nothing in this scope uses
a route). Both halt again the moment the scope widens.

Once per machine first: **`First-time setup.cmd`**, which installs
dependencies, creates the database and audit chain, and sets
`CONTROL_ROOT` and `UB_ROOT` for the user.

`scripts\Install-DailyRun.cmd` registers a Windows scheduled task so the
horizon is on screen every morning by itself. **That is a habit, not a
control** — the page appears on this machine; it does not reach anybody.
D-08 refuses the Outlook route in SUPERVISED and LIVE because a
transport needing a powered laptop cannot hold a schedule, and a missed
class 1 alert is the charter's most expensive failure.

`.cmd` rather than `.ps1` on purpose — a PowerShell script can be
refused by the machine's execution policy, and a runner that needs a
policy change before it starts is not one you can hand to somebody.

Typed by hand, if a terminal is ever wanted:

    python -m control statutory

**`Run full scan.cmd`** is the previous runner, unchanged: the nine-step
`phase1 --ocr` pass over mailbox, drive and contracts. It is out of scope
under D-15 and kept because widening means closing the §12
pre-conditions, not rebuilding. Everything below this line describes that
wider system.

### The commands worth knowing separately

| Command | What it answers |
|---|---|
| `statutory` | **The one in scope.** What is due in class 1, who owns it, and what is counting down to nothing |
| `statutory --missing` | The silent class 1 rules, what each waits on, who holds it. 3 are one line in `statutory-calendar.yaml` |
| `statutory --ask` | The same gaps as forwardable bilingual messages, one per holder. Control drafts; the CEO sends (§10) |
| `status` | Where the build actually is, read off disk — absent and zero told apart on every line |
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
