"""Week 7 - evaluation harness: runs the whole pipeline on simulated data and reports
 match execution time, number of eligible matches, match-allocation success rate,
 constraint violations, explanation correctness, database and audit consistency.
 python evaluate.py # sizes 10x15, 50x80, 200x300
 python evaluate.py --sizes 20x30,100x150 --report test_report.md
"""
import argparse
import json
import os
import tempfile
import time
import database
import generate_data
import loan_service as ls
import profile_service as ps
import scoring
from matching_engine import MatchingEngine


def _risk_result(conn, request_id):
    row = conn.execute("SELECT * FROM risk_scores WHERE request_id = ?", (request_id,)).fetchone()
    import config
    return scoring.RiskResult(row["score"], row["risk_category"], json.loads(row["components"]),
                              row["explanation"], config.RATE_BY_RISK[row["risk_category"]])


def count_constraint_violations(conn, allow_partial):
    """Re-check every selected match against the hard rules, plus capacity limits."""
    checker = scoring.CompatibilityScorer(allow_partial)
    violations = 0
    rows = conn.execute("SELECT * FROM matches WHERE status = 'recommended' AND allocated_amount > 0").fetchall()
    for m in rows:
        lender = ps.get_lender(conn, m["lender_id"])
        request = ps.get_request(conn, m["request_id"])
        borrower = ps.get_borrower(conn, request.borrower_id)
        violations += len(checker.check_constraints(lender, borrower, request, _risk_result(conn, m["request_id"])))
    for row in conn.execute("SELECT SUM(m.allocated_amount) AS used, l.available_amount FROM matches m "
                            "JOIN lenders l ON l.lender_id = m.lender_id WHERE m.status = 'recommended' "
                            "AND m.allocated_amount > 0 GROUP BY m.lender_id"):
        violations += 1 if row["used"] > row["available_amount"] + 0.01 else 0
    for row in conn.execute("SELECT SUM(m.allocated_amount) AS got, r.amount FROM matches m JOIN loan_requests r "
                            "ON r.request_id = m.request_id WHERE m.status = 'recommended' AND m.allocated_amount > 0 "
                            "GROUP BY m.request_id"):
        violations += 1 if row["got"] > row["amount"] + 0.01 else 0
    return violations, len(rows)


def explanation_correctness(conn, allow_partial):
    """Fraction of stored explanations that agree with a fresh evaluation of the same pair."""
    checker, ok, total = scoring.CompatibilityScorer(allow_partial), 0, 0
    lenders = {l.lender_id: l for l in ps.list_lenders(conn)}
    cache = {}
    for m in conn.execute("SELECT * FROM matches"):
        total += 1
        if m["request_id"] not in cache:
            request = ps.get_request(conn, m["request_id"])
            cache[m["request_id"]] = (request, ps.get_borrower(conn, request.borrower_id),
                                      _risk_result(conn, m["request_id"]))
        request, borrower, risk = cache[m["request_id"]]
        result = checker.evaluate(lenders[m["lender_id"]], borrower, request, risk)
        text = m["explanation"]
        if m["status"] == "rejected":
            good = (not result.eligible) and text.startswith("REJECTED") and all(msg in text for _, msg in result.violations)
        elif m["status"] == "recommended":
            good = result.eligible and "SELECTED (rank" in text and abs(result.score - m["compatibility_score"]) < 0.01
        else:
            good = result.eligible and "NOT SELECTED" in text
        ok += good
    return ok, total


def consistency_checks(conn):
    """Database + audit consistency after loans were created and repayments simulated."""
    checks = {}
    loans = conn.execute("SELECT * FROM loans").fetchall()
    checks["every loan has a LOAN_CREATED audit entry"] = all(conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action='LOAN_CREATED' AND entity_id=?", (l["loan_id"],)).fetchone()[0] == 1
        for l in loans)
    checks["every loan has one instalment per month"] = all(conn.execute(
        "SELECT COUNT(*) FROM repayments WHERE loan_id=?", (l["loan_id"],)).fetchone()[0] == l["duration_months"] for l in loans)
    checks["outstanding balance matches settled instalments"] = True
    for l in loans:
        settled = conn.execute("SELECT COUNT(*) FROM repayments WHERE loan_id=? AND status IN ('paid','late')",
                               (l["loan_id"],)).fetchone()[0]
        schedule = ls.build_schedule(l["principal"], l["interest_rate"], l["duration_months"], ls._to_date(l["start_date"]))
        expected = l["principal"] if settled == 0 else schedule[settled - 1]["balance_after"]
        if l["status"] == "completed":
            expected = 0.0
        if abs(expected - l["outstanding_balance"]) > 0.01:
            checks["outstanding balance matches settled instalments"] = False
    checks["funded requests: loan principals add up to the request amount"] = all(
        abs(row["total"] - row["amount"]) < 0.01 for row in conn.execute(
            "SELECT SUM(lo.principal) AS total, r.amount FROM loans lo JOIN matches m ON m.match_id = lo.match_id "
            "JOIN loan_requests r ON r.request_id = m.request_id GROUP BY r.request_id"))
    checks["no lender has negative available funds"] = conn.execute(
        "SELECT COUNT(*) FROM lenders WHERE available_amount < 0").fetchone()[0] == 0
    checks["accepted matches == loans"] = conn.execute("SELECT COUNT(*) FROM matches WHERE status='accepted'").fetchone()[0] == len(loans)
    changed = conn.execute("SELECT COUNT(*) FROM repayments WHERE status != 'pending'").fetchone()[0]
    logged = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE entity_type='repayment'").fetchone()[0]
    checks["every repayment status change is in the audit log"] = changed == logged
    checks["funded requests have loans"] = conn.execute(
        "SELECT COUNT(*) FROM loan_requests r WHERE r.status='funded' AND NOT EXISTS "
        "(SELECT 1 FROM matches m JOIN loans lo ON lo.match_id=m.match_id WHERE m.request_id=r.request_id)").fetchone()[0] == 0
    return checks


