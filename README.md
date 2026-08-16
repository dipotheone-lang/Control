# Control

Adaptive obligation & deadline control engine for **United Brothers Co.
(UBCSIS)** — the automated controller behind `control@ubcsis.com`.

The single source of truth is the operating charter: **[`CLAUDE.md`](CLAUDE.md)**
(v4.6). Everything in this repository implements it or feeds it. The two
review documents that shaped it are in [`docs/`](docs/).

## What this system is

Control tracks four classes of obligation — statutory filings, commercial
deadlines (tenders, claim notices, guarantees, accreditations),
operational reports, and informational items — evaluates submissions
against controlled forms, escalates misses on chartered schedules,
watches external threads for unanswered mail, and flags fraud and
anomaly signals to the CEO. It audits the **system**, not the people
in it, and every governance rule in the charter is enforced in code,
not convention.

## Layout

| Path | Purpose |
|---|---|
| `CLAUDE.md` | The charter — owner: Ahmed Diab, CEO; only he amends it (§17) |
| `docs/` | Expert panel challenge (v2.0) and second-round review (v4.2) |
| `config/` | Operative configuration (§5.3); undecided values carry their open-decision IDs |
| `src/control/` | The engine |
| `tests/` | 134+ tests; `python -m pytest` |
| `knowledge/`, `discovery/`, `data/`, `learning/`, `outbox/`, `reports/`, `logs/` | Runtime tree per §5.3 — operational data is gitignored (§12.1, §12.2) |

## Engine modules

| Module | Charter | Enforces |
|---|---|---|
| `startup.py` | §5.6 | Config-first startup; halts on missing config, failed integrity, broken hash chain, or an illegal §16 state |
| `states.py` | §16, §15 | Legal-state table; demotion targets per trigger |
| `db.py` | §5.2 | Append-only SQLite; corrections need reason; currency/fx constraints; period locks |
| `audit.py` | §1.9 | Hash-chained JSONL log; verify() detects edits, truncation, gaps |
| `calendar.py` | §8.3, §5.1 | Sunday–Thursday week, Africa/Cairo, working-day arithmetic |
| `classify.py` | §9 | Eleven inbound categories; fraud outranks all; injection cues flagged, never obeyed |
| `attachments.py` | §5.4, §5.5 | Macro/executable refusal, sniffing, quarantine; values-only extraction |
| `evaluate.py` | §7.1, §7.4, §12.1.3 | C1–C7 checks; verdicts; confidential reduced set |
| `render.py` | §7.5, §4 | Bilingual verdict emails; Arabic authoritative; Western numerals both halves |
| `enforce.py` | §8.1–§8.4 | Class 1/2 deadline engine; class 3 ladder; absence/dispute/reliability rules |
| `anomaly.py` | §7.3 | S1–S4 signals with honest preconditions (O-11, minimum samples) |
| `watchdog.py` | §8.5 | External SLA tracking; observation-worded notices; CC-compliance metric |
| `outbox.py` | §10 | Gate table as code; external gate has no override; authenticated approval release |
| `report.py` | §11 | Weekly report — class 1/2 horizon always first; numbers trace to rows |
| `cycle.py` | §5.6 | One sweep: state first, mailbox last, idempotent, audit-logged |
| `transport.py` | §5.1 | Mail boundary; Graph stub raises until provisioned |
| `discovery/` | §6 | Phase 0 Stages A–B, read-only, limitations always written |

## Running

```bash
pip install -e ".[dev]"
python -m pytest                          # full suite

python -m control startup   --control-root <CONTROL_ROOT> --ub-root <UB_ROOT>
python -m control discovery --control-root <CONTROL_ROOT> --ub-root <UB_ROOT>
python -m control verify    --control-root <CONTROL_ROOT>
```

There is deliberately no `cycle` command yet: a live cycle needs the
Microsoft Graph transport, which needs the §5.1 provisioning (Entra app
scoped to the single mailbox, certificate auth, Application Access
Policy) — open decision O-09.

## Deployment state

Phase 0 (Discovery), Level 0, `RUN_MODE=DISCOVERY`, `LEARNING_MODE=OBSERVE`.
The engine sends nothing. Phase gates and the full open-decision list
(O-01 … O-11) are in the charter, Appendix B.
