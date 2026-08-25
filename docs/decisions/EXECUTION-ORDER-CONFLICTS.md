# Execution order of 18-Aug-2026 — conflicts with the charter

**Raised by:** Control
**For:** Ahmed Diab, CEO — sole authority to amend the charter (§17)
**Date:** 18-Aug-2026
**Status:** open — none of these is resolvable by Control

---

## Why this document exists

The execution order says *"Where this document conflicts with anything
earlier, **this document wins.**"* Control operates on that.

But §17 says Control may propose amendments and **may never edit the
charter**, and §1.3 says a conflict is resolved by quoting the clause,
never by inventing a rule. So where the order and the charter disagree,
Control follows the order and records the disagreement here rather than
editing `CLAUDE.md` to match.

Every item below is a place where the two documents cannot both be
executed as written. None is a criticism of either. Several are
ordinary drafting collisions of the kind that happen when two documents
are maintained in parallel — but a decision register with two D-14s is
not usable as a register, which is the whole point of having one.

**Nothing here blocks steps 1 to 4 of the execution order.** Step 1 is
done; the rest can proceed while these are settled.

---

## 1. Four decision numbers carry two different decisions each

Charter Appendix B runs to **D-14**. The execution order runs to
**D-53** and its authorisation says *"Appendix B extends to D-53."*
Where the two ranges overlap, four numbers collide — the same D-number
naming two unrelated decisions.

| D | Charter v4.10, Appendix B | Execution order | Both live? |
|---|---|---|---|
| **D-10** | CEO anomaly-flag budget: 10 per week | Phase 1 limited to golden-set construction; `RUN_MODE=DISCOVERY` | Yes — unrelated subjects |
| **D-11** | Backup destination: the company M365 tenant | Data-subject contact: Mohamed Ali | Yes — unrelated subjects |
| **D-13** | Management report distribution narrowed to CEO and COO for Phase 2 | Lawful basis: consent rejected | Yes — unrelated subjects |
| **D-14** | D-05 extended to permit OCR of client-confidential contracts | Audit log 7 years, no anonymisation build | Yes — unrelated subjects |

**None of these is a substantive disagreement.** Each pair is two
decisions that happen to share a number. All eight are separately
sensible and all eight are currently in force.

**Why it cannot be left.** The charter's D-14 is load-bearing in
shipped code: it is the authority under which Control OCRs scanned
client-confidential contracts to extract guarantee expiries and claim
windows, with the OCR buffer never retained. Stage C already runs on
it. If Appendix B is extended to D-53 using the order's numbering, the
OCR permission is overwritten by a retention rule and the shipped
behaviour loses its stated authority — which under §12.1.2, where OCR
sits in the *prohibited, absolutely* list, would make it a breach
rather than an exception.

Charter D-10, D-11 and D-13 are each cited by name in running code and
in the weekly report the CEO reads.

**Proposed resolution — CEO decision required.** Renumber the execution
order's four to unused numbers (D-54 to D-57), leaving the charter's
D-01 to D-14 untouched, and append the order's remaining decisions from
D-15 upward as the order already does. This preserves every reference
in code and in issued reports. The alternative — renumbering the
charter's four — invalidates references in artefacts that have already
been sent.

---

## 2. The charter version cited does not exist

The order says *"The charter (v4.2 + §18) already exists and remains
the operating authority"* and repeats it in the footer.

The charter in the repository is **v4.10**, dated 17-Aug-2026 — one day
before the order. Versions 4.3 through 4.10 record the second-round
review findings V1–V15 and decisions D-05 through D-14, including the
OCR extension above.

**This is probably shorthand rather than an instruction to revert.**
Control has not reverted anything and is operating on v4.10. But if
v4.2 is meant literally, eight versions of resolved findings and ten
decisions would be withdrawn, and that needs saying explicitly rather
than being inferred from a version string.

**Needed:** confirmation that v4.10 is the operating authority.

---

## 3. §18 does not exist

The order references §18 four times, and three build changes depend on
it:

| Reference | Where | What it needs from §18 |
|---|---|---|
| D-53 | §2.2 | "Gap closure engine active (§18)" |
| B8 | §4 | Gap register + closure engine (§18) |
| B9 | §4 | Provenance ladder — 4 rungs, never crossing type boundaries (§18.5) |
| B10 | §4 | Coverage index split three ways, never averaged (§18.6) |

**The charter ends at §17.** There is no §18, §18.5 or §18.6 in v4.10
or in any earlier version in the repository.

