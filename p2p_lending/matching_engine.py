"""Week 4 - graph-based matchmaking with a weighted bipartite graph (NetworkX).
 Lender nodes (left, bipartite=0) --edge: eligible pair, weight = compatibility score-->
 Request nodes (right, bipartite=1; each carries its borrower)

Pipeline: score pairs -> build graph from eligible pairs -> rank edges ->
greedy allocation that never exceeds a lender's available amount ->
store recommended matches with the reason for every decision.

Partial funding (optional): one loan may be co-funded by several lenders, but a
request is only kept when the lenders together cover 100% of it.
"""
import time
import networkx as nx
import audit
import profile_service
import scoring


class MatchingEngine:
    def __init__(self, conn, allow_partial=False):
        self.conn = conn
        self.allow_partial = allow_partial
        self.graph = None

    # ---- Step 1: load -------------------------------------------------------
    def load_active_lenders(self):
        return profile_service.list_lenders(self.conn, profile_status="active")

    def load_pending_requests(self):
        return profile_service.list_requests(self.conn, status="pending")

    # ---- Steps 2-5: build the bipartite graph from eligible pairs ----------
    def build_graph(self):
        g = nx.Graph()
        for lender in self.load_active_lenders():
            g.add_node(f"L{lender.lender_id}", bipartite=0, kind="lender", name=lender.full_name,
                       available=lender.available_amount)
        for req in self.load_pending_requests():
            g.add_node(f"R{req['request_id']}", bipartite=1, kind="request", name=req["borrower"],
                       amount=req["amount"], borrower_id=req["borrower_id"])
        rows = self.conn.execute(
            "SELECT match_id, lender_id, request_id, compatibility_score FROM matches"
            " WHERE status = 'recommended' AND allocated_amount = 0").fetchall()
        for row in rows:
            lender_node, request_node = f"L{row['lender_id']}", f"R{row['request_id']}"
            if lender_node in g and request_node in g:
                g.add_edge(lender_node, request_node, weight=row["compatibility_score"], match_id=row["match_id"])
        self.graph = g
        return g

    # ---- Step 6: rank edges -------------------------------------------------
    @staticmethod
    def rank_edges(g):
        """Edges as (lender_node, request_node, data), best compatibility first."""
        edges = []
        for u, v, data in g.edges(data=True):
            lender_node, request_node = (u, v) if g.nodes[u]["bipartite"] == 0 else (v, u)
            edges.append((lender_node, request_node, data))
        edges.sort(key=lambda e: (-e[2]["weight"], e[2]["match_id"]))
        return edges

    # ---- Steps 7-9: select best matches within lender capacity -------------
    def allocate(self, g):
        ranked = self.rank_edges(g)
        failed = set()  # requests that could not be fully funded
        while True:
            capacity = {n: d["available"] for n, d in g.nodes(data=True) if d["bipartite"] == 0}
            need = {n: d["amount"] for n, d in g.nodes(data=True) if d["bipartite"] == 1}
            allocations, reasons, ranks = {}, {}, {}
            for rank, (lender_node, request_node, data) in enumerate(ranked, start=1):
                match_id = data["match_id"]
                ranks[match_id] = rank
                if request_node in failed:
                    reasons[match_id] = "the request could not be fully funded by the compatible lenders in this run"
                elif need[request_node] <= 0.005:
                    reasons[match_id] = "the borrower was already funded by a higher-ranked lender"
                else:
                    if self.allow_partial:
                        amount = min(capacity[lender_node], need[request_node])
                    else:
                        amount = need[request_node] if capacity[lender_node] + 1e-9 >= need[request_node] else 0
                    if amount <= 0.005:
                        reasons[match_id] = (f"the lender's remaining funds ({capacity[lender_node]:,.2f}) "
                                             f"cannot cover this loan")
                    else:
                        amount = round(amount, 2)
                        allocations[match_id] = amount
                        capacity[lender_node] -= amount
                        need[request_node] -= amount
            newly_failed = set()
            if self.allow_partial:
                for request_node, remaining in need.items():
                    if request_node not in failed and remaining > 0.005 and any(
                            data["match_id"] in allocations for _, r, data in ranked if r == request_node):
                        newly_failed.add(request_node)
            if not newly_failed:
                return allocations, reasons, ranks, need
            failed |= newly_failed  # free their money and try again

    # ---- store results ------------------------------------------------------
    def persist(self, g, allocations, reasons, ranks, need):
        conn = self.conn
        explanations = dict(conn.execute("SELECT match_id, explanation FROM matches WHERE status = 'recommended'"
                                         " AND allocated_amount = 0").fetchall())
        funded = {}
        for lender_node, request_node, data in self.rank_edges(g):
            match_id = data["match_id"]
            funded.setdefault(request_node, 0.0)
            funded[request_node] += allocations.get(match_id, 0.0)

        for match_id, rank in ranks.items():
            base = explanations[match_id]
            if match_id in allocations:
                note = f" | SELECTED (rank {rank} of {len(ranks)}): allocated {allocations[match_id]:,.2f}."
                conn.execute("UPDATE matches SET status = 'recommended', allocated_amount = ?, explanation = ?"
                             " WHERE match_id = ?", (allocations[match_id], base + note, match_id))
                audit.log(conn, "match", match_id, "RECOMMENDED", "eligible", "recommended",
                          details=f"allocated {allocations[match_id]:,.2f}")
            else:
                note = f" | NOT SELECTED: {reasons[match_id]}."
                conn.execute("UPDATE matches SET status = 'expired', explanation = ? WHERE match_id = ?",
                             (base + note, match_id))

        matched = 0
        for request_node, remaining in need.items():
            if funded.get(request_node, 0) > 0 and remaining <= 0.005:
                request_id = int(request_node[1:])
                conn.execute("UPDATE loan_requests SET status = 'matched' WHERE request_id = ?", (request_id,))
                audit.log(conn, "loan_request", request_id, "STATUS_CHANGE", "pending", "matched",
                          details=f"funded {funded[request_node]:,.2f}")
                matched += 1
        return matched

    # ---- public entry point -------------------------------------------------
    def run(self, rescore=True):
        started = time.perf_counter()
        if rescore:
            scoring.score_all(self.conn, allow_partial=self.allow_partial)
        g = self.build_graph()
        pending = [n for n, d in g.nodes(data=True) if d["bipartite"] == 1]
        allocations, reasons, ranks, need = self.allocate(g)
        matched = self.persist(g, allocations, reasons, ranks, need)
        audit.log(self.conn, "system", None, "MATCHING_RUN", None,
                  details=f"{len(allocations)} recommended, {matched}/{len(pending)} requests matched")
        self.conn.commit()
        return {"lenders": sum(1 for _, d in g.nodes(data=True) if d["bipartite"] == 0),
                "requests": len(pending), "eligible_edges": g.number_of_edges(),
                "recommended": len(allocations), "requests_matched": matched,
                "allocation_success_rate": round(100 * matched / len(pending), 1) if pending else 0.0,
                "total_allocated": round(sum(allocations.values()), 2),
                "partial_funding": self.allow_partial,
                "seconds": round(time.perf_counter() - started, 4)}
