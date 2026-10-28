"""Week 5 demo: accept matches, instalment schedules, paid / late / defaulted cases."""
from datetime import date
import demo_data
import loan_service as ls
from matching_engine import MatchingEngine

conn = demo_data.fresh_demo_db()
print("Matching:", MatchingEngine(conn).run())
loan_ids, errors = ls.accept_all(conn, start_date=date(2026, 1, 15))
print(f"\nAccepted matches -> {len(loan_ids)} loans created. Errors: {errors}")

print("\n=== Loans ===")
for l in ls.list_loans(conn):
    print(f"Loan #{l['loan_id']} {l['lender']:<19} -> {l['borrower']:<12} principal={l['principal']:>9,.0f} "
          f"rate={l['interest_rate']:g}% months={l['duration_months']:>2} outstanding={l['outstanding_balance']:>9,.0f}")

print("\n=== First 4 instalments of loan #1 ===")
for r in ls.get_repayments(conn, 1)[:4]:
    print(f" #{r['installment_no']} due {r['due_date']} amount {r['amount_due']:>9,.2f} [{r['status']}]")

print("\n=== Loan 1: all instalments paid ===")
print(ls.simulate_loan(conn, 1, "all_paid"))

print("\n=== Loan 2: some instalments late ===")
l2 = ls.simulate_loan(conn, 2, "some_late")
print({k: l2[k] for k in ("loan_id", "status", "outstanding_balance", "settled")})
print([(r["installment_no"], r["status"], r["amount_paid"]) for r in ls.get_repayments(conn, 2)[:4]])

print("\n=== Loan 3: borrower defaults halfway ===")
l3 = ls.simulate_loan(conn, 3, "default")
print({k: l3[k] for k in ("loan_id", "status", "outstanding_balance", "settled")})
print(sorted({r["status"] for r in ls.get_repayments(conn, 3)}))

print("\n=== Lender funds after loans were created ===")
for r in conn.execute("SELECT l.lender_id, u.full_name, l.available_amount FROM lenders l JOIN users u ON u.user_id=l.user_id"):
    print(f" {r[1]:<19} available now {r[2]:>10,.0f}")

print("\n=== Audit log (last 6 entries) ===")
for r in conn.execute("SELECT entity_type, entity_id, action, old_value, new_value FROM audit_logs ORDER BY log_id DESC LIMIT 6"):
    print(" ", tuple(r))
print("Total audit entries:", conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0])
conn.close()
