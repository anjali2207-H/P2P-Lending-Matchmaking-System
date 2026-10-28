"""Week 2 - profile management: registration, validation, status tracking.
All functions take an open sqlite3 connection (`conn`) so they work inside
Flask routes, scripts and tests. Invalid input raises ValidationError.
"""
import math
import sqlite3
from werkzeug.security import generate_password_hash
import audit
from models import Borrower, Lender, LoanRequest, ValidationError

MIN_PASSWORD_LENGTH = 8

# allowed profile-status transitions (profile status tracking)
STATUS_TRANSITIONS = {
    "pending": {"active", "rejected"},
    "active": {"inactive"},
    "inactive": {"active"},
    "rejected": {"pending"},
}

_LENDER_SQL = ("SELECT l.*, u.full_name, u.email, u.status FROM lenders l "
               "JOIN users u ON u.user_id = l.user_id")
_BORROWER_SQL = ("SELECT b.*, u.full_name, u.email, u.status FROM borrowers b "
                 "JOIN users u ON u.user_id = b.user_id")


# ---------------------------------------------------------------------------
# input parsing helpers
# ---------------------------------------------------------------------------
def _text(data, key):
    value = data.get(key)
    return "" if value is None else str(value).strip()


def _number(data, key, label, cast, errors):
    raw = data.get(key)
    if raw is None or str(raw).strip() == "":
        errors.append(f"{label} is required.")
        return None
    try:
        value = cast(str(raw).strip().replace(",", ""))
    except ValueError:
        errors.append(f"{label} must be a valid {'whole number' if cast is int else 'number'}.")
        return None
    if isinstance(value, float) and not math.isfinite(value):
        errors.append(f"{label} must be a finite number.")
        return None
    return value


def _check_password(data, errors):
    password = str(data.get("password") or "")
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must have at least {MIN_PASSWORD_LENGTH} characters.")
        return None
    return generate_password_hash(password)


def _insert_user(conn, person, role, password_hash):
    cur = conn.execute(
        "INSERT INTO users(full_name, email, password_hash, role, status) VALUES (?, ?, ?, ?, 'active')",
        (person.full_name, person.email, password_hash, role))
    return cur.lastrowid


def _email_taken(conn, email):
    return conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone() is not None


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------
def register_lender(conn, data, auto_activate=False):
    """Validate and store a lender. Returns the new lender_id."""
    errors = []
    f = lambda key, label: _number(data, key, label, float, errors)  # noqa: E731
    i = lambda key, label: _number(data, key, label, int, errors)    # noqa: E731
    lender = Lender(
        _text(data, "full_name"), _text(data, "email"), _text(data, "risk_appetite"),
        f("available_amount", "Available amount"), f("min_loan_amount", "Minimum loan amount"),
        f("max_loan_amount", "Maximum loan amount"), i("min_duration_months", "Minimum duration"),
        i("max_duration_months", "Maximum duration"), f("min_expected_return", "Minimum expected return"),
        f("max_expected_return", "Maximum expected return"))
    password_hash = _check_password(data, errors)
    if errors:
        raise ValidationError(errors)
    errors = lender.validate()
    if lender.email and _email_taken(conn, lender.email):
        errors.append("This email address is already registered.")
    if errors:
        raise ValidationError(errors)
    status = "active" if auto_activate else "pending"
    try:
        user_id = _insert_user(conn, lender, "lender", password_hash)
        cur = conn.execute(
            "INSERT INTO lenders(user_id, risk_appetite, available_amount, min_loan_amount, max_loan_amount,"
            " min_duration_months, max_duration_months, min_expected_return, max_expected_return, profile_status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, lender.risk_appetite, lender.available_amount, lender.min_loan_amount,
             lender.max_loan_amount, lender.min_duration_months, lender.max_duration_months,
             lender.min_expected_return, lender.max_expected_return, status))
        lender_id = cur.lastrowid
        audit.log(conn, "lender", lender_id, "REGISTERED", None, status, actor=lender.email)
        conn.commit()
        return lender_id
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValidationError(f"Database rejected the lender profile: {exc}")


def register_borrower(conn, data, auto_activate=False):
    """Validate and store a borrower. Returns the new borrower_id."""
    errors = []
    f = lambda key, label: _number(data, key, label, float, errors)  # noqa: E731
    borrower = Borrower(
        _text(data, "full_name"), _text(data, "email"),
        f("monthly_income", "Monthly income"), f("existing_obligations", "Existing obligations"),
        _number(data, "credit_score", "Credit score", int, errors),
        f("credit_history_years", "Credit history (years)"))
    password_hash = _check_password(data, errors)
    if errors:
        raise ValidationError(errors)
    errors = borrower.validate()
    if borrower.email and _email_taken(conn, borrower.email):
        errors.append("This email address is already registered.")
    if errors:
        raise ValidationError(errors)
    status = "active" if auto_activate else "pending"
    try:
        user_id = _insert_user(conn, borrower, "borrower", password_hash)
        cur = conn.execute(
            "INSERT INTO borrowers(user_id, monthly_income, existing_obligations, credit_score,"
            " credit_history_years, profile_status) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, borrower.monthly_income, borrower.existing_obligations, borrower.credit_score,
             borrower.credit_history_years, status))
        borrower_id = cur.lastrowid
        audit.log(conn, "borrower", borrower_id, "REGISTERED", None, status, actor=borrower.email)
        conn.commit()
        return borrower_id
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValidationError(f"Database rejected the borrower profile: {exc}")


