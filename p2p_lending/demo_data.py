"""Hand-made demo dataset (simulated people) used by the weekly demo scripts.
Loaded through the SAME validated services the web forms use, so the demo
also proves that registration works. Run python demo_data.py to load the
data into the real application database (data/p2p_lending.db).
"""
import os
import config
import database
import profile_service as ps

PASSWORD = "password123"

LENDERS = [
    # name, email, appetite, available, min_loan, max_loan, min_m, max_m, min_ret, max_ret
    ("Conservative Carla", "carla@p2p.test", "low", 300000, 10000, 150000, 6, 36, 7, 11),
    ("Balanced Bala", "bala@p2p.test", "medium", 250000, 5000, 200000, 6, 48, 9, 15),
    ("Aggressive Arjun", "arjun@p2p.test", "high", 250000, 5000, 300000, 3, 60, 12, 22),
    ("Small Sita", "sita@p2p.test", "medium", 20000, 2000, 30000, 3, 24, 9, 16),
    ("Cohort Chitra", "chitra@p2p.test", "high", 100000, 50000, 300000, 12, 60, 12, 22),
]

BORROWERS = [
    # name, email, income, obligations, credit, history_years
    ("Ravi Kumar", "ravi@p2p.test", 60000, 8000, 780, 6),
    ("Meena Iyer", "meena@p2p.test", 25000, 9000, 540, 1.5),
    ("Sunil Verma", "sunil@p2p.test", 45000, 12000, 650, 3),
    ("Anita Das", "anita@p2p.test", 30000, 18000, 600, 2),
    ("Kiran Rao", "kiran@p2p.test", 90000, 5000, 820, 10),
    ("Pooja Nair", "pooja@p2p.test", 35000, 6000, 700, 4),
]

REQUESTS = [
    # borrower index (1-based), amount, term, purpose
    (1, 50000, 12, "Education"),
    (2, 20000, 6, "Medical"),
    (3, 80000, 24, "Home renovation"),
    (4, 40000, 12, "Business"),
    (5, 15000, 12, "Vehicle repair"),
    (5, 120000, 36, "Home loan top-up"),
    (6, 280000, 48, "Start-up capital"),
]


def load_demo_data(conn):
    """Insert the demo dataset; returns (lender_ids, borrower_ids, request_ids)."""
    # Ensure default admin account is present
    if not conn.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone():
        from werkzeug.security import generate_password_hash
        conn.execute("INSERT INTO users(full_name, email, password_hash, role, status) VALUES (?, ?, ?, ?, 'active')",
                     ("Administrator", "admin@p2p.test", generate_password_hash(PASSWORD), "admin"))
    lender_ids = []
    for name, email, appetite, avail, lo, hi, mn, mx, rmin, rmax in LENDERS:
        lender_ids.append(ps.register_lender(conn, {
            "full_name": name, "email": email, "password": PASSWORD, "risk_appetite": appetite,
            "available_amount": avail, "min_loan_amount": lo, "max_loan_amount": hi,
            "min_duration_months": mn, "max_duration_months": mx,
            "min_expected_return": rmin, "max_expected_return": rmax}, auto_activate=True))
    borrower_ids = []
    for name, email, income, obligations, credit, years in BORROWERS:
        borrower_ids.append(ps.register_borrower(conn, {
            "full_name": name, "email": email, "password": PASSWORD, "monthly_income": income,
            "existing_obligations": obligations, "credit_score": credit,
            "credit_history_years": years}, auto_activate=True))
    request_ids = []
    for index, amount, term, purpose in REQUESTS:
        request_ids.append(ps.create_loan_request(conn, borrower_ids[index - 1], {
            "amount": amount, "term_months": term, "purpose": purpose}))
    return lender_ids, borrower_ids, request_ids


def fresh_demo_db(path=None):
    """Create a brand-new demo database file, load the demo data, return a connection."""
    path = path or os.path.join(config.BASE_DIR, "data", "demo.db")
    if os.path.exists(path):
        os.remove(path)
    database.init_db(path)
    conn = database.get_connection(path)
    load_demo_data(conn)
    return conn


if __name__ == "__main__":
    database.init_db()
    connection = database.get_connection()
    if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        print("The application database already contains users - nothing loaded.")
        print("Delete data/p2p_lending.db first if you want a clean start.")
    else:
        load_demo_data(connection)
        print("Demo data loaded into", config.DATABASE_PATH)
    connection.close()
