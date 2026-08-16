"""System of record — charter §5.2. SQLite is the master; Excel is export.

Invariants enforced here in schema, not in convention:
- append-only: UPDATE and DELETE are blocked by triggers on record tables;
  corrections INSERT a new row carrying `correction_of` and a reason
- every row carries source (LIVE|BACKFILL) and provenance columns
- monetary values require currency_code; non-EGP requires fx_rate and
  fx_rate_date (CHECK constraints)
- period lock: once a management report issues, later rows for that period
  need a CEO-approved correction reference
- derived values are always recomputed, never trusted from storage —
  therefore no derived columns exist in the schema
"""

import sqlite3
from pathlib import Path

from . import HaltError

# Tables that are strictly append-only (§5.2).
APPEND_ONLY = (
    "obligations",
    "submissions",
    "findings",
    "external_threads",
    "anomalies",
    "disputes",
    "learning_ledger",
    "knowledge_base",
    "baselines",
    "outcomes",
    "period_locks",
    "registers_contracts",
    "registers_instruments",
    "registers_accreditations",
    "registers_quotations",
    "registers_tenders",
)

# SQLite grammar: all column definitions must precede table-level CHECKs,
# so columns and constraints are separate fragments composed in order.
_PROVENANCE_COLS = """
    source_email_id TEXT,
    submitted_by    TEXT,
    submitted_at    TEXT,
    period          TEXT,
    posted_at       TEXT DEFAULT (datetime('now')),
    source          TEXT NOT NULL CHECK (source IN ('LIVE','BACKFILL')),
    correction_of   INTEGER,
    correction_reason TEXT,
"""

_PROVENANCE_CHECK = """
    CHECK (correction_of IS NULL OR correction_reason IS NOT NULL)
"""

_PROVENANCE = _PROVENANCE_COLS + _PROVENANCE_CHECK

_MONEY_COLS = """
    amount        REAL,
    currency_code TEXT,
    fx_rate       REAL,
    fx_rate_date  TEXT,
"""

_MONEY_CHECKS = """
    CHECK (amount IS NULL OR currency_code IS NOT NULL),
    CHECK (currency_code IS NULL OR currency_code = 'EGP'
           OR (fx_rate IS NOT NULL AND fx_rate_date IS NOT NULL)),
"""

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY, value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    name TEXT,
    role TEXT,
    reports_to TEXT,
    tier INTEGER,
    confirmed INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    language_mode TEXT NOT NULL DEFAULT 'formal',
    recorded_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS absence (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    from_date TEXT NOT NULL,
    to_date TEXT NOT NULL,
    delegate TEXT,
    registered_by TEXT,
    recorded_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS obligations (
    id INTEGER PRIMARY KEY,
    obligation_id TEXT NOT NULL,
    class INTEGER NOT NULL CHECK (class IN (1,2,3,4)),
    name TEXT NOT NULL,
    owner TEXT,
    form TEXT,
    cadence TEXT,
    due_rule TEXT,
    governing_clause TEXT,
    confidence TEXT CHECK (confidence IN ('HIGH','MEDIUM','LOW')),
    approved_by_ceo TEXT,
    {_PROVENANCE}
);

CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY,
    obligation_id TEXT,
    verdict TEXT CHECK (verdict IN (
        'ACCEPTED','ACCEPTED_WITH_OBSERVATIONS','RETURNED_FOR_REVISION',
        'NOT_ACCEPTED','UNREADABLE',
        'RECEIVED_ON_TIME','RECEIVED_LATE','NOT_RECEIVED',
        'NOT_ASSESSED_CONFIDENTIAL_SCOPE')),
    timeliness TEXT,
    confidential INTEGER NOT NULL DEFAULT 0,
    file_path TEXT,
    {_PROVENANCE}
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY,
    submission_id INTEGER,
    check_id TEXT NOT NULL CHECK (check_id IN ('C1','C2','C3','C4','C5','C6','C7')),
    result TEXT NOT NULL,
    required TEXT,
    observed TEXT,
    action TEXT,
    reference TEXT,
    {_PROVENANCE}
);

CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY,
    signal TEXT NOT NULL CHECK (signal IN ('S1','S2','S3','S4')),
    detail TEXT NOT NULL,
    subject_ref TEXT,
    flagged_to TEXT,
    confirmed_useful INTEGER,
    {_MONEY_COLS}
    {_PROVENANCE_COLS}
    {_MONEY_CHECKS}
    {_PROVENANCE_CHECK}
);

CREATE TABLE IF NOT EXISTS external_threads (
    id INTEGER PRIMARY KEY,
    thread_id TEXT NOT NULL,
    category TEXT,
    owner TEXT,
    sla_first TEXT,
    sla_final TEXT,
    state TEXT NOT NULL CHECK (state IN (
        'OPEN','CLOSED_OBSERVED_REPLY','CLOSED_DECLARED','BREACHED')),
    declarant TEXT,
    {_PROVENANCE}
);

CREATE TABLE IF NOT EXISTS disputes (
    id INTEGER PRIMARY KEY,
    submission_id INTEGER,
    raised_by TEXT NOT NULL,
    raised_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PENDING','UPHELD','REJECTED')),
    adjudicated_by TEXT,
    adjudicated_at TEXT,
    {_PROVENANCE}
);

CREATE TABLE IF NOT EXISTS learning_ledger (
    id INTEGER PRIMARY KEY,
    adaptation_id TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (tier IN ('A','B','C')),
    direction TEXT NOT NULL CHECK (direction IN ('TIGHTENING','LOOSENING','NEUTRAL')),
    state TEXT NOT NULL CHECK (state IN (
        'PROPOSED','REJECTED_BY_GATE','APPLIED','ROLLED_BACK','CEO_APPROVED','CEO_REVERTED')),
    trigger TEXT,
    evidence TEXT,
    expected_effect TEXT,
    {_PROVENANCE}
);

CREATE TABLE IF NOT EXISTS knowledge_base (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    {_PROVENANCE}
);

CREATE TABLE IF NOT EXISTS baselines (
    id INTEGER PRIMARY KEY,
    metric TEXT NOT NULL,
    stat TEXT NOT NULL,
    value REAL,
    sample_size INTEGER NOT NULL,
    sufficient INTEGER NOT NULL DEFAULT 0,
    {_PROVENANCE}
);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    ref TEXT,
    result TEXT,
    detail TEXT,
    {_MONEY_COLS}
    {_PROVENANCE_COLS}
    {_MONEY_CHECKS}
    {_PROVENANCE_CHECK}
);

-- Class 2 registers (§2.2). The charter calls these the highest-value
-- items in the system: a missed tender deadline or a lapsed guarantee
-- costs orders of magnitude more than a late internal report.

CREATE TABLE IF NOT EXISTS registers_contracts (
    id INTEGER PRIMARY KEY,
    contract_ref TEXT NOT NULL,
    client TEXT NOT NULL,
    title TEXT,
    owner TEXT,
    start_date TEXT,
    end_date TEXT,
    ld_rate TEXT,
    ld_cap TEXT,
    notice_period_days INTEGER,
    variation_procedure TEXT,
    retention_pct REAL,
    dlp_end_date TEXT,
    payment_terms TEXT,
    confidential INTEGER NOT NULL DEFAULT 0,
    {_MONEY_COLS}
    {_PROVENANCE_COLS}
    {_MONEY_CHECKS}
    {_PROVENANCE_CHECK}
);

CREATE TABLE IF NOT EXISTS registers_instruments (
    id INTEGER PRIMARY KEY,
    instrument_ref TEXT NOT NULL,
    instrument_type TEXT NOT NULL CHECK (instrument_type IN (
        'LETTER_OF_GUARANTEE','ADVANCE_PAYMENT_GUARANTEE','PERFORMANCE_BOND',
        'BID_BOND','INSURANCE_POLICY','RETENTION')),
    issuer TEXT,
    beneficiary TEXT,
    project_ref TEXT,
    issue_date TEXT,
    expiry_date TEXT NOT NULL,
    release_date TEXT,
    owner TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','RELEASED','EXPIRED','EXTENDED','CANCELLED')),
    {_MONEY_COLS}
    {_PROVENANCE_COLS}
    {_MONEY_CHECKS}
    {_PROVENANCE_CHECK}
);

