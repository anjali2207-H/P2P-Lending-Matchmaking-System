"""Week 7 - the ten required test scenarios plus the evaluation metrics.
Run everything: python -m pytest -v (or) python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import add_borrower, add_lender, add_request, new_conn
import evaluate
import loan_service as ls
import profile_service as ps
import queries
from matching_engine import MatchingEngine
from models import ValidationError


def selected(conn):
    return [r for r in queries.list_pairs(conn, status="recommended") if r["allocated_amount"] > 0]


class RequiredScenarios(unittest.TestCase):
    def test_01_multiple_lenders_compete_for_one_borrower(self):
        conn, _ = new_conn()
        best = add_lender(conn, appetite="medium", min_ret=10, max_ret=15)
        add_lender(conn, appetite="high", min_ret=10, max_ret=15)
        add_lender(conn, appetite="high", min_ret=10, max_ret=15)
        add_request(conn, add_borrower(conn, income=45000, obligations=12000, credit=650, years=3), amount=60000, term=24)
        MatchingEngine(conn).run()
        rows = selected(conn)
        self.assertEqual([r["lender_id"] for r in rows], [best])
        self.assertEqual(len(queries.list_pairs(conn, status="expired")), 2)

    def test_02_one_lender_matched_with_multiple_loans(self):
        conn, _ = new_conn()
        add_lender(conn, available=500000)
        for _ in range(5):
            add_request(conn, add_borrower(conn), amount=40000)
        s = MatchingEngine(conn).run()
        self.assertEqual((s["requests_matched"], s["total_allocated"]), (5, 200000))

    def test_03_no_compatible_lender(self):
        conn, _ = new_conn()
        add_lender(conn, appetite="low", min_ret=1, max_ret=4)
        add_request(conn, add_borrower(conn))
        s = MatchingEngine(conn).run()
        self.assertEqual((s["eligible_edges"], s["requests_matched"], s["allocation_success_rate"]), (0, 0, 0.0))
        row = queries.list_pairs(conn)[0]
        self.assertEqual(row["status"], "rejected")
        self.assertIn("outside the lender's expected return", row["explanation"])

    def test_04_loan_amount_exceeds_available_funds(self):
        conn, _ = new_conn()
        add_lender(conn, available=25000)
        add_request(conn, add_borrower(conn), amount=60000)
        MatchingEngine(conn).run()
        self.assertIn("has 25,000 available but 60,000 is needed", queries.list_pairs(conn)[0]["explanation"])

    def test_05_risk_appetite_mismatch(self):
        conn, _ = new_conn()
        add_lender(conn, appetite="low", min_ret=6, max_ret=25)
        add_request(conn, add_borrower(conn, income=30000, obligations=5000, credit=520, years=1), amount=30000)
        MatchingEngine(conn).run()
        row = queries.list_pairs(conn)[0]
        self.assertEqual(row["status"], "rejected")
        self.assertIn("only accepts up to low risk", row["explanation"])

    def test_06_repayment_term_mismatch(self):
        conn, _ = new_conn()
        add_lender(conn, min_m=6, max_m=12)
        add_request(conn, add_borrower(conn), amount=30000, term=36)
        MatchingEngine(conn).run()
        self.assertIn("outside the lender's range 6-12 months", queries.list_pairs(conn)[0]["explanation"])

    def test_07_duplicate_loan_requests(self):
        conn, _ = new_conn()
        b = add_borrower(conn)
        add_request(conn, b, amount=30000, term=12)
        with self.assertRaises(ValidationError):
            add_request(conn, b, amount=30000, term=12)
        add_request(conn, b, amount=30000, term=18)  # different term is fine
        self.assertEqual(len(ps.list_requests(conn)), 2)

    def test_08_large_datasets(self):
        r = evaluate.evaluate(60, 100)
        self.assertEqual(r["constraint_violations"], 0)
        self.assertLess(r["match_seconds"], 30)
        self.assertGreater(r["eligible_matches"], 0)

    def test_09_paid_late_and_defaulted_repayments(self):
        conn, _ = new_conn()
        add_lender(conn, available=500000)
        rids = [add_request(conn, add_borrower(conn), amount=30000, term=12) for _ in range(3)]
        MatchingEngine(conn).run()
        loans = [ls.accept_request(conn, rid)[0] for rid in rids]
        paid, late, default = (ls.simulate_loan(conn, lid, sc) for lid, sc in zip(loans, ("all_paid", "some_late", "default")))
        self.assertEqual((paid["status"], paid["outstanding_balance"]), ("completed", 0.0))
        self.assertEqual((late["status"], late["settled"]), ("completed", 12))
        self.assertEqual(default["status"], "defaulted")
        self.assertGreater(default["outstanding_balance"], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM repayments WHERE status='late'").fetchone()[0], 3)

    def test_10_incorrect_or_missing_profile_information(self):
        conn, _ = new_conn()
        base = {"full_name": "A B", "email": "ab@x.com", "password": "password123", "monthly_income": 1000,
                "existing_obligations": 0, "credit_score": 600, "credit_history_years": 1}
        for bad in ({}, {**base, "credit_score": 1200}, {**base, "monthly_income": -5}, {**base, "email": "nope"},
                    {**base, "full_name": ""}, {**base, "credit_history_years": "abc"}, {**base, "password": "123"}):
            with self.assertRaises(ValidationError):
                ps.register_borrower(conn, bad)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)  # nothing half-saved


class EvaluationMetrics(unittest.TestCase):
    def test_full_funding_metrics(self):
        r = evaluate.evaluate(30, 45)
        self.assertEqual(r["constraint_violations"], 0)
        self.assertEqual(r["explanation_correct_pct"], 100.0)
        self.assertTrue(all(r["consistency_details"].values()), r["consistency_details"])
        self.assertGreaterEqual(r["allocation_success_rate"], 0)

    def test_partial_funding_metrics(self):
        full, partial = evaluate.evaluate(30, 45), evaluate.evaluate(30, 45, partial=True)
        self.assertEqual(partial["constraint_violations"], 0)
        self.assertTrue(all(partial["consistency_details"].values()), partial["consistency_details"])
        self.assertGreaterEqual(partial["requests_matched"], full["requests_matched"])

    def test_runs_are_deterministic(self):
        a, b = evaluate.evaluate(20, 30, seed=5), evaluate.evaluate(20, 30, seed=5)
        for key in ("eligible_matches", "selected_matches", "requests_matched", "loans_created"):
            self.assertEqual(a[key], b[key])


if __name__ == "__main__":
    unittest.main(verbosity=2)
