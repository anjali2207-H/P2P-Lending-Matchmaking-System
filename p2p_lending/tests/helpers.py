"""Shared helpers for the test files (Weeks 4-7)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database
import profile_service as ps

_counter = [0]


def new_conn():
    path = os.path.join(tempfile.mkdtemp(), "test.db")
    database.init_db(path)
    return database.get_connection(path), path


def add_lender(conn, appetite="medium", available=100000, min_loan=5000, max_loan=100000,
               min_m=6, max_m=36, min_ret=8, max_ret=22, activate=True):
    _counter[0] += 1
    return ps.register_lender(conn, {
        "full_name": f"Lender {_counter[0]}", "email": f"lender{_counter[0]}@t.com", "password": "password123",
        "risk_appetite": appetite, "available_amount": available, "min_loan_amount": min_loan,
        "max_loan_amount": max_loan, "min_duration_months": min_m, "max_duration_months": max_m,
        "min_expected_return": min_ret, "max_expected_return": max_ret}, auto_activate=activate)


def add_borrower(conn, income=60000, obligations=5000, credit=720, years=5, activate=True):
    _counter[0] += 1
    return ps.register_borrower(conn, {
        "full_name": f"Borrower {_counter[0]}", "email": f"borrower{_counter[0]}@t.com", "password": "password123",
        "monthly_income": income, "existing_obligations": obligations, "credit_score": credit,
        "credit_history_years": years}, auto_activate=activate)


def add_request(conn, borrower_id, amount=30000, term=12, purpose="test"):
    return ps.create_loan_request(conn, borrower_id, {"amount": amount, "term_months": term, "purpose": purpose})
