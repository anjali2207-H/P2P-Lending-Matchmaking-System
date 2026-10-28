-- P2P Lending Matchmaking System : database schema (SQLite)  -- Week 1
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name      TEXT    NOT NULL CHECK (length(trim(full_name)) > 0),
    email          TEXT    NOT NULL UNIQUE,
    password_hash  TEXT    NOT NULL,
    role           TEXT    NOT NULL CHECK (role IN ('lender','borrower','admin')),
    status         TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive','suspended')),
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lenders (
    lender_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id              INTEGER NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    risk_appetite        TEXT    NOT NULL CHECK (risk_appetite IN ('low','medium','high')),
    available_amount     REAL    NOT NULL CHECK (available_amount >= 0),
    min_loan_amount      REAL    NOT NULL CHECK (min_loan_amount > 0),
    max_loan_amount      REAL    NOT NULL,
    min_duration_months  INTEGER NOT NULL CHECK (min_duration_months > 0),
    max_duration_months  INTEGER NOT NULL,
    min_expected_return  REAL    NOT NULL CHECK (min_expected_return >= 0),   -- annual %
    max_expected_return  REAL    NOT NULL,                                    -- annual %
    profile_status       TEXT    NOT NULL DEFAULT 'pending'
                         CHECK (profile_status IN ('pending','active','inactive','rejected')),
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    CHECK (max_loan_amount >= min_loan_amount),
    CHECK (max_duration_months >= min_duration_months),
    CHECK (max_expected_return >= min_expected_return)
);

CREATE TABLE IF NOT EXISTS borrowers (
    borrower_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                INTEGER NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
    monthly_income         REAL    NOT NULL CHECK (monthly_income > 0),       -- simulated
    existing_obligations   REAL    NOT NULL DEFAULT 0 CHECK (existing_obligations >= 0), -- monthly EMIs
    credit_score           INTEGER NOT NULL CHECK (credit_score BETWEEN 300 AND 900),    -- simulated
    credit_history_years   REAL    NOT NULL DEFAULT 0 CHECK (credit_history_years >= 0),
    profile_status         TEXT    NOT NULL DEFAULT 'pending'
                           CHECK (profile_status IN ('pending','active','inactive','rejected')),
    created_at             TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS loan_requests (
    request_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id   INTEGER NOT NULL REFERENCES borrowers(borrower_id) ON DELETE CASCADE,
    amount        REAL    NOT NULL CHECK (amount > 0),
    term_months   INTEGER NOT NULL CHECK (term_months > 0),
    purpose       TEXT,
    status        TEXT    NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','matched','funded','rejected','cancelled')),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
-- Rule: a borrower cannot have two identical open requests (duplicate-request protection)
CREATE UNIQUE INDEX IF NOT EXISTS ux_open_duplicate_request
    ON loan_requests (borrower_id, amount, term_months)
    WHERE status IN ('pending','matched');

CREATE TABLE IF NOT EXISTS risk_scores (
    risk_score_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    borrower_id    INTEGER NOT NULL REFERENCES borrowers(borrower_id) ON DELETE CASCADE,
    request_id     INTEGER REFERENCES loan_requests(request_id) ON DELETE SET NULL,
    score          REAL    NOT NULL CHECK (score BETWEEN 0 AND 100),
    risk_category  TEXT    NOT NULL CHECK (risk_category IN ('low','medium','high')),
    components     TEXT,      -- JSON: score breakdown
    explanation    TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matches (
    match_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    lender_id            INTEGER NOT NULL REFERENCES lenders(lender_id) ON DELETE CASCADE,
    request_id           INTEGER NOT NULL REFERENCES loan_requests(request_id) ON DELETE CASCADE,
    compatibility_score  REAL    NOT NULL DEFAULT 0 CHECK (compatibility_score BETWEEN 0 AND 100),
    risk_fit             REAL    NOT NULL DEFAULT 0,
    amount_fit           REAL    NOT NULL DEFAULT 0,
    term_fit             REAL    NOT NULL DEFAULT 0,
    return_fit           REAL    NOT NULL DEFAULT 0,
    allocated_amount     REAL    NOT NULL DEFAULT 0 CHECK (allocated_amount >= 0),
    status               TEXT    NOT NULL DEFAULT 'recommended'
                         CHECK (status IN ('recommended','accepted','rejected','expired')),
    explanation          TEXT,
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (lender_id, request_id)
);

CREATE TABLE IF NOT EXISTS loans (
    loan_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id             INTEGER NOT NULL UNIQUE REFERENCES matches(match_id),
    lender_id            INTEGER NOT NULL REFERENCES lenders(lender_id),
    borrower_id          INTEGER NOT NULL REFERENCES borrowers(borrower_id),
    principal            REAL    NOT NULL CHECK (principal > 0),
    interest_rate        REAL    NOT NULL CHECK (interest_rate >= 0),   -- annual %
    duration_months      INTEGER NOT NULL CHECK (duration_months > 0),
    outstanding_balance  REAL    NOT NULL CHECK (outstanding_balance >= 0),
    status               TEXT    NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active','completed','defaulted')),
    start_date           TEXT    NOT NULL DEFAULT (date('now')),
    created_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS repayments (
    repayment_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id             INTEGER NOT NULL REFERENCES loans(loan_id) ON DELETE CASCADE,
    installment_no      INTEGER NOT NULL CHECK (installment_no > 0),
    due_date            TEXT    NOT NULL,
    amount_due          REAL    NOT NULL CHECK (amount_due > 0),
    amount_paid         REAL    NOT NULL DEFAULT 0 CHECK (amount_paid >= 0),
    status              TEXT    NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','paid','late','defaulted')),
    paid_date           TEXT,
    UNIQUE (loan_id, installment_no)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type  TEXT NOT NULL,
    entity_id    INTEGER,
    action       TEXT NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    actor        TEXT NOT NULL DEFAULT 'system',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for fast matching on large datasets
CREATE INDEX IF NOT EXISTS ix_lenders_status      ON lenders(profile_status, risk_appetite);
CREATE INDEX IF NOT EXISTS ix_requests_status     ON loan_requests(status);
CREATE INDEX IF NOT EXISTS ix_matches_request     ON matches(request_id);
CREATE INDEX IF NOT EXISTS ix_repayments_loan     ON repayments(loan_id, status);
CREATE INDEX IF NOT EXISTS ix_audit_entity        ON audit_logs(entity_type, entity_id);
