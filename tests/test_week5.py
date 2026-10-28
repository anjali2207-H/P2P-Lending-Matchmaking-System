"""Week 5 tests: loans, schedules, repayment statuses, balances and audit log."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import add_borrower, add_lender, add_request, new_conn
import config
import loan_service as ls
from matching_engine import MatchingEngine
from models import ValidationError

START = date(2026, 1, 31)


def funded_loan(conn, amount=60000, term=12):
    lender = add_lender(conn, available=200000)
    rid = add_request(conn, add_borrower(conn), amount=amount, term=term)
    MatchingEngine(conn).run()
    loan_ids = ls.accept_request(conn, rid, start_date=START)
    return lender, rid, loan_ids[0]


class ScheduleTests(unittest.TestCase):
    def test_schedule_sums_and_balance_reaches_zero(self):
        for principal, rate, months in [(100000, 12, 12), (50000, 9, 36), (12345.67, 20, 7), (5000, 14, 3)]:
            s = ls.build_schedule(principal, rate, months, START)
            self.assertEqual(len(s), months)
            self.assertAlmostEqual(sum(i["principal"] for i in s), principal, places=2)
            self.assertEqual(s[-1]["balance_after"], 0.0)
            self.assertAlmostEqual(sum(i["amount_due"] for i in s), principal + sum(i["interest"] for i in s), places=2)

    def test_month_end_dates(self):
        s = ls.build_schedule(1000, 10, 3, START)
        self.assertEqual([i["due_date"] for i in s], ["2026-02-28", "2026-03-31", "2026-04-30"])


class AcceptTests(unittest.TestCase):
    def test_accept_creates_loan_schedule_and_updates_funds(self):
        conn, _ = new_conn()
        lender, rid, loan_id = funded_loan(conn)
        loan = ls.get_loan(conn, loan_id)
        self.assertEqual((loan["principal"], loan["duration_months"], loan["status"]), (60000, 12, "active"))
        self.assertEqual(loan["outstanding_balance"], 60000)
        self.assertIn(loan["interest_rate"], config.RATE_BY_RISK.values())
        self.assertEqual(len(ls.get_repayments(conn, loan_id)), 12)
        self.assertEqual(conn.execute("SELECT available_amount FROM lenders").fetchone()[0], 140000)
        self.assertEqual(conn.execute("SELECT status FROM loan_requests").fetchone()[0], "funded")
        self.assertEqual(conn.execute("SELECT status FROM matches WHERE status='accepted'").fetchone()[0], "accepted")

    def test_cannot_accept_twice_or_unmatched(self):
        conn, _ = new_conn()
        lender, rid, loan_id = funded_loan(conn)
        with self.assertRaises(ValidationError):
            ls.accept_request(conn, rid)
        with self.assertRaises(ValidationError):
            ls.accept_request(conn, 999)

    def test_cannot_allocate_beyond_available_funds(self):
        conn, _ = new_conn()
        lender = add_lender(conn, available=100000)
        rid = add_request(conn, add_borrower(conn), amount=60000)
        MatchingEngine(conn).run()
        conn.execute("UPDATE lenders SET available_amount = 10000")  # lender spent money elsewhere
        conn.commit()
        with self.assertRaises(ValidationError):
            ls.accept_request(conn, rid)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0], 0)  # nothing half-created
        self.assertEqual(conn.execute("SELECT status FROM loan_requests").fetchone()[0], "matched")

    def test_cofunded_request_creates_one_loan_per_lender(self):
        conn, _ = new_conn()
        add_lender(conn, available=60000)
        add_lender(conn, available=60000)
        rid = add_request(conn, add_borrower(conn), amount=100000)
        MatchingEngine(conn, allow_partial=True).run()
        ids = ls.accept_request(conn, rid, start_date=START)
        self.assertEqual(len(ids), 2)
        self.assertEqual(sum(ls.get_loan(conn, i)["principal"] for i in ids), 100000)


class RepaymentTests(unittest.TestCase):
    def setUp(self):
        self.conn, _ = new_conn()
        self.lender, self.rid, self.loan_id = funded_loan(self.conn)
        self.reps = ls.get_repayments(self.conn, self.loan_id)

    def test_paid_instalment_reduces_balance(self):
        ls.mark_installment(self.conn, self.reps[0]["repayment_id"], "paid")
        loan = ls.get_loan(self.conn, self.loan_id)
        expected = ls.build_schedule(60000, loan["interest_rate"], 12, START)[0]["balance_after"]
        self.assertEqual(loan["outstanding_balance"], expected)
        self.assertEqual(loan["status"], "active")
        rep = ls.get_repayments(self.conn, self.loan_id)[0]
        self.assertEqual((rep["status"], rep["amount_paid"]), ("paid", rep["amount_due"]))

    def test_late_instalment_adds_fee(self):
        ls.mark_installment(self.conn, self.reps[0]["repayment_id"], "late")
        rep = ls.get_repayments(self.conn, self.loan_id)[0]
        fee = round(rep["amount_due"] * config.LATE_FEE_RATE, 2)
        self.assertEqual(rep["amount_paid"], round(rep["amount_due"] + fee, 2))
        self.assertGreater(rep["paid_date"], rep["due_date"])

    def test_default_stops_loan(self):
        ls.mark_installment(self.conn, self.reps[0]["repayment_id"], "paid")
        ls.mark_installment(self.conn, self.reps[1]["repayment_id"], "defaulted")
        statuses = [r["status"] for r in ls.get_repayments(self.conn, self.loan_id)]
        self.assertEqual(statuses, ["paid"] + ["defaulted"] * 11)
        loan = ls.get_loan(self.conn, self.loan_id)
        self.assertEqual(loan["status"], "defaulted")
        self.assertGreater(loan["outstanding_balance"], 0)

    def test_all_paid_completes_loan(self):
        loan = ls.simulate_loan(self.conn, self.loan_id, "all_paid")
        self.assertEqual((loan["status"], loan["outstanding_balance"], loan["settled"]), ("completed", 0.0, 12))

    def test_rules_are_enforced(self):
        with self.assertRaises(ValidationError):  # must pay in order
            ls.mark_installment(self.conn, self.reps[1]["repayment_id"], "paid")
        ls.mark_installment(self.conn, self.reps[0]["repayment_id"], "paid")
        with self.assertRaises(ValidationError):  # cannot change twice
            ls.mark_installment(self.conn, self.reps[0]["repayment_id"], "late")
        with self.assertRaises(ValidationError):
            ls.mark_installment(self.conn, self.reps[1]["repayment_id"], "unknown")

    def test_every_status_change_is_audited(self):
        ls.simulate_loan(self.conn, self.loan_id, "some_late")
        changes = self.conn.execute("SELECT COUNT(*) FROM audit_logs WHERE entity_type='repayment'").fetchone()[0]
        self.assertEqual(changes, 12)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='LOAN_CREATED'").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT new_value FROM audit_logs WHERE entity_type='loan' AND "
                                           "action='STATUS_CHANGE'").fetchone()[0].split(" |")[0], "completed")

    def test_random_simulation_is_reproducible_and_consistent(self):
        a = ls.simulate_loan(self.conn, self.loan_id, "random", seed=7)
        conn2, _ = new_conn()
        _, _, loan2 = funded_loan(conn2)
        b = ls.simulate_loan(conn2, loan2, "random", seed=7)
        self.assertEqual((a["status"], a["settled"]), (b["status"], b["settled"]))
        paid_principal = sum(i["principal"] for i in ls.build_schedule(60000, a["interest_rate"], 12, START)[:a["settled"]])
        self.assertAlmostEqual(a["outstanding_balance"], 60000 - paid_principal if a["status"] != "completed" else 0, places=1)


class WebTests(unittest.TestCase):
    def test_screens(self):
        from app import create_app
        conn, path = new_conn()
        _, rid, loan_id = funded_loan(conn)
        conn.close()
        client = create_app(path).test_client()
        for url in ("/loans", "/loans/pending", f"/loans/{loan_id}", "/scoring/pairs", "/scoring/risk",
                    "/matching/recommendations"):
            self.assertEqual(client.get(url).status_code, 200, url)
        r = client.post(f"/loans/{loan_id}/simulate?scenario=all_paid", follow_redirects=True)
        self.assertIn(b"completed", r.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
