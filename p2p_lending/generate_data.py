"""Week 7 - generate a large SIMULATED dataset (CSV files and/or database rows).
 python generate_data.py --lenders 50 --borrowers 80 --out data/sample
 python generate_data.py --lenders 50 --borrowers 80 --load # into data/p2p_lending.db
"""
import argparse
import os
import random
import pandas as pd
import database
import profile_service as ps
from models import ValidationError

PASSWORD = "password123"


def generate(n_lenders, n_borrowers, seed=42):
    rng = random.Random(seed)
    lenders, borrowers, requests = [], [], []
    for i in range(1, n_lenders + 1):
        min_loan = rng.choice([5000, 10000, 20000])
        min_return = round(rng.uniform(6, 11) * 2) / 2
        lenders.append({
            "full_name": f"Lender {i:04d}", "email": f"lender{i:04d}@sim.test", "password": PASSWORD,
            "risk_appetite": rng.choices(["low", "medium", "high"], weights=[3, 4, 3])[0],
            "available_amount": rng.randrange(100000, 2000001, 10000), "min_loan_amount": min_loan,
            "max_loan_amount": rng.choice([150000, 300000, 600000]),
            "min_duration_months": rng.choice([3, 6, 12]), "max_duration_months": rng.choice([24, 36, 48, 60]),
            "min_expected_return": min_return,
            "max_expected_return": min(30, min_return + round(rng.uniform(6, 14) * 2) / 2)})
    for i in range(1, n_borrowers + 1):
        income = rng.randrange(20000, 150001, 1000)
        borrowers.append({
            "full_name": f"Borrower {i:04d}", "email": f"borrower{i:04d}@sim.test", "password": PASSWORD,
            "monthly_income": income, "existing_obligations": round(income * rng.uniform(0, 0.5), -2),
            "credit_score": rng.randint(400, 850), "credit_history_years": round(rng.uniform(0.5, 15), 1)})
        used = set()
        for _ in range(rng.choice([1, 1, 1, 2])):
            amount, term = rng.randrange(10000, 400001, 1000), rng.choice([6, 12, 18, 24, 36, 48])
            if (amount, term) not in used:
                used.add((amount, term))
                requests.append({"borrower_index": i, "amount": amount, "term_months": term,
                                 "purpose": rng.choice(["Education", "Medical", "Business", "Home", "Vehicle"])})
    return lenders, borrowers, requests


def write_csv(out_dir, lenders, borrowers, requests):
    os.makedirs(out_dir, exist_ok=True)
    pd.DataFrame(lenders).drop(columns=["password"]).to_csv(os.path.join(out_dir, "sample_lenders.csv"), index=False)
    pd.DataFrame(borrowers).drop(columns=["password"]).to_csv(os.path.join(out_dir, "sample_borrowers.csv"), index=False)
    pd.DataFrame(requests).to_csv(os.path.join(out_dir, "sample_requests.csv"), index=False)


def load(conn, lenders, borrowers, requests):
    """Insert through the validated services. Returns (lender_ids, borrower_ids, request_ids, skipped)."""
    lender_ids = [ps.register_lender(conn, d, auto_activate=True) for d in lenders]
    borrower_ids = [ps.register_borrower(conn, d, auto_activate=True) for d in borrowers]
    request_ids, skipped = [], 0
    for r in requests:
        try:
            request_ids.append(ps.create_loan_request(conn, borrower_ids[r["borrower_index"] - 1], r))
        except ValidationError:
            skipped += 1
    return lender_ids, borrower_ids, request_ids, skipped


def main():
    parser = argparse.ArgumentParser(description="Generate simulated P2P lending data")
    parser.add_argument("--lenders", type=int, default=50)
    parser.add_argument("--borrowers", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=os.path.join("data", "sample"), help="folder for the CSV files")
    parser.add_argument("--load", action="store_true", help="also load the data into the application database")
    args = parser.parse_args()
    lenders, borrowers, requests = generate(args.lenders, args.borrowers, args.seed)
    write_csv(args.out, lenders, borrowers, requests)
    print(f"CSV files written to {args.out}: {len(lenders)} lenders, {len(borrowers)} borrowers, {len(requests)} requests")
    if args.load:
        database.init_db()
        conn = database.get_connection()
        _, _, request_ids, skipped = load(conn, lenders, borrowers, requests)
        conn.close()
        print(f"Loaded into database: {len(request_ids)} requests ({skipped} skipped)")


if __name__ == "__main__":
    main()
