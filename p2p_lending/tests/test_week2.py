"""Week 2 tests: models, validation, profile status tracking, forms.
Run: python -m unittest tests.test_week2 -v (or python -m pytest tests/test_week2.py)
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database
import profile_service as ps
from models import Borrower, Lender, LoanRequest, ValidationError, calculate_emi

LENDER = {"full_name": "Test Lender", "email": "tl@x.com", "password": "password123", "risk_appetite": "medium",
          "available_amount": 100000, "min_loan_amount": 5000, "max_loan_amount": 50000,
          "min_duration_months": 6, "max_duration_months": 24, "min_expected_return": 8, "max_expected_return": 15}
BORROWER = {"full_name": "Test Borrower", "email": "tb@x.com", "password": "password123", "monthly_income": 40000,
            "existing_obligations": 5000, "credit_score": 700, "credit_history_years": 4}


class Week2Tests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "t.db")
        database.init_db(self.path)
        self.conn = database.get_connection(self.path)

    def tearDown(self):
        self.conn.close()

    def expect_error(self, func, *args, contains=""):
        with self.assertRaises(ValidationError) as ctx:
            func(*args)
        self.assertIn(contains.lower(), " ".join(ctx.exception.errors).lower())

    # ---- models ------------------------------------------------------------
    def test_emi_formula(self):
        self.assertAlmostEqual(calculate_emi(100000, 12, 12), 8884.88, places=2)
        self.assertEqual(calculate_emi(1200, 0, 12), 100.0)

    def test_lender_behaviour(self):
        lender = Lender("Ann Lee", "a@x.com", "medium", 1000, 100, 900, 6, 12, 8, 12, profile_status="active")
        self.assertTrue(lender.accepts_risk("low") and lender.accepts_risk("medium"))
        self.assertFalse(lender.accepts_risk("high"))
        self.assertTrue(lender.accepts_duration(12) and not lender.accepts_duration(13))
        self.assertTrue(lender.accepts_rate(8) and not lender.accepts_rate(12.5))
        self.assertTrue(lender.is_matchable())

    def test_borrower_dti_and_request_instalment(self):
        b = Borrower("Bo Ray", "b@x.com", 10000, 2500, 700, 3)
        self.assertEqual(b.debt_to_income(), 0.25)
        self.assertEqual(LoanRequest(1, 100000, 12).monthly_instalment(12), 8884.88)

    # ---- registration + validation ----------------------------------------
    def test_register_lender_starts_pending(self):
        lender_id = ps.register_lender(self.conn, LENDER)
        self.assertEqual(ps.get_lender(self.conn, lender_id).profile_status, "pending")
        self.assertEqual(self.conn.execute("SELECT role FROM users").fetchone()["role"], "lender")

    def test_password_is_hashed(self):
        ps.register_lender(self.conn, LENDER)
        stored = self.conn.execute("SELECT password_hash FROM users").fetchone()[0]
        self.assertNotIn("password123", stored)

    def test_missing_fields(self):
        self.expect_error(ps.register_lender, self.conn, {}, contains="required")
        self.expect_error(ps.register_borrower, self.conn, {}, contains="required")

    def test_invalid_values(self):
        self.expect_error(ps.register_lender, self.conn, dict(LENDER, risk_appetite="wild"), contains="risk appetite")
        self.expect_error(ps.register_lender, self.conn, dict(LENDER, email="bad"), contains="valid email")
        self.expect_error(ps.register_lender, self.conn, dict(LENDER, available_amount="-5"), contains="greater than 0")
        self.expect_error(ps.register_lender, self.conn, dict(LENDER, min_duration_months="30"), contains="duration")
        self.expect_error(ps.register_lender, self.conn, dict(LENDER, available_amount="nan"), contains="finite")
        self.expect_error(ps.register_lender, self.conn, dict(LENDER, password="short"), contains="password")
        self.expect_error(ps.register_borrower, self.conn, dict(BORROWER, credit_score="950"), contains="credit score")
        self.expect_error(ps.register_borrower, self.conn, dict(BORROWER, monthly_income="0"), contains="income")
        self.expect_error(ps.register_borrower, self.conn, dict(BORROWER, credit_score="7.5"), contains="whole number")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)

    def test_duplicate_email(self):
        ps.register_lender(self.conn, LENDER)
        self.expect_error(ps.register_borrower, self.conn, dict(BORROWER, email="TL@x.com"), contains="already")

    # ---- loan requests -----------------------------------------------------
    def test_request_needs_active_borrower(self):
        bid = ps.register_borrower(self.conn, BORROWER)
        self.expect_error(ps.create_loan_request, self.conn, bid, {"amount": 5000, "term_months": 12}, contains="active")
        ps.set_profile_status(self.conn, "borrower", bid, "active")
        rid = ps.create_loan_request(self.conn, bid, {"amount": 5000, "term_months": 12})
        self.assertEqual(ps.get_request(self.conn, rid).status, "pending")

    def test_duplicate_and_invalid_requests(self):
        bid = ps.register_borrower(self.conn, BORROWER, auto_activate=True)
        ps.create_loan_request(self.conn, bid, {"amount": 5000, "term_months": 12})
        self.expect_error(ps.create_loan_request, self.conn, bid, {"amount": 5000, "term_months": 12}, contains="duplicate")
        self.expect_error(ps.create_loan_request, self.conn, bid, {"amount": 10, "term_months": 12}, contains="between")
        self.expect_error(ps.create_loan_request, self.conn, bid, {"amount": 5000, "term_months": 500}, contains="term")
        self.expect_error(ps.create_loan_request, self.conn, bid, {"amount": "", "term_months": 12}, contains="required")
        self.expect_error(ps.create_loan_request, self.conn, 999, {"amount": 5000, "term_months": 12}, contains="exist")

    def test_cancel_request_allows_same_request_again(self):
        bid = ps.register_borrower(self.conn, BORROWER, auto_activate=True)
        rid = ps.create_loan_request(self.conn, bid, {"amount": 5000, "term_months": 12})
        ps.cancel_request(self.conn, rid)
        ps.create_loan_request(self.conn, bid, {"amount": 5000, "term_months": 12})

    # ---- profile-status tracking ------------------------------------------
    def test_status_transitions_and_audit(self):
        lid = ps.register_lender(self.conn, LENDER)
        ps.set_profile_status(self.conn, "lender", lid, "active")
        ps.set_profile_status(self.conn, "lender", lid, "inactive")
        self.expect_error(ps.set_profile_status, self.conn, "lender", lid, "rejected", contains="cannot change")
        self.expect_error(ps.set_profile_status, self.conn, "lender", 99, "active", contains="does not exist")
        actions = [r[0] for r in self.conn.execute("SELECT action FROM audit_logs WHERE entity_type='lender'")]
        self.assertEqual(actions, ["REGISTERED", "PROFILE_STATUS_CHANGE", "PROFILE_STATUS_CHANGE"])

    def test_engine_loads_only_active_lenders(self):
        from matching_engine import MatchingEngine
        ps.register_lender(self.conn, LENDER, auto_activate=True)
        ps.register_lender(self.conn, dict(LENDER, email="o@x.com"))
        self.assertEqual(len(MatchingEngine(self.conn).load_active_lenders()), 1)

    # ---- web forms ----------------------------------------------------------
    def test_forms_in_browser(self):
        from app import create_app
        client = create_app(self.path).test_client()
        for url in ("/", "/lenders", "/borrowers", "/requests", "/lenders/register", "/borrowers/register", "/requests/new"):
            self.assertEqual(client.get(url).status_code, 200, url)
        bad = client.post("/lenders/register", data=dict(LENDER, email="bad"))
        self.assertEqual(bad.status_code, 200)
        self.assertIn(b"valid email", bad.data)
        ok = client.post("/lenders/register", data=LENDER, follow_redirects=True)
        self.assertIn(b"registered", ok.data)
        client.post("/borrowers/register", data=BORROWER)
        approve = client.post("/profiles/borrower/1/status?to=active", follow_redirects=True)
        self.assertIn(b"is now", approve.data)
        made = client.post("/requests/new", data={"borrower_id": "1", "amount": "9000", "term_months": "12"},
                           follow_redirects=True)
        self.assertIn(b"created", made.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
