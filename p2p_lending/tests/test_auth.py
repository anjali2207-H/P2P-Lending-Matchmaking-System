"""Authentication, session management, and role-based redirect tests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import demo_data
from app import create_app


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.conn = demo_data.fresh_demo_db()
        self.conn.close()
        self.app = create_app()
        self.client = self.app.test_client()

    def test_login_page_renders(self):
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Sign In", res.data)
        self.assertIn(b"Quick Demo Login", res.data)

    def test_admin_login_success(self):
        res = self.client.post("/login", data={"email": "admin@p2p.test", "password": "password123"})
        self.assertEqual(res.status_code, 302)
        self.assertIn("/admin", res.headers["Location"])

    def test_lender_login_success(self):
        res = self.client.post("/login", data={"email": "carla@p2p.test", "password": "password123"})
        self.assertEqual(res.status_code, 302)
        self.assertIn("/lender/", res.headers["Location"])

    def test_borrower_login_success(self):
        res = self.client.post("/login", data={"email": "ravi@p2p.test", "password": "password123"})
        self.assertEqual(res.status_code, 302)
        self.assertIn("/borrower/", res.headers["Location"])

    def test_invalid_login_rejected(self):
        res = self.client.post("/login", data={"email": "carla@p2p.test", "password": "wrongpassword"})
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Invalid email or password", res.data)

    def test_quick_demo_login_admin(self):
        res = self.client.get("/login?demo=admin")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/admin", res.headers["Location"])

    def test_quick_demo_login_lender(self):
        res = self.client.get("/login?demo=lender")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/lender/", res.headers["Location"])

    def test_logout(self):
        # First log in
        self.client.get("/login?demo=admin")
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("role"), "admin")
        # Then logout
        res = self.client.get("/logout")
        self.assertEqual(res.status_code, 302)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("role"))

    def test_my_dashboard_unauthenticated(self):
        res = self.client.get("/my-dashboard")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers["Location"])

    def test_my_dashboard_authenticated(self):
        self.client.get("/login?demo=lender")
        res = self.client.get("/my-dashboard")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/lender/", res.headers["Location"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
