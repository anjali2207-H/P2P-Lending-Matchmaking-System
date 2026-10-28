"""Week 4 demo: weighted bipartite graph, ranking and allocation (uses data/demo.db)."""
import demo_data
import queries
from matching_engine import MatchingEngine


def run(partial):
    conn = demo_data.fresh_demo_db()
    engine = MatchingEngine(conn, allow_partial=partial)
    summary = engine.run()
    print("Summary:", summary)
    g = engine.graph
    print(f"Graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} weighted edges")
    print("\nTop-ranked edges:")
    for lender_node, request_node, d in engine.rank_edges(g)[:5]:
        print(f" {g.nodes[lender_node]['name']:<19} -- {d['weight']:>6} --> request {request_node} "
              f"({g.nodes[request_node]['name']})")
    print("\nRecommended matches:")
    for r in queries.list_pairs(conn, status="recommended"):
        if r["allocated_amount"] > 0:
            print(f" Request #{r['request_id']} {r['borrower']:<12} <- {r['lender']:<19} "
                  f"allocated {r['allocated_amount']:>10,.2f} score {r['score']}")
    print("\nRequests left without a match:")
    for r in conn.execute("SELECT r.request_id, u.full_name FROM loan_requests r JOIN borrowers b ON "
                          "b.borrower_id=r.borrower_id JOIN users u ON u.user_id=b.user_id "
                          "WHERE r.status='pending'"):
        print(f" Request #{r[0]} {r[1]}")
    print("\nExample 'not selected' explanation:")
    expired = queries.list_pairs(conn, status="expired")
    if expired:
        print(" ", expired[0]["explanation"][-190:])
    conn.close()


if __name__ == "__main__":
    print("########## FULL FUNDING ##########")
    run(False)
    print("\n########## PARTIAL FUNDING (co-funding) ##########")
    run(True)
