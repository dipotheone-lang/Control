# Control — the runbook

Everything you need to run, in order, from a machine with nothing on it.

Runs on your laptop against `E:\UBCSIS Co Date Jan 2026`. **Nothing in
this document sends mail.** Nothing writes outside `CONTROL_ROOT`.

**Start with §3 if you only have twenty minutes.** It is the one whose
output can matter before the system is even finished.

---

## 1. Setup — once per machine

### 1.1 Prerequisites

| | |
|---|---|
| Python 3.11 or later | `python --version` |
| Git | `git --version` |
| Outlook, signed in, running | The mailboxes must be in the profile |
| `E:\UBCSIS Co Date Jan 2026` reachable | Startup halts if it is not |

### 1.2 One command

```powershell
git clone https://github.com/dipotheone-lang/Control.git
cd Control
.\scripts\setup-laptop.ps1
```

That installs dependencies including `pywin32`, creates `CONTROL_ROOT`
from the config templates, sets `CONTROL_ROOT` and `UB_ROOT` for your
user, initialises the database and audit chain, and reports readiness.

Different drive? `.\scripts\setup-laptop.ps1 -UbRoot "D:\Company"`

### 1.3 Confirm

```powershell
python -m control doctor
```

Must print **READY**. If it does not, §9 below has the failure you are
looking at.

### 1.4 Every later session

```powershell
cd Control
git pull
pip install -e .
```

If `doctor` then reports missing config files, run
`python -m control init` — the config set grows as decisions are taken,
and startup halts on a missing file rather than assuming a default.

---

## 2. Turn on the backup — before anything writes

```powershell
python -m control backup --init-key
```

**Write the key down somewhere off this laptop, now.** A key that
exists only on the machine the backup protects against is not a key.
Without it nobody can restore the archives — including you.

```powershell
python -m control backup
python -m control backup --test
```

The destination resolves from OneDrive automatically (decision D-11).
`--test` restores a real archive and re-verifies the database and the
audit chain, because an untested backup is a hope rather than a
control.

Why first: §5.2 requires the backup before the first write. A hash
chain that is not backed up can be truncated undetectably by a dead
laptop, and the chain is what proves the record was never altered.

---

## 3. Commercial exposure — the one that matters

```powershell
python -m control contracts
```

Walks the whole of `UB_ROOT` — not a folder someone remembered — and
writes `%CONTROL_ROOT%\discovery\COMMERCIAL-EXPOSURE.md`: every
guarantee expiry, claim window, retention release, LD term and
accreditation date found, sorted by urgency.

**Read the nearest five dates before anything else in this repository.**
§6 says this output will likely contain dates needing action before the
system is built. A guarantee expiring in three weeks is worth more than
everything else here put together.

Expect it to take a while on a full drive.

**Confidential contracts.** Control does not open them by default —
decision D-01. To extract dates and term durations only, under the D-05
exception:

```powershell
python -m control contracts --confidential-dates
```

No clause text is stored either way. The redaction happens at capture,
not at rendering, so it cannot leak through a later template change.

### 3.1 OCR — for the scans

The first live scan found **zero** dates across 362 legal documents:
47% of them are photographs of text, 81% for supplier legal documents.
Guarantee expiries and claim windows are in there; nothing could read
them.

OCR needs an engine, and it is not bundled:

```powershell
winget install UB-Mannheim.TesseractOCR
```

During that installer, tick **Additional language data** and include
**Arabic**. Then:

```powershell
pip install pytesseract pillow pymupdf
python -m control doctor
```

`doctor` now has an OCR section naming exactly what is missing. When it
reports the engine, PDF rendering and Arabic data all present, set
`enabled: true` in `%CONTROL_ROOT%\config\ocr.yaml` and re-run:

```powershell
python -m control contracts --ocr --confidential-dates
```

**Readings below the confidence floor are discarded, not used.** §5.5:
a wrong number in a register is worse than no number, and on a scanned
Arabic contract a permissive floor produces plausible dates that are
wrong. The run reports three separate counts — accepted, below floor,
and engine failed — because "the reading was not trustworthy" and
"nothing looked at it" are different problems with different fixes.

---

## 4. The manuals

