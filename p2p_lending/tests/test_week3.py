"""Week 3 tests: risk scoring, hard constraints, compatibility scores, stored explanations."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import demo_data
import queries
import scoring
from models import Borrower, Lender, LoanRequest


def lender(**kw):
    base = dict(full_name="Len Der", email="l@x.com", risk_appetite="medium", available_amount=100000,
                min_loan_amount=5000, max_loan_amount=80000, min_duration_months=6, max_duration_months=24,
                min_expected_return=9, max_expected_return=15, profile_status="active")
    base.update(kw)
    return Lender(**base)


def borrower(**kw):
    base = dict(full_name="Bor Rower", email="b@x.com", monthly_income=60000, existing_obligations=6000,
                credit_score=700, credit_history_years=5, profile_status="active")
    base.update(kw)
    return Borrower(**base)


def request(amount=30000, term=12):
    return LoanRequest(1, amount, term)


class RiskTests(unittest.TestCase):
    def test_classes_and_weights(self):
        self.assertEqual(sum(config.RISK_SCORE_WEIGHTS.values()), 100)
        s = scoring.RiskScorer()
        self.assertEqual(s.classify(70), "low")
        self.assertEqual(s.classify(69.99), "medium")
        self.assertEqual(s.classify(45), "medium")
        self.assertEqual(s.classify(44.99), "high")

    def test_better_borrower_scores_higher(self):
        s = scoring.RiskScorer()
        good = s.score(borrower(credit_score=820, existing_obligations=1000, credit_history_years=10), request())
        bad = s.score(borrower(credit_score=450, existing_obligations=30000, credit_history_years=0.5), request())
        self.assertGreater(good.score, bad.score)
        self.assertEqual((good.category, bad.category), ("low", "high"))
        self.assertTrue(0 <= bad.score <= good.score <= 100)

    def test_components_add_up(self):
        r = scoring.RiskScorer().score(borrower(), request())
        self.assertAlmostEqual(sum(r.components.values()), r.score, places=1)
        self.assertIn("Offered interest rate", r.explanation)


class ConstraintTests(unittest.TestCase):
    def codes(self, l=None, b=None, r=None, partial=False, category="medium"):
        l, b, r = l or lender(), b or borrower(), r or request()
        risk = scoring.RiskResult(60, category, {}, "", config.RATE_BY_RISK[category])
        return scoring.CompatibilityScorer(partial).evaluate(l, b, r, risk).violation_codes

    def test_ok_pair_has_no_violations(self):
        self.assertEqual(self.codes(), [])

    def test_risk_appetite_mismatch(self):
        self.assertIn("RISK_APPETITE", self.codes(l=lender(risk_appetite="low")))

    def test_amount_outside_lender_range(self):
        self.assertIn("AMOUNT_RANGE", self.codes(r=request(amount=90000)))

    def test_loan_exceeds_available_funds_and_partial_mode(self):
        small = lender(available_amount=20000)
        self.assertIn("INSUFFICIENT_FUNDS", self.codes(l=small))
        self.assertNotIn("INSUFFICIENT_FUNDS", self.codes(l=small, partial=True))  # 20000 >= 20% of 30000

    def test_term_mismatch(self):
        self.assertIn("DURATION_RANGE", self.codes(r=request(term=48)))

    def test_return_range_mismatch(self):
        self.assertIn("RETURN_RANGE", self.codes(l=lender(min_expected_return=15, max_expected_return=18)))

    def test_affordability(self):
        self.assertIn("AFFORDABILITY", self.codes(b=borrower(existing_obligations=35000)))

    def test_inactive_profiles(self):
        self.assertIn("LENDER_INACTIVE", self.codes(l=lender(profile_status="pending")))
        self.assertIn("BORROWER_INACTIVE", self.codes(b=borrower(profile_status="inactive")))

    def test_multiple_violations_are_all_reported(self):
        codes = self.codes(l=lender(risk_appetite="low"), r=request(amount=90000, term=48))
        self.assertTrue({"RISK_APPETITE", "AMOUNT_RANGE", "DURATION_RANGE"} <= set(codes))


class CompatibilityTests(unittest.TestCase):
    def evaluate(self, l, category="medium"):
        risk = scoring.RiskResult(60, category, {}, "", config.RATE_BY_RISK[category])
        return scoring.CompatibilityScorer().evaluate(l, borrower(), request(), risk)

    def test_score_is_sum_of_components(self):
        r = self.evaluate(lender())
        self.assertTrue(r.eligible)
        self.assertAlmostEqual(r.score, r.risk_fit + r.amount_fit + r.term_fit + r.return_fit, places=1)
        self.assertTrue(0 < r.score <= 100)

    def test_exact_risk_match_beats_looser_appetite(self):
        exact = self.evaluate(lender(risk_appetite="medium"))
        loose = self.evaluate(lender(risk_appetite="high"))
        self.assertGreater(exact.risk_fit, loose.risk_fit)
        self.assertEqual(exact.risk_fit, config.SCORE_WEIGHTS["risk_fit"])

    def test_explanations_present(self):
        self.assertTrue(self.evaluate(lender()).explanation.startswith("ELIGIBLE"))
        self.assertTrue(self.evaluate(lender(risk_appetite="low")).explanation.startswith("REJECTED"))


class StoredScoringTests(unittest.TestCase):
    def setUp(self):
        self.conn = demo_data.fresh_demo_db(os.path.join(config.BASE_DIR, "data", "test_w3.db"))

    def tearDown(self):
        self.conn.close()

    def test_every_pair_is_stored_with_explanation(self):
        s = scoring.score_all(self.conn)
        self.assertEqual(s["pairs"], 35)
        self.assertEqual(s["eligible"] + s["rejected"], 35)
        rows = queries.list_pairs(self.conn)
        self.assertEqual(len(rows), 35)
        self.assertTrue(all(r["explanation"] for r in rows))
        self.assertTrue(all(r["score"] == 0 for r in rows if r["status"] == "rejected"))

    def test_risk_scores_stored_with_json_components(self):
        scoring.score_all(self.conn)
        row = self.conn.execute("SELECT * FROM risk_scores WHERE request_id = 1").fetchone()
        self.assertEqual(row["risk_category"], "low")
        self.assertEqual(set(json.loads(row["components"])), {"credit", "dti", "history", "loan_to_income"})

    def test_no_compatible_lender_for_unaffordable_request(self):
        scoring.score_all(self.conn)
        self.assertEqual(queries.list_pairs(self.conn, status="recommended", request_id=4), [])

    def test_rerun_does_not_duplicate(self):
        scoring.score_all(self.conn)
        scoring.score_all(self.conn)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 35)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM risk_scores").fetchone()[0], 7)

    def test_partial_mode_creates_extra_candidates(self):
        full = scoring.score_all(self.conn)["eligible"]
        partial = scoring.score_all(self.conn, allow_partial=True)["eligible"]
        self.assertGreater(partial, full)


if __name__ == "__main__":
    unittest.main(verbosity=2)
