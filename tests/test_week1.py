"""Week 1 tests: run with  python tests/test_week1.py  (or  python -m pytest)"""
import os, sys, sqlite3, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database import init_db, get_connection, list_tables
from seed_data import seed

EXPECTED = {"users", "lenders", "borrowers", "loan_requests", "matches",
            "loans", "repayments", "risk_scores", "audit_logs"}

LENDER_COLS = ("(user_id,risk_appetite,available_amount,min_loan_amount,max_loan_amount,"
               "min_duration_months,max_duration_months,min_expected_return,max_expected_return)")


class Week1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        init_db(self.db)

    def _user(self, c, email, role):
        c.execute("INSERT INTO users(full_name,email,password_hash,role) VALUES ('X',?,'h',?)", (email, role))

    def test_all_nine_tables_exist(self):
        self.assertEqual(set(list_tables(self.db)), EXPECTED)

    def test_init_is_idempotent(self):
        init_db(self.db); init_db(self.db)
        self.assertEqual(set(list_tables(self.db)), EXPECTED)

    def test_seed_data_loads(self):
        seed(self.db)
        c = get_connection(self.db)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM lenders").fetchone()[0], 2)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM loan_requests").fetchone()[0], 2)
        c.close()

    def test_invalid_risk_appetite_rejected(self):
        c = get_connection(self.db); self._user(c, "a@x.com", "lender")
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO lenders" + LENDER_COLS + " VALUES (1,'extreme',1000,100,500,3,12,5,10)")
        c.close()

    def test_negative_amount_rejected(self):
        c = get_connection(self.db); self._user(c, "b@x.com", "borrower")
        c.execute("INSERT INTO borrowers(user_id,monthly_income,credit_score) VALUES (1,1000,700)")
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO loan_requests(borrower_id,amount,term_months) VALUES (1,-5,12)")
        c.close()

    def test_duplicate_open_request_rejected(self):
        c = get_connection(self.db); self._user(c, "b@x.com", "borrower")
        c.execute("INSERT INTO borrowers(user_id,monthly_income,credit_score) VALUES (1,1000,700)")
        c.execute("INSERT INTO loan_requests(borrower_id,amount,term_months) VALUES (1,5000,12)")
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO loan_requests(borrower_id,amount,term_months) VALUES (1,5000,12)")
        c.close()

    def test_duplicate_email_rejected(self):
        c = get_connection(self.db); self._user(c, "a@x.com", "admin")
        with self.assertRaises(sqlite3.IntegrityError):
            self._user(c, "a@x.com", "admin")
        c.close()

    def test_lender_min_cannot_exceed_max(self):
        c = get_connection(self.db); self._user(c, "a@x.com", "lender")
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO lenders" + LENDER_COLS + " VALUES (1,'low',1000,900,100,3,12,5,10)")
        c.close()

    def test_foreign_key_enforced(self):
        c = get_connection(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO loan_requests(borrower_id,amount,term_months) VALUES (999,5000,12)")
        c.close()

    def test_flask_routes(self):
        from app import create_app
        client = create_app(self.db).test_client()
        self.assertEqual(client.get("/health").get_json()["status"], "ok")
        self.assertEqual(client.get("/").status_code, 200)
        self.assertIn("users", client.get("/api/tables").get_json())
        self.assertEqual(client.get("/api/rules").get_json()["score_weights"]["risk_fit"], 40)


if __name__ == "__main__":
    unittest.main(verbosity=2)