```powershell
python -m control manuals
```

Writes `MANUAL-INVENTORY.md` with tick boxes. Nothing is treated as
authoritative until you tick it: a document with "manual" in its name
is a candidate, and check C6 depends on the difference. Until manuals
are confirmed, C6 honestly returns `NOT ASSESSED` rather than
`CONFORMS`.

Read any **AMBIGUOUS — CEO DECISION** section first — those are
documents that look like the same manual at different revisions.
Evaluating a submission against the wrong revision produces a
confident, wrong verdict.

The charter says twelve manuals exist. If fewer are found, the report
asks which it is — named differently, unreadable, or not written —
because that changes what a verdict can honestly claim.

---

## 5. The mailbox scan

```powershell
python -m control phase0 --folders "Inbox,Sent Items" --recurse
```

Metadata only. No message body is read. HR subject lines are redacted
at capture.

**Sent Items matters.** Three earlier runs silently found none — Gmail
nests it under `[Gmail]/Sent Mail` and the exact string never matched.
Folder matching now reports **NOT FOUND** with the folders it actually
saw. This run is what makes Stage H's unanswered counts trustworthy;
without Sent Items, "no reply found" only meant "I cannot see replies".

Then:

```powershell
python -m control analyse
```

Writes the Stage D cadence analysis — the candidate obligations — and
Stage H response times, per mailbox.

---

## 6. The two worksheets you fill in

### 6.1 Domains — decision O-04

```powershell
python -m control classify
```

`DOMAIN-CLASSIFICATION.csv`: every external domain with volume,
inbound/outbound split, attachment count, date range and which
mailboxes saw it. Fill `YOUR_DECISION` with `CONFIDENTIAL` or
`NOT_CONFIDENTIAL`, then:

```powershell
python -m control classify --apply "%CONTROL_ROOT%\discovery\DOMAIN-CLASSIFICATION.csv"
```

Do it in passes if you like. **Blank rows stay confidential** — silence
is never read as approval. A typo stops the whole apply and names the
line rather than guessing what you meant.

**It has a second job.** The near-miss fraud signal compares incoming
senders against every domain you have classified, in either direction.
Until this is filled, that signal only protects the handful of client
domains already on file — and the spoofed *supplier* invoice is the
fraud that actually happens.

### 6.2 Accreditations

```powershell
python -m control registers --import-file config\accreditations-seed.yaml
python -m control registers
```

Twelve clients go on the register with `status: UNKNOWN` and no expiry.
That is deliberate: they appear under **ON THE REGISTER, ALERTING ON
NOTHING** with a named owner, instead of being invisible. An undated
row and an empty register produce the same silent horizon, and §2.2
says a lapsed prequalification looks exactly like silence.

KNAUF, Canal Sugar, Sukari and Air Liquide carry `CHECK FIRST` —
they barely appear in the scanned mail.

---

## 7. The dry run — Phase 1

```powershell
$env:RUN_MODE = "DRY_RUN"
$env:LEARNING_MODE = "OBSERVE"
python -m control cycle
```

**This sends nothing.** Everything is evaluated; everything is drafted
into `%CONTROL_ROOT%\outbox\pending-approval\`.

Run it *before* the obligation register is approved. It will track
almost nothing and print a list of gaps — each line something Control
is deliberately **not** doing, and why:

```
GAPS — 12. Each is a thing Control is NOT doing:
  - obligations.yaml is empty. The register is populated from Phase 0
    Stage D and approved by the CEO — that approval is what ends Phase 0.
  - statutory-calendar.yaml: verified_by_advisor is false (O-03)...
    class 1 — the only class carrying fines — is tracking nothing.
  - STAT-ETA-SUB: due expression 'UNVERIFIED — CONFIRM WITH ADVISOR'
    not understood — no class 1 alert can fire (O-03)
