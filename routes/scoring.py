"""Week 3 routes - run scoring, risk explanation screen, scored-pair screen."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
import queries
import scoring
from utils import db_conn

bp = Blueprint("scoring", __name__, url_prefix="/scoring")


@bp.route("/run", methods=["POST"])
def run():
    partial = request.args.get("partial") == "1"
    with db_conn() as conn:
        s = scoring.score_all(conn, allow_partial=partial)
        flash(f"Scored {s['pairs']} pairs: {s['eligible']} eligible, {s['rejected']} rejected "
              f"({s['seconds']} s).", "success")
        return redirect(url_for("scoring.pairs"))


@bp.route("/risk")
def risk_scores():
    with db_conn() as conn:
        rows = queries.list_risk_scores(conn)
        columns = [("request_id", "Request"), ("borrower", "Borrower"), ("amount", "Amount"),
                   ("term_months", "Term"), ("score", "Score /100"), ("risk_category", "Risk class"),
                   ("explanation", "Why")]
        return render_template("table.html", title="Borrower risk scores", columns=columns, rows=rows,
                               intro="Higher score = safer borrower. Run scoring first if this table is empty.",
                               top_actions=[{"label": "Run scoring", "method": "post",
                                             "url": url_for("scoring.run")}])


@bp.route("/pairs")
def pairs():
    status = request.args.get("status")
    request_id = request.args.get("request_id", type=int)
    with db_conn() as conn:
        rows = queries.list_pairs(conn, status=status, request_id=request_id)
        columns = [("request_id", "Req"), ("borrower", "Borrower"), ("lender", "Lender"), ("amount", "Amount"),
                   ("score", "Score"), ("risk_fit", "Risk"), ("amount_fit", "Amt"), ("term_fit", "Term"),
                   ("return_fit", "Ret"), ("status", "Status"), ("explanation", "Why recommended / rejected")]
        return render_template(
            "table.html", title="Scored lender-borrower pairs", columns=columns, rows=rows,
            intro="Filter with ?status=recommended, ?status=rejected or ?status=expired (also ?request_id=N).",
            top_actions=[{"label": "Run scoring", "method": "post", "url": url_for("scoring.run")},
                         {"label": "Run scoring (partial funding)", "method": "post", "style": "secondary",
                          "url": url_for("scoring.run", partial=1)}])
