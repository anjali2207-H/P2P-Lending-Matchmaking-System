"""Week 5 - convert accepted matches into simulated loans, build instalment
schedules, simulate repayment statuses and keep outstanding balances + audit log
up to date. No real payments are involved.
"""
import calendar
import random
from datetime import date, datetime, timedelta
import audit
import config
import profile_service
from models import ValidationError, calculate_emi

SETTLED = ("paid", "late")


# ---------------------------------------------------------------------------
# schedule maths
# ---------------------------------------------------------------------------
def add_months(start, months):
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def build_schedule(principal, annual_rate, months, start_date):
    """Reducing-balance schedule: list of dicts, last instalment clears the balance exactly."""
    emi = calculate_emi(principal, annual_rate, months)
    monthly_rate = annual_rate / 12 / 100
    balance, schedule = round(principal, 2), []
    for no in range(1, months + 1):
        interest = round(balance * monthly_rate, 2)
        principal_part = balance if no == months else round(emi - interest, 2)
        due = round(principal_part + interest, 2)
        balance = round(balance - principal_part, 2)
        schedule.append({"installment_no": no, "due_date": add_months(start_date, no).isoformat(),
                         "amount_due": due, "principal": principal_part, "interest": interest,
                         "balance_after": max(balance, 0.0)})
    return schedule


def _to_date(value):
    return value if isinstance(value, date) else datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _rate_for_request(conn, request_id):
    row = conn.execute("SELECT risk_category FROM risk_scores WHERE request_id = ?", (request_id,)).fetchone()
    return config.RATE_BY_RISK[row["risk_category"] if row else "medium"]


def _category_for_request(conn, request_id):
    row = conn.execute("SELECT risk_category FROM risk_scores WHERE request_id = ?", (request_id,)).fetchone()
    return row["risk_category"] if row else "medium"


# ---------------------------------------------------------------------------
# accepting matches -> loans
# ---------------------------------------------------------------------------
def accept_request(conn, request_id, start_date=None, actor="admin"):
    """Turn every recommended match of a fully matched request into a loan. Returns loan ids."""
    request = profile_service.get_request(conn, request_id)
    if request is None:
        raise ValidationError(f"Loan request #{request_id} does not exist.")
    if request.status != "matched":
        raise ValidationError(f"Request #{request_id} is '{request.status}', only 'matched' requests "
                              f"can be accepted.")
    matches = conn.execute("SELECT * FROM matches WHERE request_id = ? AND status = 'recommended'"
                           " AND allocated_amount > 0 ORDER BY match_id", (request_id,)).fetchall()
    if not matches:
        raise ValidationError(f"Request #{request_id} has no recommended matches.")
    if abs(sum(m["allocated_amount"] for m in matches) - request.amount) > 0.01:
        raise ValidationError(f"Request #{request_id} is not fully funded by its recommended matches.")
    start = _to_date(start_date) if start_date else date.today()
    rate = _rate_for_request(conn, request_id)
    borrower = profile_service.get_borrower(conn, request.borrower_id)
    try:
        for m in matches:  # never allocate beyond available funds
            lender = profile_service.get_lender(conn, m["lender_id"])
            if lender is None or not lender.can_fund(m["allocated_amount"]):
                raise ValidationError(f"Lender #{m['lender_id']} no longer has {m['allocated_amount']:,.2f} available.")
        loan_ids = []
        for m in matches:
            principal = m["allocated_amount"]
            cur = conn.execute(
                "INSERT INTO loans(match_id, lender_id, borrower_id, principal, interest_rate, duration_months,"
                " outstanding_balance, status, start_date) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)",
                (m["match_id"], m["lender_id"], request.borrower_id, principal, rate, request.term_months,
                 principal, start.isoformat()))
            loan_id = cur.lastrowid
            loan_ids.append(loan_id)
            conn.execute("UPDATE lenders SET available_amount = available_amount - ? WHERE lender_id = ?",
                         (principal, m["lender_id"]))
            for item in build_schedule(principal, rate, request.term_months, start):
                conn.execute("INSERT INTO repayments(loan_id, installment_no, due_date, amount_due) VALUES (?, ?, ?, ?)",
                             (loan_id, item["installment_no"], item["due_date"], item["amount_due"]))
            conn.execute("UPDATE matches SET status = 'accepted' WHERE match_id = ?", (m["match_id"],))
            audit.log(conn, "match", m["match_id"], "STATUS_CHANGE", "recommended", "accepted", actor=actor)
            audit.log(conn, "loan", loan_id, "LOAN_CREATED", None, "active", actor,
                      f"principal {principal:,.2f} at {rate:g}% for {request.term_months} months")
        conn.execute("UPDATE loan_requests SET status = 'funded' WHERE request_id = ?", (request_id,))
        audit.log(conn, "loan_request", request_id, "STATUS_CHANGE", "matched", "funded", actor=actor)
        conn.commit()
        return loan_ids
    except Exception:
        conn.rollback()
        raise