```

Seeing that once is worth more than any description of it. The list
shrinks as answers arrive, and it is what stops a green dashboard from
lying to you.

Reset to Phase 0 defaults afterwards:

```powershell
Remove-Item Env:RUN_MODE, Env:LEARNING_MODE
```

---

## 8. Checking the system itself

```powershell
python -m control verify        # DB integrity + audit hash chain
python -m control doctor        # this machine can still run Control
python -m control backup --test # restore actually works
```

A hash-chain break is a critical incident (§13.3), not a warning.

---

## 9. When something fails

| What you see | What it is |
|---|---|
| `HALT: required config missing` | Config set grew. `python -m control init` |
| `HALT: UB_ROOT unreachable` | Drive not mounted. Control never operates on a partial view |
| `HALT: transport route 'outlook_com' is not permitted in RUN_MODE=SUPERVISED` | D-08 working. Phase 2 needs Graph; Outlook cannot hold a schedule |
| `HALT: mailbox-scope.yaml: state is LIVE with open preconditions` | Someone set the scope live before O-07/O-08/O-10 closed. Control will not widen its own reach |
| `backup encryption key not available` | Run `backup --init-key`. Control never writes an unencrypted backup to a synced folder |
| `Outlook not available: pywin32 is required` | `pip install pywin32`, Windows only |
| `claude` or `python` not found after install | The shell predates the PATH change. Open a new terminal |
| Scan stops partway | Per-item failures are counted, not fatal. Check the `unreadable` count in the summary |
| `.ost` locked | Close Outlook, or read a copy. Never parse the live file |
| A mailbox is skipped | It is not in the Outlook profile. Recorded as a gap, other mailboxes continue |

**Anything unexpected: send me the output verbatim.** Do not paste
message contents — the errors never contain them, and they should not
start now.

---

## 10. What to send back

1. `COMMERCIAL-EXPOSURE.md` — or just the nearest five dates
2. `MANUAL-INVENTORY.md` with the governing manuals ticked
3. `DOMAIN-CLASSIFICATION.csv` with decisions filled in
4. The `STAGE-D-*.md` files — we go through them together to approve
   the obligation register, which is what ends Phase 0
5. Anything that errored, verbatim

---

## 11. What is blocked, and on whom

| Blocked | On | Document |
|---|---|---|
| O-03 statutory calendar | Tax advisor | `docs/governance/TAX-ADVISOR-BRIEF.md` |
| O-06 IWR amendment | Counsel | `docs/governance/IWR-AMENDMENT.md` |
| **O-07 PDPL basis** | Counsel, then your notification | `docs/governance/PDPL-BASIS.md` |
| **O-08 usage policy** | You circulate, everyone signs | `docs/governance/USAGE-POLICY.md` |
| **O-10 retention schedule** | Counsel | `docs/governance/RETENTION-SCHEDULE.md` |
| Holiday calendar | HR — Mohamed Ali | `config/sla.yaml` |
| Obligation register | You, after §5 | `config/obligations.yaml` |
| Golden set | You, 10 items a week | `docs/GOLDEN-SET-PLAN.md` |
| Graph provisioning | Tenant admin sign-in | `scripts/provision-graph.ps1` |

The three in bold also gate the D-07 mailbox scope. Until all three
close, Control reads `control@` only and says so in every report.

**Counsel is the critical path.** Everything else can be done in a day;
that cannot, and Phase 2 cannot start without it.

---

## 12. Command reference

| Command | What it does |
|---|---|
| `doctor` | Can this machine run Control |
| `init` | Create `CONTROL_ROOT` from the config templates |
| `verify` | DB integrity and audit hash chain |
| `backup` | Encrypted backup; `--init-key`, `--test`, `--restore` |
| `contracts` | Stage C — commercial terms and dates from documents |
| `manuals` | Stage C — governing manuals, for confirmation |
| `phase0` | Scan every mailbox, analyse, write the deliverables |
| `outlook-scan` | One named mailbox, for a targeted re-run |
| `analyse` | Stage D cadence and Stage H response times |
| `classify` | O-04 domain worksheet; `--apply` to read it back |
| `registers` | Class 2 registers — import rows, show the horizon |
| `cycle` | One sweep: fetch, classify, evaluate, enforce, gate |
| `startup` | The §5.6 sequence alone, to check state |
| `discovery` | Stages A–B against `UB_ROOT` |

Every command takes `--control-root` and most take `--ub-root`; both
default to the environment variables `setup-laptop.ps1` set, so you
should not need to type either.