CREATE TABLE IF NOT EXISTS registers_accreditations (
    id INTEGER PRIMARY KEY,
    client TEXT NOT NULL,
    -- UNKNOWN is not PENDING. A prequalification whose status nobody
    -- has checked is a different fact from one under application, and
    -- §2.2 warns the dangerous case looks like silence (§1.1).
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'ACTIVE','PENDING','LAPSED','WITHDRAWN','UNKNOWN')),
    registered_on TEXT,
    expiry_date TEXT,
    documents_required TEXT,
    renewal_owner TEXT,
    portal TEXT,
    {_PROVENANCE_COLS}
    {_PROVENANCE_CHECK}
);

CREATE TABLE IF NOT EXISTS registers_quotations (
    id INTEGER PRIMARY KEY,
    quote_ref TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('ISSUED','RECEIVED')),
    counterparty TEXT NOT NULL,
    subject TEXT,
    issued_date TEXT,
    valid_until TEXT,
    opportunity_ref TEXT,
    owner TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','WON','LOST','EXPIRED','WITHDRAWN')),
    {_MONEY_COLS}
    {_PROVENANCE_COLS}
    {_MONEY_CHECKS}
    {_PROVENANCE_CHECK}
);

CREATE TABLE IF NOT EXISTS registers_tenders (
    id INTEGER PRIMARY KEY,
    tender_ref TEXT NOT NULL,
    client TEXT NOT NULL,
    title TEXT,
    owner TEXT,
    rfq_received TEXT,
    bid_decision_due TEXT,
    site_visit_date TEXT,
    clarification_deadline TEXT,
    bid_bond_due TEXT,
    submission_deadline TEXT,
    technical_opening TEXT,
    commercial_opening TEXT,
    result TEXT CHECK (result IS NULL OR result IN ('WON','LOST','CANCELLED','PENDING')),
    result_date TEXT,
    postmortem_due TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','SUBMITTED','CLOSED','NO_BID')),
    {_MONEY_COLS}
    {_PROVENANCE_COLS}
    {_MONEY_CHECKS}
    {_PROVENANCE_CHECK}
);

CREATE TABLE IF NOT EXISTS period_locks (
    id INTEGER PRIMARY KEY,
    period TEXT NOT NULL,
    locked_by_report TEXT NOT NULL,
    locked_at TEXT DEFAULT (datetime('now')),
    source TEXT NOT NULL DEFAULT 'LIVE' CHECK (source IN ('LIVE','BACKFILL'))
);
"""


def _append_only_triggers(table: str) -> str:
    return f"""
CREATE TRIGGER IF NOT EXISTS {table}_no_update
BEFORE UPDATE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only: corrections INSERT with correction_of (§5.2)'); END;
CREATE TRIGGER IF NOT EXISTS {table}_no_delete
BEFORE DELETE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only: history is never deleted (§5.2)'); END;
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    for table in APPEND_ONLY:
        conn.executescript(_append_only_triggers(table))
    # Stamped from the package constant rather than a literal, which
    # had already drifted three charter versions behind.
    from . import CHARTER_VERSION

    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value)"
        " VALUES ('charter_version', ?)", (CHARTER_VERSION,)
    )
    conn.commit()
    return conn


def integrity_check(conn: sqlite3.Connection) -> None:
    """§5.6 step 2: verify DB integrity or halt."""
    row = conn.execute("PRAGMA integrity_check").fetchone()
    if row is None or row[0] != "ok":
        raise HaltError(f"control.db integrity check failed: {row}")


def period_is_locked(conn: sqlite3.Connection, period: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM period_locks WHERE period = ? LIMIT 1", (period,)
    ).fetchone()
    return row is not None


def insert_submission(conn: sqlite3.Connection, row: dict) -> int:
    """Insert honouring the period lock (§5.2): a locked period requires a
    CEO-approved correction (correction_of + correction_reason)."""
    period = row.get("period")
    if period and period_is_locked(conn, period) and not row.get("correction_of"):
        raise HaltError(
            f"period {period} is locked; a later entry needs a CEO-approved "
            "correction and a reissued report revision (§5.2)"
        )
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    cur = conn.execute(f"INSERT INTO submissions ({cols}) VALUES ({marks})", list(row.values()))
    conn.commit()
    return cur.lastrowid