B8, B9 and B10 are the three build changes with no specification
Control can read. The intent is legible from the one-line summaries and
from §6 of the order — four provenance rungs that never cross type
boundaries, a coverage index split three ways rather than averaged, a
gap register typed per item — but building from a one-line summary is
inventing a rule, which §1.3 forbids.

**Needed:** §18 as text, or agreement that Control drafts it as a
proposal for CEO approval before B8–B10 are built. Control can draft
it; it cannot adopt its own draft.

---

## 4. M2, M4 and M5 are named but never defined

D-52 accepts the legal risk *"subject to mitigations M1–M5"*, and step
9 says *"M1–M5 apply throughout."*

The order defines:

- **M1** — Phase 2 on `control@` only (§3.1), with its accepted costs
  itemised. Control has implemented this.
- **M3** — the usage policy keeps its eleven signatures (§3.3).

**M2, M4 and M5 appear nowhere.** Control cannot apply a mitigation it
cannot read, and D-52's acceptance of legal risk is expressly
conditional on all five.

**Needed:** the text of M2, M4 and M5.

---

## 5. D-52 versus charter §12

Charter §12 opens: *"Phase 2 does not begin until every item is closed.
The learning engine may never modify this section."* Its items include
O-06 (IWR), O-07 (PDPL basis), O-08 (usage policy) and O-10 (retention)
— all four requiring confirmation **with counsel**.

Order D-52: *"Phase 2 proceeds on CEO-stated legal positions."* §6
records **no counsel engaged** and instructs that legal coverage *"will
read 0% and must stay visible at 0%. That is D-52 working, not
failing."*

**These cannot both be executed.** The order wins, and Control is
building to it: the coverage index will report legal coverage at 0%
rather than treating CEO-stated positions as closure, and the counsel
questions stay open in the gap register.

**But the charter still says otherwise in its own text**, and §5.6
halts at startup on a state the charter does not permit. Two consequences:

1. The §16 phase gates read from the charter. A Phase 2 promotion with
   §12 items open is, as the charter is written today, an illegal state.
2. §12 is on the *never learnable* list (§14.2), so Control cannot
   reconcile it even in ADAPTIVE mode. Only the CEO can.

**Needed:** an amendment to §12 recording that Phase 2 may proceed on
CEO-stated positions under D-52, with the 18-Nov-2026 review date and
the standing 0% legal-coverage disclosure written into the section.
Without it the charter and the order give opposite answers at the
Phase 2 gate, and Control will halt at the gate rather than pass it.

---

## 6. Step 1 activates four obligations, not ten

Step 1 says: *"Statutory calendar (§2.3), retention (§2.4), all flagged
`ceo_stated`. Ten of twelve obligations activate immediately."*

The calendar is loaded. **Four obligations produce an alert:**

| Activated | Rule | Next date |
|---|---|---|
| STAT-VAT | end of the following month, −5 working days | 23-Sep-2026 |
| STAT-WHT | end of the following month | 30-Sep-2026 |
| STAT-SOCINS | day 15 | 15-Sep-2026 |
| STAT-CIT | 31 March | 31-Mar-2027 |

**Eight do not, and the reasons are not the same reason:**

| Not activated | Why | Who closes it |
|---|---|---|
| STAT-PAYROLL | quarterly dates not supplied | Hadeer |
| STAT-REG | renewal dates not supplied | Mohamed Ali, from certificates |
| STAT-LIC | renewal dates not supplied | Mohamed Ali, from certificates |
| STAT-PDPL-REGS | quarterly review date not set | CEO |
| STAT-PDPL-REG | mechanism unknown — depends on regulations that have not issued (D-40) | not closable yet |
| STAT-ETA-SUB | real-time; correctly has no deadline (B2) | build — exception detection |
| STAT-ETA-REJ | event-driven; clock starts on an ETA rejection | build — event register |
| STAT-SI-HEADCOUNT | event-driven; clock starts on a joiner or leaver | build — event register |

The last three are **not gaps in the answers**. The order is right
about all three and Control has recorded them as the order states them.
They are gaps in the machinery: an event window has no recurring date
to compute, so it needs an event register — which is B1, B2 and B4.
Until those are built, six await a fact from a named person and two
await code.

**Two of the eight are the expensive ones.** STAT-ETA-REJ is, in the
order's own words, the tightest statutory window in the system, and M1
already makes its *detection* manual because rejections arrive in
`accounts@`. Until the event register is built, its *tracking* is
manual too. That is stated in the weekly report and is not hidden.

