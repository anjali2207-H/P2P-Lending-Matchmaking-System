"""Week 6 tests: dashboards, REST API integration, downloadable reports."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import add_borrower, add_lender, add_request, new_conn
import loan_service as ls
from app import create_app
from matching_engine import MatchingEngine


def world():
    conn, path = new_conn()
    lender = add_lender(conn, available=300000)
    borrower = add_borrower(conn)
    rid = add_request(conn, borrower, amount=60000, term=12)
    MatchingEngine(conn).run()
    loan_id = ls.accept_request(conn, rid)[0]
    ls.simulate_loan(conn, loan_id, "some_late")
    conn.close()
    return create_app(path).test_client(), lender, borrower, loan_id


class DashboardTests(unittest.TestCase):
    def test_all_dashboards_and_screens_open(self):
        client, lender, borrower, loan_id = world()
        for url in ("/admin", f"/lender/{lender}", f"/borrower/{borrower}", "/reports/audit",
                    "/reports/audit?entity_type=loan", "/loans", f"/loans/{loan_id}"):
            self.assertEqual(client.get(url).status_code, 200, url)
        self.assertEqual(client.get("/lender/999").status_code, 404)
        self.assertEqual(client.get("/borrower/999").status_code, 404)
        self.assertIn(b"Administrator dashboard", client.get("/admin").data)

    def test_downloads(self):
        client, *_ = world()
        self.assertIn(b"loan_id", client.get("/reports/loans.csv").data)
        self.assertEqual(client.get("/reports/loans.xlsx").data[:2], b"PK")  # xlsx is a zip file
        self.assertEqual(client.get("/reports/summary.pdf").data[:4], b"%PDF")


class ApiTests(unittest.TestCase):
    def test_full_flow_through_rest_api(self):
        conn, path = new_conn()
        conn.close()
        c = create_app(path).test_client()
        lender = {"full_name": "Api Lender", "email": "al@x.com", "password": "password123", "risk_appetite": "medium",
                  "available_amount": 200000, "min_loan_amount": 5000, "max_loan_amount": 100000,
                  "min_duration_months": 6, "max_duration_months": 36, "min_expected_return": 8, "max_expected_return": 22}
        borrower = {"full_name": "Api Borrower", "email": "ab@x.com", "password": "password123", "monthly_income": 60000,
                    "existing_obligations": 5000, "credit_score": 720, "credit_history_years": 5}
        self.assertEqual(c.post("/api/lenders", json=lender).status_code, 201)
        self.assertEqual(c.post("/api/borrowers", json=borrower).status_code, 201)
        self.assertEqual(c.post("/api/profiles/lender/1/status", json={"status": "active"}).status_code, 200)
        self.assertEqual(c.post("/api/profiles/borrower/1/status", json={"status": "active"}).status_code, 200)
        r = c.post("/api/requests", json={"borrower_id": 1, "amount": 50000, "term_months": 12})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(c.post("/api/requests", json={"borrower_id": 1, "amount": 50000, "term_months": 12}).status_code, 400)
        self.assertEqual(c.post("/api/scoring/run").get_json()["eligible"], 1)
        self.assertEqual(c.post("/api/matching/run", json={}).get_json()["requests_matched"], 1)
        self.assertEqual(len(c.get("/api/matches?status=recommended").get_json()), 1)
        self.assertEqual(c.post("/api/loans/accept/1").get_json()["loan_ids"], [1])
        self.assertEqual(c.post("/api/loans/1/simulate", json={"scenario": "all_paid"}).get_json()["status"], "completed")
        self.assertEqual(len(c.get("/api/loans/1/repayments").get_json()), 12)
        self.assertEqual(c.get("/api/loans/99/repayments").status_code, 404)
        self.assertEqual(c.get("/api/stats").get_json()["Funded requests"], 1)

    def test_validation_errors_are_json(self):
        conn, path = new_conn()
        conn.close()
        r = create_app(path).test_client().post("/api/lenders", json={"full_name": "x"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "validation_failed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
