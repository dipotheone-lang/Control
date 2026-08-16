# Statutory calendar — brief for the tax advisor

**Closes:** open decision **O-03** (charter §2.1)
**Blocks:** the Phase 0 gate, and every class 1 obligation
**Status:** `DRAFT` — to be sent to the company's tax advisor
**Prepared for:** Ahmed Diab, CEO

---

## What is being asked, and why it is asked this way

Control alerts on statutory deadlines at T−7, T−3, T−1 and again on the
morning of the deadline, escalating to the CEO on the day. Class 1 is
the only obligation class that carries fines, and it is the one class
where a wrong date is worse than no date: a system that alerts
confidently on the wrong day teaches people to trust it, and then
misses.

So the charter is strict about this at §2.1:

> Exact deadlines must be confirmed with the company's tax advisor and
> re-verified every January. **Never hardcode a statutory date from
> assumption.**

Every rule in `config/statutory-calendar.yaml` currently reads
`UNVERIFIED — CONFIRM WITH ADVISOR`. Unverified rules still alert, and
they err early. **Nothing below is a proposed answer.** Supplying a
plausible date for the advisor to correct would anchor the answer, and
the point of asking is to get the real one.

---

## What we need for each obligation

For each row: the filing deadline, the payment deadline where it
differs, the period basis (monthly, quarterly, annual), how the
deadline moves when it falls on a weekend or public holiday, and any
lead time the preparer needs before the statutory date.

That last item matters more than it looks. If a return is due on the
10th and the data cannot be closed before the 8th, the operative
deadline for the company is the 8th, and that is what the system should
alert on.

| # | Obligation | Filing deadline | Payment deadline | Period basis | Weekend/holiday rule | Internal lead time |
|---|---|---|---|---|---|---|
| 1 | VAT return and payment | | | | | |
| 2 | Withholding tax | | | | | |
| 3 | Payroll tax | | | | | |
| 4 | Social insurance contributions | | | | | |
| 5 | Social insurance headcount declarations (joiners/leavers) | | | | | |
| 6 | **ETA electronic invoicing — submission** | | | | | |
| 7 | **ETA electronic invoicing — rejection clearance window** | | | | | |
| 8 | Corporate income tax return | | | | | |
| 9 | Corporate income tax instalments | | | | | |
| 10 | Commercial register renewal | | | | | |
| 11 | Tax card renewal | | | | | |
| 12 | Industrial register renewal | | | | | |

---

## Two rows we would particularly like attention on

**ETA e-invoicing (rows 6 and 7).** Phase 0 discovery found **767
messages** from `invoicing.eta.gov.eg` in the company's mail. That
volume says the obligation is live and active, not dormant. Two
questions follow:

- What is the submission deadline, and is it per-invoice or periodic?
- **When an invoice is rejected, what is the window to correct and
  resubmit, and what happens if it closes?** A rejection clearance
  window is a deadline the company may not currently be tracking at
  all, and it is the kind that expires quietly.

**Social insurance headcount declarations (row 5).** These are
event-driven rather than calendar-driven — they run from a joiner or
leaver date. We need the number of days and the event that starts the
clock, so the system can compute the deadline when HR registers the
event rather than waiting for a fixed date that does not exist.

---

## Three questions beyond the table

1. **Anything missing?** The list comes from the charter, not from a
   review of this company's actual registrations. Are there filings
   this company owes that are not listed — industry-specific, or
   arising from its client base or contracting licences?

2. **Any deadline changing in the next 12 months?** A rule that is
   correct today and changes in March is worse than one known to be
   changing.

3. **What is the penalty for missing each one?** Not to alarm anyone —
   Control reports the consequence of a miss alongside the deadline in
   its CEO escalation, and it should state the real figure rather than
   a generic warning.

---

## What happens with the answers

They go into `config/statutory-calendar.yaml` with
`verified_by_advisor: true`, the verification date, and
`next_annual_verification` set to January.

**The learning engine may never modify a statutory deadline** (§14.2
Tier C). These dates change only when the advisor says so, and the
January re-verification is itself tracked as an obligation.

---

## Sign-off

| | Name | Date |
|---|---|---|
| Completed by | | |
| Firm | | |
| Received by | Mohamed Abdelsadiq, Acting CFO | |
| Loaded into the calendar by | | |

**O-03 closes when every row above carries a confirmed deadline and
`verified_by_advisor` is set true.**
