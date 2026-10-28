"""Week 6 demo: drives the whole system through the Flask REST API (uses data/demo6.db)."""
import os
import config
import demo_data
from app import create_app

path = os.path.join(config.BASE_DIR, "data", "demo6.db")
if os.path.exists(path):
    os.remove(path)
client = create_app(path).test_client()  # create_app builds the empty database


def show(title, response):
    print(f"{title:<42} -> HTTP {response.status_code}")
    return response


import database
conn = database.get_connection(path)
demo_data.load_demo_data(conn)
conn.close()

print("--- REST API walk-through ---")
print(show("GET /api/stats", client.get("/api/stats")).get_json())
print(show("POST /api/matching/run", client.post("/api/matching/run", json={})).get_json())
for rid in (1, 2, 3):
    print(show(f"POST /api/loans/accept/{rid}", client.post(f"/api/loans/accept/{rid}")).get_json())
print(show("POST /api/loans/1/simulate (default)", client.post("/api/loans/1/simulate", json={"scenario": "default"})).get_json()["status"])
bad = show("POST /api/lenders (invalid)", client.post("/api/lenders", json={"full_name": "x"}))
print(bad.get_json()["messages"][:2])

print("\n--- Screens ---")
for url in ("/", "/admin", "/lender/1", "/borrower/1", "/reports/audit", "/loans", "/loans/1", "/scoring/pairs",
            "/scoring/risk", "/matching/recommendations", "/loans/pending", "/lenders", "/borrowers", "/requests"):
    show("GET " + url, client.get(url))

for url in ("/reports/loans.csv", "/reports/loans.xlsx", "/reports/summary.pdf"):
    r = show("GET " + url, client.get(url))
    print(f" downloaded {len(r.data):,} bytes ({r.mimetype})")