def create_loan_request(conn, borrower_id, data):
    """Validate and store a loan request for an ACTIVE borrower. Returns request_id."""
    borrower = get_borrower(conn, borrower_id)
    if borrower is None:
        raise ValidationError("Borrower does not exist.")
    if not borrower.is_matchable():
        raise ValidationError(f"Borrower profile must be active before requesting a loan "
                              f"(current status: {borrower.profile_status}).")
    errors = []
    request = LoanRequest(borrower_id,
                          _number(data, "amount", "Loan amount", float, errors),
                          _number(data, "term_months", "Repayment term", int, errors),
                          _text(data, "purpose"))
    if errors:
        raise ValidationError(errors)
    errors = request.validate()
    duplicate = conn.execute(
        "SELECT request_id FROM loan_requests WHERE borrower_id = ? AND amount = ? AND term_months = ?"
        " AND status IN ('pending', 'matched')", (borrower_id, request.amount, request.term_months)).fetchone()
    if duplicate:
        errors.append(f"Duplicate request: request #{duplicate['request_id']} with the same amount and "
                      f"term is already open.")
    if errors:
        raise ValidationError(errors)
    try:
        cur = conn.execute(
            "INSERT INTO loan_requests(borrower_id, amount, term_months, purpose) VALUES (?, ?, ?, ?)",
            (borrower_id, request.amount, request.term_months, request.purpose))
        request_id = cur.lastrowid
        audit.log(conn, "loan_request", request_id, "CREATED", None, "pending", actor=borrower.email)
        conn.commit()
        return request_id
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValidationError(f"Database rejected the loan request: {exc}")


def cancel_request(conn, request_id, actor="user"):
    row = conn.execute("SELECT status FROM loan_requests WHERE request_id = ?", (request_id,)).fetchone()
    if row is None:
        raise ValidationError("Loan request does not exist.")
    if row["status"] not in ("pending", "matched"):
        raise ValidationError(f"A request in status '{row['status']}' cannot be cancelled.")
    conn.execute("UPDATE loan_requests SET status = 'cancelled' WHERE request_id = ?", (request_id,))
    audit.log(conn, "loan_request", request_id, "STATUS_CHANGE", row["status"], "cancelled", actor)
    conn.commit()


# ---------------------------------------------------------------------------
# profile-status tracking
# ---------------------------------------------------------------------------
def set_profile_status(conn, role, profile_id, new_status, actor="admin"):
    """Move a lender/borrower profile along the allowed status transitions."""
    if role not in ("lender", "borrower"):
        raise ValidationError("Role must be 'lender' or 'borrower'.")
    table, key = ("lenders", "lender_id") if role == "lender" else ("borrowers", "borrower_id")
    row = conn.execute(f"SELECT profile_status FROM {table} WHERE {key} = ?", (profile_id,)).fetchone()
    if row is None:
        raise ValidationError(f"{role.capitalize()} #{profile_id} does not exist.")
    old = row["profile_status"]
    if new_status not in STATUS_TRANSITIONS.get(old, set()):
        raise ValidationError(f"Cannot change {role} profile from '{old}' to '{new_status}'.")
    conn.execute(f"UPDATE {table} SET profile_status = ? WHERE {key} = ?", (new_status, profile_id))
    audit.log(conn, role, profile_id, "PROFILE_STATUS_CHANGE", old, new_status, actor)
    conn.commit()


# ---------------------------------------------------------------------------
# queries
# ---------------------------------------------------------------------------
def get_lender(conn, lender_id):
    row = conn.execute(_LENDER_SQL + " WHERE l.lender_id = ?", (lender_id,)).fetchone()
    return Lender.from_row(row) if row else None


def get_borrower(conn, borrower_id):
    row = conn.execute(_BORROWER_SQL + " WHERE b.borrower_id = ?", (borrower_id,)).fetchone()
    return Borrower.from_row(row) if row else None


def get_request(conn, request_id):
    row = conn.execute("SELECT * FROM loan_requests WHERE request_id = ?", (request_id,)).fetchone()
    return LoanRequest.from_row(row) if row else None


def list_lenders(conn, profile_status=None):
    sql, params = _LENDER_SQL, ()
    if profile_status:
        sql, params = sql + " WHERE l.profile_status = ?", (profile_status,)
    return [Lender.from_row(r) for r in conn.execute(sql + " ORDER BY l.lender_id", params)]


def list_borrowers(conn, profile_status=None):
    sql, params = _BORROWER_SQL, ()
    if profile_status:
        sql, params = sql + " WHERE b.profile_status = ?", (profile_status,)
    return [Borrower.from_row(r) for r in conn.execute(sql + " ORDER BY b.borrower_id", params)]


def list_requests(conn, status=None):
    """Loan requests joined with the borrower's name (plain dicts for tables)."""
    sql = ("SELECT r.request_id, r.borrower_id, u.full_name AS borrower, r.amount, r.term_months,"
           " r.purpose, r.status, r.created_at FROM loan_requests r"
           " JOIN borrowers b ON b.borrower_id = r.borrower_id JOIN users u ON u.user_id = b.user_id")
    params = ()
    if status:
        sql, params = sql + " WHERE r.status = ?", (status,)
    return [dict(r) for r in conn.execute(sql + " ORDER BY r.request_id", params)]