def accept_all(conn, start_date=None, actor="admin"):
    """Accept every matched request. Returns (loan_ids, errors)."""
    loan_ids, errors = [], []
    for row in conn.execute("SELECT request_id FROM loan_requests WHERE status = 'matched' ORDER BY request_id").fetchall():
        try:
            loan_ids += accept_request(conn, row["request_id"], start_date, actor)
        except ValidationError as exc:
            errors.append(f"Request #{row['request_id']}: {exc}")
    return loan_ids, errors


# ---------------------------------------------------------------------------
# repayment status changes
# ---------------------------------------------------------------------------
def _outstanding(conn, loan):
    settled = conn.execute("SELECT COUNT(*) FROM repayments WHERE loan_id = ? AND status IN ('paid', 'late')",
                           (loan["loan_id"],)).fetchone()[0]
    if settled == 0:
        return round(loan["principal"], 2)
    schedule = build_schedule(loan["principal"], loan["interest_rate"], loan["duration_months"],
                              _to_date(loan["start_date"]))
    return schedule[settled - 1]["balance_after"]


def mark_installment(conn, repayment_id, status, actor="simulation"):
    """Set one instalment to paid / late / defaulted and update loan balance + audit log."""
    if status not in ("paid", "late", "defaulted"):
        raise ValidationError("Status must be 'paid', 'late' or 'defaulted'.")
    rep = conn.execute("SELECT * FROM repayments WHERE repayment_id = ?", (repayment_id,)).fetchone()
    if rep is None:
        raise ValidationError(f"Repayment #{repayment_id} does not exist.")
    if rep["status"] != "pending":
        raise ValidationError(f"Instalment is already '{rep['status']}'.")
    earlier = conn.execute("SELECT COUNT(*) FROM repayments WHERE loan_id = ? AND installment_no < ?"
                           " AND status = 'pending'", (rep["loan_id"], rep["installment_no"])).fetchone()[0]
    if earlier:
        raise ValidationError("Earlier instalments must be settled first.")
    loan = conn.execute("SELECT * FROM loans WHERE loan_id = ?", (rep["loan_id"],)).fetchone()
    due = _to_date(rep["due_date"])
    try:
        if status == "paid":
            conn.execute("UPDATE repayments SET status='paid', amount_paid=?, paid_date=? WHERE repayment_id=?",
                         (rep["amount_due"], due.isoformat(), repayment_id))
        elif status == "late":
            fee = round(rep["amount_due"] * config.LATE_FEE_RATE, 2)
            conn.execute("UPDATE repayments SET status='late', amount_paid=?, paid_date=? WHERE repayment_id=?",
                         (round(rep["amount_due"] + fee, 2), (due + timedelta(days=config.LATE_DAYS)).isoformat(),
                          repayment_id))
        else:
            conn.execute("UPDATE repayments SET status='defaulted', amount_paid=0 WHERE repayment_id=?",
                         (repayment_id,))
        audit.log(conn, "repayment", repayment_id, "STATUS_CHANGE", "pending", status, actor,
                  f"loan {loan['loan_id']} instalment {rep['installment_no']}")
        if status == "defaulted":  # a default stops the whole loan
            for later in conn.execute("SELECT repayment_id FROM repayments WHERE loan_id = ? AND status = 'pending'",
                                      (loan["loan_id"],)).fetchall():
                conn.execute("UPDATE repayments SET status='defaulted' WHERE repayment_id = ?", (later[0],))
                audit.log(conn, "repayment", later[0], "STATUS_CHANGE", "pending", "defaulted", actor,
                          "loan defaulted - remaining instalments written off")
            new_status = "defaulted"
        else:
            pending = conn.execute("SELECT COUNT(*) FROM repayments WHERE loan_id = ? AND status = 'pending'",
                                   (loan["loan_id"],)).fetchone()[0]
            new_status = "completed" if pending == 0 else "active"
        balance = 0.0 if new_status == "completed" else _outstanding(conn, loan)
        conn.execute("UPDATE loans SET outstanding_balance = ?, status = ? WHERE loan_id = ?",
                     (balance, new_status, loan["loan_id"]))
        if new_status != loan["status"]:
            audit.log(conn, "loan", loan["loan_id"], "STATUS_CHANGE", loan["status"], new_status, actor,
                      f"outstanding balance {balance:,.2f}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def simulate_loan(conn, loan_id, scenario="random", seed=None):
    """Simulate repayments of one loan.
    scenario: 'all_paid' | 'some_late' (every 4th instalment late) | 'default' (stops paying
    halfway) | 'random' (probabilities depend on the borrower's risk class).
    """
    loan = conn.execute("SELECT * FROM loans WHERE loan_id = ?", (loan_id,)).fetchone()
    if loan is None:
        raise ValidationError(f"Loan #{loan_id} does not exist.")
    if scenario not in ("all_paid", "some_late", "default", "random"):
        raise ValidationError("Unknown scenario.")
    request_id = conn.execute("SELECT request_id FROM matches WHERE match_id = ?", (loan["match_id"],)).fetchone()[0]
    probs = config.REPAYMENT_PROBABILITIES[_category_for_request(conn, request_id)]
    rng = random.Random(seed)
    for rep in conn.execute("SELECT repayment_id, installment_no FROM repayments WHERE loan_id = ? AND"
                           " status = 'pending' ORDER BY installment_no", (loan_id,)).fetchall():
        n = rep["installment_no"]
        if scenario == "all_paid":
            status = "paid"
        elif scenario == "some_late":
            status = "late" if n % 4 == 0 else "paid"
        elif scenario == "default":
            status = "defaulted" if n > loan["duration_months"] // 2 else "paid"
        else:
            status = rng.choices(["paid", "late", "defaulted"], weights=probs)[0]
        mark_installment(conn, rep["repayment_id"], status)
        if status == "defaulted":
            break
    return get_loan(conn, loan_id)


def simulate_all(conn, scenario="random", seed=None):
    rng = random.Random(seed)
    ids = [r[0] for r in conn.execute("SELECT loan_id FROM loans WHERE status = 'active' ORDER BY loan_id")]
    for loan_id in ids:
        simulate_loan(conn, loan_id, scenario, rng.randint(0, 10**9))
    return ids


# ---------------------------------------------------------------------------
# queries for screens
# ---------------------------------------------------------------------------
_LOAN_SQL = """
SELECT lo.loan_id, lo.match_id, lo.lender_id, ul.full_name AS lender, lo.borrower_id, ub.full_name AS borrower,
 lo.principal, lo.interest_rate, lo.duration_months, lo.outstanding_balance, lo.status, lo.start_date,
 (SELECT COUNT(*) FROM repayments r WHERE r.loan_id = lo.loan_id AND r.status IN ('paid','late')) AS settled
FROM loans lo
JOIN lenders l ON l.lender_id = lo.lender_id JOIN users ul ON ul.user_id = l.user_id
JOIN borrowers b ON b.borrower_id = lo.borrower_id JOIN users ub ON ub.user_id = b.user_id
"""


def list_loans(conn):
    return [dict(r) for r in conn.execute(_LOAN_SQL + " ORDER BY lo.loan_id")]


def get_loan(conn, loan_id):
    row = conn.execute(_LOAN_SQL + " WHERE lo.loan_id = ?", (loan_id,)).fetchone()
    return dict(row) if row else None


def get_repayments(conn, loan_id):
    return [dict(r) for r in conn.execute("SELECT * FROM repayments WHERE loan_id = ? ORDER BY installment_no",
                                         (loan_id,))]


def list_pending_funding(conn):
    """Fully matched requests waiting for acceptance."""
    sql = ("SELECT r.request_id, u.full_name AS borrower, r.amount, r.term_months,"
           " COUNT(m.match_id) AS lenders, ROUND(SUM(m.allocated_amount), 2) AS allocated"
           " FROM loan_requests r JOIN borrowers b ON b.borrower_id = r.borrower_id"
           " JOIN users u ON u.user_id = b.user_id"
           " JOIN matches m ON m.request_id = r.request_id AND m.status = 'recommended' AND m.allocated_amount > 0"
           " WHERE r.status = 'matched' GROUP BY r.request_id ORDER BY r.request_id")
    return [dict(r) for r in conn.execute(sql)]
