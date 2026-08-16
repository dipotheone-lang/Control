# Run this today — the Phase 0 commands, in order

Everything below runs on your laptop against `E:\UBCSIS Co Date Jan 2026`.
Nothing sends mail. Nothing writes outside `CONTROL_ROOT`.

**Why today.** §6 says to read `COMMERCIAL-EXPOSURE.md` first because it
will likely contain dates needing action before the system is even
built. If there is a guarantee expiring in three weeks sitting in a
folder, finding it now is worth more than everything else built so far.
Every other output can wait; that one cannot.

---

## 0. Get the latest code

```
cd %CONTROL_REPO%
git pull
pip install -e .
python -m control doctor --control-root "%CONTROL_ROOT%"
```

`doctor` must print **READY**. If it reports missing config files, run
`python -m control init --control-root "%CONTROL_ROOT%"` — four new
config files landed this session (`mailbox-scope`, `transport`,
`backup`, `continuity`) and startup halts without them by design.

---

## 1. The one that matters — commercial exposure

```
python -m control contracts --control-root "%CONTROL_ROOT%"
```

`--source` now defaults to `UB_ROOT`, so this walks the whole drive
rather than folders someone remembered. Expect it to take a while.

Then open `%CONTROL_ROOT%\discovery\COMMERCIAL-EXPOSURE.md` and read the
nearest dates first.

**On confidential contracts.** By default Control does not open them —
D-01. To extract dates and term durations only, under the D-05
exception, add `--confidential-dates`. No clause text is stored either
way; the redaction happens at capture, not at rendering.

---

## 2. The manuals

```
python -m control manuals --control-root "%CONTROL_ROOT%"
```

Writes `MANUAL-INVENTORY.md` with tick boxes. Nothing is treated as
authoritative until you tick it. Check C6 — manual conformance — cannot
return `CONFORMS` for anything until this is done, and until then it
honestly returns `NOT ASSESSED`.

Look especially at any **AMBIGUOUS — CEO DECISION** section: those are
documents that look like the same manual at different revisions.
Evaluating a submission against the wrong revision produces a
confident, wrong verdict.

---

## 3. The mailbox scan, with Sent Items

```
python -m control phase0 --control-root "%CONTROL_ROOT%" ^
    --folders "Inbox,Sent Items" --recurse
```

Folder matching was fixed after three earlier runs silently found no
Sent Items — Gmail nests it under `[Gmail]/Sent Mail` and the exact
string never matched. It now reports **NOT FOUND** with the folders it
actually saw, so a miss is visible.

This run makes Stage H's unanswered counts trustworthy for the first
time. Without Sent Items, "no reply found" meant "I cannot see replies".

---

## 4. The domain worksheet — decision O-04

```
python -m control classify --control-root "%CONTROL_ROOT%"
```

Writes `DOMAIN-CLASSIFICATION.csv`: every external domain with volume,
inbound/outbound split, attachments, date range and which mailboxes saw
it. Fill the `YOUR_DECISION` column with `CONFIDENTIAL` or
`NOT_CONFIDENTIAL`, then:

```
python -m control classify --control-root "%CONTROL_ROOT%" ^
    --apply "%CONTROL_ROOT%\discovery\DOMAIN-CLASSIFICATION.csv"
```

You can do it in passes. Blank rows stay confidential — silence is
never read as approval. A typo stops the whole apply and names the line.

**This one has a second job.** The near-miss fraud signal compares
incoming senders against every domain you have classified, in either
direction. Until the worksheet is filled, that signal only protects the
handful of client domains already on file — and the spoofed *supplier*
invoice is the fraud that actually happens.

---

## 5. Seed the accreditation register

```
python -m control registers --control-root "%CONTROL_ROOT%" ^
    --import-file config\accreditations-seed.yaml
python -m control registers --control-root "%CONTROL_ROOT%"
```

Twelve clients go on the register with `status: UNKNOWN` and no expiry
date. That is the point: they appear under **ON THE REGISTER, ALERTING
ON NOTHING**, with a named owner, instead of being invisible.

Four of them — KNAUF, Canal Sugar, Sukari, Air Liquide — carry
`CHECK FIRST`, because they barely appear in the scanned mail and §2.2
says a lapsed prequalification looks exactly like silence.

---

## 6. Turn on the backup

```
python -m control backup --control-root "%CONTROL_ROOT%" --init-key
```

**Write the key down somewhere off that laptop, immediately.** A key
that exists only on the machine the backup protects against is not a
key. Then:

```
python -m control backup --control-root "%CONTROL_ROOT%"
python -m control backup --control-root "%CONTROL_ROOT%" --test
```

The destination resolves from OneDrive automatically. `--test` restores
a real archive and re-verifies the database and the audit chain, because
an untested backup is a hope rather than a control.

---

## 7. A dry run — the first time the engine actually runs

```
set RUN_MODE=DRY_RUN
set LEARNING_MODE=OBSERVE
python -m control cycle --control-root "%CONTROL_ROOT%" --ub-root "%UB_ROOT%"
```

**This sends nothing.** DRY_RUN is Phase 1: everything is evaluated,
everything is drafted into `outbox\pending-approval\`, nothing leaves.

Expect it to report a long list of gaps and track almost nothing. That
is correct today — the obligation register is empty until you approve
it, and every statutory rule is unverified until the advisor answers.
The list is the point: each line is something Control is deliberately
**not** doing, with the reason.

Run it before the register is approved so you can see what the gap list
looks like when it is honest. It gets shorter as the answers come in.

## What to send back

1. `COMMERCIAL-EXPOSURE.md` — or just the nearest five dates
2. `MANUAL-INVENTORY.md` with the governing manuals ticked
3. `DOMAIN-CLASSIFICATION.csv` with decisions filled in
4. Anything that errored, verbatim

## What is still blocked, and on whom

| Blocked | On |
|---|---|
| O-03 statutory calendar | Tax advisor — `docs/governance/TAX-ADVISOR-BRIEF.md` |
| O-06 IWR amendment | Counsel |
| O-07 PDPL basis | Counsel, then your notification |
| O-08 usage policy | You circulate, everyone signs |
| O-10 retention schedule | Counsel |
| Holiday calendar | HR — Mohamed Ali |
| Obligation register approval | You, after the scan |
| Golden set | You, batches of 10 weekly |

O-07, O-08 and O-10 also gate the D-07 mailbox scope. Until all three
close, Control reads `control@` only and says so in every report.
