"""Week 5 routes - accept matches, loan list, repayment schedule, repayment simulation."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
import loan_service as ls
from models import ValidationError
from utils import db_conn

bp = Blueprint("loans", __name__, url_prefix="/loans")


def _flash_errors(exc):
    for message in exc.errors:
        flash(message, "danger")


@bp.route("/pending")
def pending():
    with db_conn() as conn:
        rows = ls.list_pending_funding(conn)
        for row in rows:
            row["_actions"] = [{"label": "Accept & create loan(s)", "method": "post",
                                "url": url_for("loans.accept", request_id=row["request_id"])}]
        columns = [("request_id", "Request"), ("borrower", "Borrower"), ("amount", "Amount"),
                   ("term_months", "Term (m)"), ("lenders", "Lenders"), ("allocated", "Allocated")]
        return render_template("table.html", title="Matched requests waiting for acceptance", columns=columns,
                               rows=rows, intro="Run matching first, then accept matches to create simulated loans.",
                               top_actions=[{"label": "Accept all", "method": "post", "url": url_for("loans.accept_all")}])


@bp.route("/accept/<int:request_id>", methods=["POST"])
def accept(request_id):
    with db_conn() as conn:
        try:
            ids = ls.accept_request(conn, request_id)
            flash(f"Request #{request_id} accepted: loan(s) {', '.join('#' + str(i) for i in ids)} created.", "success")
        except ValidationError as exc:
            _flash_errors(exc)
        return redirect(url_for("loans.loans"))


@bp.route("/accept-all", methods=["POST"])
def accept_all():
    with db_conn() as conn:
        ids, errors = ls.accept_all(conn)
        flash(f"{len(ids)} loan(s) created.", "success")
        for message in errors:
            flash(message, "danger")
        return redirect(url_for("loans.loans"))


@bp.route("")
def loans():
    with db_conn() as conn:
        rows = ls.list_loans(conn)
        for row in rows:
            row["_actions"] = [{"label": "Schedule", "method": "get", "style": "outline-primary",
                                "url": url_for("loans.detail", loan_id=row["loan_id"])}]
        columns = [("loan_id", "Loan"), ("lender", "Lender"), ("borrower", "Borrower"), ("principal", "Principal"),
                   ("interest_rate", "Rate %"), ("duration_months", "Months"), ("settled", "Paid instalments"),
                   ("outstanding_balance", "Outstanding"), ("status", "Status"), ("start_date", "Start")]
        return render_template("table.html", title="Loan lifecycle tracker", columns=columns, rows=rows,
                               top_actions=[{"label": "Simulate all repayments", "method": "post",
                                             "url": url_for("loans.simulate_everything")}])


@bp.route("/<int:loan_id>")
def detail(loan_id):
    with db_conn() as conn:
        loan = ls.get_loan(conn, loan_id)
        if loan is None:
            flash("Loan not found.", "danger")
            return redirect(url_for("loans.loans"))
        rows = ls.get_repayments(conn, loan_id)
        first_pending = next((r for r in rows if r["status"] == "pending"), None)
        if first_pending:
            base = url_for("loans.mark", repayment_id=first_pending["repayment_id"])
            first_pending["_actions"] = [
                {"label": "Paid", "method": "post", "style": "success", "url": f"{base}?status=paid"},
                {"label": "Late", "method": "post", "style": "warning", "url": f"{base}?status=late"},
                {"label": "Default", "method": "post", "style": "danger", "url": f"{base}?status=defaulted"}]
        columns = [("installment_no", "#"), ("due_date", "Due date"), ("amount_due", "Amount due"),
                   ("amount_paid", "Paid"), ("status", "Status"), ("paid_date", "Paid on")]
        title = (f"Loan #{loan_id}: {loan['lender']} -> {loan['borrower']} | principal {loan['principal']:,.2f} | "
                 f"outstanding {loan['outstanding_balance']:,.2f} | {loan['status']}")
        actions = [{"label": label, "method": "post", "style": "secondary",
                    "url": url_for("loans.simulate", loan_id=loan_id, scenario=key)}
                   for label, key in (("Simulate: all paid", "all_paid"), ("Simulate: some late", "some_late"),
                                      ("Simulate: default", "default"), ("Simulate: random", "random"))]
        return render_template("table.html", title=title, columns=columns, rows=rows, top_actions=actions)


@bp.route("/installments/<int:repayment_id>/mark", methods=["POST"])
def mark(repayment_id):
    with db_conn() as conn:
        loan_id = conn.execute("SELECT loan_id FROM repayments WHERE repayment_id = ?", (repayment_id,)).fetchone()
        try:
            ls.mark_installment(conn, repayment_id, request.args.get("status", ""), actor="admin")
        except ValidationError as exc:
            _flash_errors(exc)
        return redirect(url_for("loans.detail", loan_id=loan_id[0]) if loan_id else url_for("loans.loans"))


@bp.route("/<int:loan_id>/simulate", methods=["POST"])
def simulate(loan_id):
    with db_conn() as conn:
        try:
            ls.simulate_loan(conn, loan_id, request.args.get("scenario", "random"))
            flash("Repayment simulation finished.", "success")
        except ValidationError as exc:
            _flash_errors(exc)
        return redirect(url_for("loans.detail", loan_id=loan_id))


@bp.route("/simulate-all", methods=["POST"])
def simulate_everything():
    with db_conn() as conn:
        ids = ls.simulate_all(conn)
        flash(f"Simulated repayments for {len(ids)} active loan(s).", "success")
        return redirect(url_for("loans.loans"))
