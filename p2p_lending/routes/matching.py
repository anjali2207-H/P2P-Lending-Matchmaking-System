"""Week 4 routes - run the matching engine and show recommended matches."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
import queries
from matching_engine import MatchingEngine
from utils import db_conn

bp = Blueprint("matching", __name__, url_prefix="/matching")


@bp.route("/run", methods=["POST"])
def run():
    partial = request.args.get("partial") == "1"
    with db_conn() as conn:
        s = MatchingEngine(conn, allow_partial=partial).run()
        flash(f"Matching finished: {s['recommended']} recommended matches, {s['requests_matched']} of "
              f"{s['requests']} requests fully matched ({s['allocation_success_rate']}%), "
              f"{s['seconds']} s.", "success")
        return redirect(url_for("matching.recommendations"))


@bp.route("/recommendations")
def recommendations():
    with db_conn() as conn:
        rows = [r for r in queries.list_pairs(conn) if r["status"] in ("recommended", "accepted")
                and r["allocated_amount"] > 0]
        columns = [("request_id", "Req"), ("borrower", "Borrower"), ("lender", "Lender"), ("amount", "Loan amount"),
                   ("allocated_amount", "Allocated"), ("score", "Score"), ("status", "Status"),
                   ("explanation", "Why recommended")]
        return render_template(
            "table.html", title="Recommended lender-borrower matches", columns=columns, rows=rows,
            intro="Best compatibility first. A lender is never allocated more than its available amount.",
            top_actions=[{"label": "Run matching", "method": "post", "url": url_for("matching.run")},
                         {"label": "Run matching (partial funding)", "method": "post", "style": "secondary",
                          "url": url_for("matching.run", partial=1)}])
