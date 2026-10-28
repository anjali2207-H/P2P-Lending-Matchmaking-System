"""Inserts a small sample dataset (simulated data only) to test the Week 1 schema."""
from werkzeug.security import generate_password_hash
from database import get_connection, init_db


def seed(db_path=None):
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            print("Sample data already present - skipping.")
            return
        pw = generate_password_hash("password123")
        users = [
            ("Admin User", "admin@p2p.test", "admin"),
            ("Lender One", "lender1@p2p.test", "lender"),
            ("Lender Two", "lender2@p2p.test", "lender"),
            ("Borrower One", "borrower1@p2p.test", "borrower"),
            ("Borrower Two", "borrower2@p2p.test", "borrower"),
        ]
        for name, email, role in users:
            conn.execute("INSERT INTO users(full_name,email,password_hash,role) VALUES (?,?,?,?)",
                         (name, email, pw, role))
        # lenders: user_id, appetite, available, min/max loan, min/max months, min/max return %
        conn.execute("INSERT INTO lenders(user_id,risk_appetite,available_amount,min_loan_amount,max_loan_amount,"
                     "min_duration_months,max_duration_months,min_expected_return,max_expected_return,profile_status)"
                     " VALUES (2,'low',200000,5000,100000,6,36,7,12,'active')")
        conn.execute("INSERT INTO lenders(user_id,risk_appetite,available_amount,min_loan_amount,max_loan_amount,"
                     "min_duration_months,max_duration_months,min_expected_return,max_expected_return,profile_status)"
                     " VALUES (3,'high',500000,2000,200000,3,60,10,24,'active')")
        # borrowers: user_id, income, obligations, credit score, history years
        conn.execute("INSERT INTO borrowers(user_id,monthly_income,existing_obligations,credit_score,"
                     "credit_history_years,profile_status) VALUES (4,60000,8000,780,6,'active')")
        conn.execute("INSERT INTO borrowers(user_id,monthly_income,existing_obligations,credit_score,"
                     "credit_history_years,profile_status) VALUES (5,25000,9000,540,1.5,'active')")
        conn.execute("INSERT INTO loan_requests(borrower_id,amount,term_months,purpose) VALUES (1,50000,12,'Education')")
        conn.execute("INSERT INTO loan_requests(borrower_id,amount,term_months,purpose) VALUES (2,20000,6,'Medical')")
        conn.execute("INSERT INTO audit_logs(entity_type,entity_id,action,new_value,actor)"
                     " VALUES ('system',NULL,'SEED_DATA_LOADED','5 users, 2 lenders, 2 borrowers, 2 requests','system')")
        conn.commit()
        print("Sample data inserted.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
