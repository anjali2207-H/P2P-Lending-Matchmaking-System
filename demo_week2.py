"""Week 2 demo: profiles, validation and status tracking (uses data/demo.db)."""
import demo_data
import profile_service as ps
from models import ValidationError


def show(title):
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)


conn = demo_data.fresh_demo_db()

show("1. Registered lenders")
for l in ps.list_lenders(conn):
    print(f"#{l.lender_id} {l.full_name:<20} appetite={l.risk_appetite:<6} available={l.available_amount:>10,.0f} "
          f"loans {l.min_loan_amount:,.0f}-{l.max_loan_amount:,.0f} {l.min_duration_months}-{l.max_duration_months}m "
          f" return {l.min_expected_return:g}-{l.max_expected_return:g}% [{l.profile_status}]")

show("2. Registered borrowers")
for b in ps.list_borrowers(conn):
    print(f"#{b.borrower_id} {b.full_name:<14} income={b.monthly_income:>8,.0f} obligations={b.existing_obligations:>7,.0f} "
          f"credit={b.credit_score} history={b.credit_history_years}y DTI={b.debt_to_income():.0%} [{b.profile_status}]")

show("3. Loan requests")
for r in ps.list_requests(conn):
    print(f"#{r['request_id']} {r['borrower']:<14} amount={r['amount']:>9,.0f} term={r['term_months']}m "
          f"purpose={r['purpose']:<16} [{r['status']}]")

show("4. Validation rejects wrong data")
bad_cases = {
    "missing name + invalid email": {"full_name": "", "email": "not-an-email", "password": "password123",
                                     "risk_appetite": "low", "available_amount": 1000, "min_loan_amount": 1000, "max_loan_amount": 5000,
                                     "min_duration_months": 3, "max_duration_months": 12, "min_expected_return": 5, "max_expected_return": 9},
    "unknown risk appetite": {"full_name": "Test Lender", "email": "t1@p2p.test", "password": "password123",
                              "risk_appetite": "extreme", "available_amount": 1000, "min_loan_amount": 1000, "max_loan_amount": 5000,
                              "min_duration_months": 3, "max_duration_months": 12, "min_expected_return": 5, "max_expected_return": 9},
    "min duration above max": {"full_name": "Test Lender", "email": "t2@p2p.test", "password": "password123",
                               "risk_appetite": "low", "available_amount": 1000, "min_loan_amount": 1000, "max_loan_amount": 5000,
                               "min_duration_months": 24, "max_duration_months": 12, "min_expected_return": 5, "max_expected_return": 9},
    "text in a number field": {"full_name": "Test Lender", "email": "t3@p2p.test", "password": "password123",
                               "risk_appetite": "low", "available_amount": "lots", "min_loan_amount": 1000, "max_loan_amount": 5000,
                               "min_duration_months": 3, "max_duration_months": 12, "min_expected_return": 5, "max_expected_return": 9},
    "duplicate email": {"full_name": "Another Carla", "email": "carla@p2p.test", "password": "password123",
                        "risk_appetite": "low", "available_amount": 1000, "min_loan_amount": 1000, "max_loan_amount": 5000,
                        "min_duration_months": 3, "max_duration_months": 12, "min_expected_return": 5, "max_expected_return": 9},
}
for label, payload in bad_cases.items():
    try:
        ps.register_lender(conn, payload)
        print(f"- {label}: ACCEPTED (unexpected!)")
    except ValidationError as exc:
        print(f"- {label}: rejected -> {exc.errors[0]}")

try:
    ps.create_loan_request(conn, 1, {"amount": 50000, "term_months": 12})
except ValidationError as exc:
    print(f"- duplicate loan request: rejected -> {exc.errors[0]}")

show("5. Profile-status tracking (pending -> active -> inactive)")
new_id = ps.register_lender(conn, {"full_name": "Pending Pia", "email": "pia@p2p.test", "password": "password123",
                                   "risk_appetite": "medium", "available_amount": 50000, "min_loan_amount": 5000, "max_loan_amount": 40000,
                                   "min_duration_months": 6, "max_duration_months": 24, "min_expected_return": 8, "max_expected_return": 14})
print("registered lender status :", ps.get_lender(conn, new_id).profile_status)
ps.set_profile_status(conn, "lender", new_id, "active")
print("after approval           :", ps.get_lender(conn, new_id).profile_status)
ps.set_profile_status(conn, "lender", new_id, "inactive")
print("after deactivation       :", ps.get_lender(conn, new_id).profile_status)
try:
    ps.set_profile_status(conn, "lender", new_id, "rejected")
except ValidationError as exc:
    print("illegal move inactive->rejected blocked:", exc.errors[0])

show("6. Audit trail (last 5 entries)")
for row in conn.execute("SELECT entity_type, entity_id, action, old_value, new_value FROM audit_logs "
                        "ORDER BY log_id DESC LIMIT 5"):
    print(tuple(row))
conn.close()