def evaluate(n_lenders, n_borrowers, seed=42, partial=False):
    path = os.path.join(tempfile.mkdtemp(), "eval.db")
    database.init_db(path)
    conn = database.get_connection(path)
    lenders, borrowers, requests = generate_data.generate(n_lenders, n_borrowers, seed)
    _, _, request_ids, _ = generate_data.load(conn, lenders, borrowers, requests)
    started = time.perf_counter()
    summary = MatchingEngine(conn, allow_partial=partial).run()
    match_seconds = time.perf_counter() - started
    violations, selected = count_constraint_violations(conn, partial)
    good, total = explanation_correctness(conn, partial)
    ls.accept_all(conn)
    ls.simulate_all(conn, "random", seed)
    checks = consistency_checks(conn)
    result = {
        "lenders": n_lenders, "requests": len(request_ids), "pairs_evaluated": n_lenders * len(request_ids),
        "match_seconds": round(match_seconds, 3), "eligible_matches": summary["eligible_edges"],
        "selected_matches": selected, "requests_matched": summary["requests_matched"],
        "allocation_success_rate": summary["allocation_success_rate"], "constraint_violations": violations,
        "explanation_correct": f"{good}/{total}", "explanation_correct_pct": round(100 * good / total, 2) if total else 100.0,
        "consistency_passed": f"{sum(checks.values())}/{len(checks)}", "consistency_details": checks,
        "loans_created": conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0],
        "audit_entries": conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]}
    conn.close()
    return result


def markdown_report(results, partial):
    lines = ["# P2P Lending Matchmaking - Evaluation Report", "",
             f"Funding mode: {'partial (co-funding)' if partial else 'full funding'}. Simulated data only.", "",
             "| Lenders | Requests | Pairs | Match time (s) | Eligible | Selected | Matched | Success % |"
             " Violations | Explanations | Consistency |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['lenders']} | {r['requests']} | {r['pairs_evaluated']} | {r['match_seconds']} | "
                     f"{r['eligible_matches']} | {r['selected_matches']} | {r['requests_matched']} | "
                     f"{r['allocation_success_rate']} | {r['constraint_violations']} | {r['explanation_correct']} | "
                     f"{r['consistency_passed']} |")
    lines += ["", "## Consistency checks (largest run)", ""]
    lines += [f"- [{'x' if ok else ' '}] {name}" for name, ok in results[-1]["consistency_details"].items()]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="10x15,50x80,200x300", help="lenders x borrowers, comma separated")
    parser.add_argument("--partial", action="store_true")
    parser.add_argument("--report", help="write a markdown report to this file")
    args = parser.parse_args()
    results = []
    for size in args.sizes.split(","):
        n_l, n_b = (int(x) for x in size.lower().split("x"))
        r = evaluate(n_l, n_b, partial=args.partial)
        results.append(r)
        print(f"\n=== {n_l} lenders x {n_b} borrowers ({r['requests']} requests, {r['pairs_evaluated']:,} pairs) ===")
        for key in ("match_seconds", "eligible_matches", "selected_matches", "requests_matched",
                    "allocation_success_rate", "constraint_violations", "explanation_correct",
                    "consistency_passed", "loans_created", "audit_entries"):
            print(f" {key:<26} {r[key]}")
        failed = [k for k, ok in r["consistency_details"].items() if not ok]
        print(" consistency problems ", failed or "none")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(markdown_report(results, args.partial))
        print(f"\nReport written to {args.report}")


if __name__ == "__main__":
    main()
