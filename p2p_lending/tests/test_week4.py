"""Week 4 tests: bipartite graph, ranking, allocation limits, partial funding."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import add_borrower, add_lender, add_request, new_conn
import queries
from matching_engine import MatchingEngine


def recommended(conn):
    return [r for r in queries.list_pairs(conn, status="recommended") if r["allocated_amount"] > 0]


class GraphTests(unittest.TestCase):
    def test_graph_is_bipartite_with_weighted_edges(self):
        import networkx as nx
        conn, _ = new_conn()
        l1, l2 = add_lender(conn), add_lender(conn)
        b = add_borrower(conn)
        add_request(conn, b)
        engine = MatchingEngine(conn)
        engine.run()
        g = engine.graph
        self.assertTrue(nx.is_bipartite(g))
        self.assertEqual(g.number_of_nodes(), 3)
        self.assertEqual(g.number_of_edges(), 2)
        self.assertTrue(all(d["weight"] > 0 for _, _, d in g.edges(data=True)))
        ranked = MatchingEngine.rank_edges(g)
        self.assertGreaterEqual(ranked[0][2]["weight"], ranked[1][2]["weight"])


class AllocationTests(unittest.TestCase):
    def test_multiple_lenders_compete_for_one_borrower_best_wins(self):
        conn, _ = new_conn()
        exact = add_lender(conn, appetite="medium", min_ret=10, max_ret=15)
        loose = add_lender(conn, appetite="high", min_ret=10, max_ret=15)
        b = add_borrower(conn, income=45000, obligations=12000, credit=650, years=3)
        rid = add_request(conn, b, amount=60000, term=24)
        s = MatchingEngine(conn).run()
        rows = recommended(conn)
        self.assertEqual(len(rows), 1)  # only ONE lender funds the borrower
        self.assertEqual(rows[0]["lender_id"], exact)  # the better-fitting lender wins
        self.assertEqual(s["requests_matched"], 1)
        expired = queries.list_pairs(conn, status="expired")
        self.assertEqual(expired[0]["lender_id"], loose)
        self.assertIn("higher-ranked lender", expired[0]["explanation"])

    def test_one_lender_can_fund_multiple_loans(self):
        conn, _ = new_conn()
        lender = add_lender(conn, available=100000)
        for _ in range(3):
            add_request(conn, add_borrower(conn), amount=30000)
        s = MatchingEngine(conn).run()
        self.assertEqual(s["requests_matched"], 3)
        self.assertEqual(sum(r["allocated_amount"] for r in recommended(conn)), 90000)

    def test_lender_is_never_over_allocated(self):
        conn, _ = new_conn()
        lender = add_lender(conn, available=100000)
        for _ in range(4):
            add_request(conn, add_borrower(conn), amount=30000)
        s = MatchingEngine(conn).run()
        self.assertEqual(s["requests_matched"], 3)  # 4 x 30000 > 100000
        self.assertLessEqual(sum(r["allocated_amount"] for r in recommended(conn)), 100000)
        reasons = [r["explanation"] for r in queries.list_pairs(conn, status="expired")]
        self.assertTrue(any("remaining funds" in x for x in reasons))

    def test_no_compatible_lender(self):
        conn, _ = new_conn()
        add_lender(conn, appetite="low", min_ret=1, max_ret=5)
        add_request(conn, add_borrower(conn), amount=30000)
        s = MatchingEngine(conn).run()
        self.assertEqual(s["requests_matched"], 0)
        self.assertEqual(s["allocation_success_rate"], 0.0)
        self.assertEqual(conn.execute("SELECT status FROM loan_requests").fetchone()[0], "pending")

    def test_amount_exceeding_available_funds(self):
        conn, _ = new_conn()
        add_lender(conn, available=20000)
        add_request(conn, add_borrower(conn), amount=30000)
        self.assertEqual(MatchingEngine(conn).run()["requests_matched"], 0)

    def test_inactive_lender_is_ignored(self):
        conn, _ = new_conn()
        add_lender(conn, activate=False)
        add_request(conn, add_borrower(conn), amount=30000)
        s = MatchingEngine(conn).run()
        self.assertEqual((s["lenders"], s["requests_matched"]), (0, 0))

    def test_rerun_is_repeatable(self):
        conn, _ = new_conn()
        add_lender(conn)
        add_request(conn, add_borrower(conn))
        first = MatchingEngine(conn).run()
        second = MatchingEngine(conn).run()
        self.assertEqual(first["recommended"], second["recommended"])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 1)


class PartialFundingTests(unittest.TestCase):
    def test_two_lenders_cofund_one_request(self):
        conn, _ = new_conn()
        a, b = add_lender(conn, available=60000), add_lender(conn, available=60000)
        add_request(conn, add_borrower(conn), amount=100000)
        self.assertEqual(MatchingEngine(conn).run()["requests_matched"], 0)  # full mode fails
        s = MatchingEngine(conn, allow_partial=True).run()
        self.assertEqual(s["requests_matched"], 1)
        rows = recommended(conn)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(r["allocated_amount"] for r in rows), 100000)
        self.assertTrue(all(r["allocated_amount"] <= 60000 for r in rows))

    def test_unfundable_request_is_rolled_back_and_frees_money(self):
        conn, _ = new_conn()
        add_lender(conn, available=60000)
        big = add_request(conn, add_borrower(conn), amount=100000)  # cannot be covered (only 60000 exists)
        small = add_request(conn, add_borrower(conn), amount=50000)
        s = MatchingEngine(conn, allow_partial=True).run()
        statuses = dict(conn.execute("SELECT request_id, status FROM loan_requests").fetchall())
        self.assertEqual(statuses[big], "pending")
        self.assertEqual(statuses[small], "matched")  # freed money funds the smaller one
        self.assertEqual(s["total_allocated"], 50000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
