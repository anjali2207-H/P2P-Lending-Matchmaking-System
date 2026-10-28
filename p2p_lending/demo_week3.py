"""Week 3 demo: risk scores, hard-constraint rejections and match explanations."""
import demo_data
import queries
import scoring

conn = demo_data.fresh_demo_db()
summary = scoring.score_all(conn)
print("Scoring summary:", summary)

print("\n=== Borrower risk scores ===")
for r in queries.list_risk_scores(conn):
    print(f"Request #{r['request_id']} {r['borrower']:<12} amount={r['amount']:>9,.0f} "
          f"score={r['score']:>6} -> {r['risk_category'].upper()}")

print("\n=== Eligible lender candidates per request (best first) ===")
for p in queries.list_pairs(conn, status="recommended"):
    print(f"Request #{p['request_id']} {p['borrower']:<12} <- {p['lender']:<19} score={p['score']:>6} "
          f"(risk {p['risk_fit']} + amount {p['amount_fit']} + term {p['term_fit']} + return {p['return_fit']})")

print("\n=== Why were pairs rejected? (request #4 - Anita Das) ===")
for p in queries.list_pairs(conn, status="rejected", request_id=4)[:2]:
    print(f"{p['lender']}: {p['explanation']}")

print("\n=== Example explanation of a recommendation ===")
best = queries.list_pairs(conn, status="recommended", request_id=3)[0]
print(best["explanation"])

print("\n=== Example risk explanation ===")
print(queries.list_risk_scores(conn)[0]["explanation"])

conn.close()