**One near-miss, recorded because it is the failure mode this system
exists to prevent.** `"7 days from rejection"` initially parsed as day
7 of the month: an event-driven window silently became a fixed monthly
date, alerting confidently on the wrong day every month. §2.1 rates a
wrong statutory date worse than no date, and this one would have looked
completely normal in the report. It is fixed, and the test that guards
it says so in its docstring.

**No correction to the order is needed** — "activate" may well have
meant "loaded into config", which is exactly true of ten of the twelve
rows in §2.3. This entry exists so the number in the order and the
number in the report can be reconciled by anyone reading both.

---

## 7. D-32 is a rule about the register, not a row in it

§2.3 lists **Completeness — no obligations missing (D-32)** as a row in
the class 1 statutory table. It has no deadline, no owner and no
cadence, so it cannot be a tracked obligation; a row like that would
either never alert or alert every day on nothing.

Control has implemented it as what it appears to be — a standing
property of the register — rather than as a thirteenth obligation. It
is already load-bearing: the test asserting §2.1's list is complete is
what recovered `STAT-LIC` after an earlier rewrite of the calendar file
dropped it silently, along with the owner and preparer on every row.

**Recorded, not queried.** If D-32 was meant as a trackable obligation
with its own review cadence, say so and it becomes one.

---

## 8. Charter decisions the order does not mention

These are live in the charter and untouched by the order. Listed so
that "supersedes all prior instruction on open items" does not silently
retire them.

| D | Decision | Live consequence |
|---|---|---|
| **D-06** | Authority thresholds: interim itemise-everything, **review due 16-Sep-2026** | Every commitment is itemised weekly until thresholds are set. The review date is four weeks away and is not in the order's §6 open list |
| **D-12** | Draft release: CEO, with the COO deputising during registered absence | Without it, class 3 escalations stop moving whenever the CEO travels |
| **D-04** | Continuity CC content exclusions — never carries `SUSPECTED_FRAUD`, S1–S4 flags, SOD itemisations or confidential-client content | Order D-09 retains the CC but does not restate the exclusions. Control continues to apply them |

**D-04 is the one worth a second look.** Order step 6 clears the launch
announcement for both addresses in CC "as standard procedure". That is
consistent with D-04 — an announcement carries none of the excluded
content classes. Control raises it only because "as standard procedure"
reads as a general permission, and the exclusions are what keep the
single external-gate exception narrow.

---

## 9. The authorisation block is unsigned

§8's signature table is blank in the copy Control holds.

Control is proceeding on the order as instructed — it came from the CEO
directly, and treating it otherwise would be pedantry that stops work.
This is recorded only because §10 requires every approval to be logged
with its authentication, and "unsigned copy, received directly from the
CEO on 18-Aug-2026" is what the log will say unless a signed copy
replaces it.

---

## 10. What this changes about the counsel pack

Not a conflict — a consequence, recorded here because it changes what
gets sent.

§2.4 and §2.5 of the order answer most of the questions the governance
pack was drafted to ask. Retention periods, lawful basis, the DSR
window, the notification method, the registration position, the
data-subject contact — all now have CEO-stated answers where the drafts
said `TO BE CONFIRMED`.

The pack should therefore go out as **"confirm or correct these
positions"** rather than **"please supply these"**. That is a materially
better instruction: it is faster to review, and per D-52 the positions
are already operative, so counsel is being asked to check a live
position rather than to design one.

The same applies to step 5: the advisor brief sends the **completed**
statutory table for correction, not blank rows.

**The `TO BE CONFIRMED` markers do not all clear.** A CEO-stated
position is `ceo_stated`, not `verified_by_advisor` — §7 of the order
makes promoting one without a named human a stop condition. The drafts
will say which positions are CEO-stated and which are still unanswered
by anyone, because those are different things and merging them would
lose exactly the distinction D-52 depends on.

---

## Summary — what Control needs

| # | Needed | From | Blocks |
|---|---|---|---|
| 1 | Renumber the four colliding D-numbers | CEO | Appendix B is not a usable register until then |
| 2 | Confirm v4.10 is the operating authority | CEO | nothing — Control is on v4.10 |
| 3 | §18 text, or approval of a Control-drafted proposal | CEO | B8, B9, B10 |
| 4 | Text of M2, M4, M5 | CEO | D-52's risk acceptance is conditional on them |
| 5 | §12 amendment recording D-52 | CEO | the Phase 2 gate — Control halts there as written |
| 6–9 | Noted; no action required unless the reading is wrong | — | — |
| 10 | Reframe the counsel pack as confirm-or-correct | Control | in hand |

Items 1 to 5 are CEO decisions. Control has not acted on any of them
and will not.
