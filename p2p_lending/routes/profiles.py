"""Week 2 routes - lender / borrower registration, loan requests, profile status."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
import profile_service as ps
from models import ValidationError
from utils import db_conn

bp = Blueprint("profiles", __name__)

RISK_OPTIONS = [("low", "Low"), ("medium", "Medium"), ("high", "High")]


def _flash_errors(exc):
    for message in exc.errors:
        flash(message, "danger")


def _status_actions(role, pid, status):
    """Buttons shown for each profile row depending on its current status."""
    base = url_for("profiles.change_status", role=role, profile_id=pid)
    options = {
        "pending": [("Approve", "active", "success"), ("Reject", "rejected", "danger")],
        "active": [("Deactivate", "inactive", "warning")],
        "inactive": [("Activate", "active", "success")],
        "rejected": [("Re-open", "pending", "secondary")],
    }
    return [{"label": label, "url": f"{base}?to={to}", "method": "post", "style": style}
            for label, to, style in options.get(status, [])]


# ---------------------------------------------------------------------------
@bp.route("/lenders/register", methods=["GET", "POST"])
def register_lender():
    fields = [
        {"name": "full_name", "label": "Full name"},
        {"name": "email", "label": "Email", "type": "email"},
        {"name": "password", "label": "Password (min 8 characters)", "type": "password"},
        {"name": "risk_appetite", "label": "Risk appetite", "type": "select", "options": RISK_OPTIONS},
        {"name": "available_amount", "label": "Available investment amount", "type": "number", "step": "any"},
        {"name": "min_loan_amount", "label": "Minimum loan amount you will fund", "type": "number", "step": "any"},
        {"name": "max_loan_amount", "label": "Maximum loan amount you will fund", "type": "number", "step": "any"},
        {"name": "min_duration_months", "label": "Preferred minimum duration (months)", "type": "number"},
        {"name": "max_duration_months", "label": "Preferred maximum duration (months)", "type": "number"},
        {"name": "min_expected_return", "label": "Minimum expected return (% per year)", "type": "number", "step": "any"},
        {"name": "max_expected_return", "label": "Maximum expected return (% per year)", "type": "number", "step": "any"},
    ]
    if request.method == "POST":
        with db_conn() as conn:
            try:
                lender_id = ps.register_lender(conn, request.form)
                flash(f"Lender #{lender_id} registered. Status: pending approval.", "success")
                return redirect(url_for("profiles.lenders"))
            except ValidationError as exc:
                _flash_errors(exc)
    return render_template("form.html", title="Lender registration", fields=fields,
                           values=request.form, submit_label="Register lender")


@bp.route("/borrowers/register", methods=["GET", "POST"])
def register_borrower():
    fields = [
        {"name": "full_name", "label": "Full name"},
        {"name": "email", "label": "Email", "type": "email"},
        {"name": "password", "label": "Password (min 8 characters)", "type": "password"},
        {"name": "monthly_income", "label": "Simulated monthly income", "type": "number", "step": "any"},
        {"name": "existing_obligations", "label": "Existing monthly obligations (EMIs)", "type": "number", "step": "any"},
        {"name": "credit_score", "label": "Simulated credit score (300-900)", "type": "number"},
        {"name": "credit_history_years", "label": "Credit history (years)", "type": "number", "step": "any"},
    ]
    if request.method == "POST":
        with db_conn() as conn:
            try:
                borrower_id = ps.register_borrower(conn, request.form)
                flash(f"Borrower #{borrower_id} registered. Status: pending approval.", "success")
                return redirect(url_for("profiles.borrowers"))
            except ValidationError as exc:
                _flash_errors(exc)
    return render_template("form.html", title="Borrower registration", fields=fields,
                           values=request.form, submit_label="Register borrower")


@bp.route("/requests/new", methods=["GET", "POST"])
def new_request():
    with db_conn() as conn:
        active = [(b.borrower_id, f"#{b.borrower_id} {b.full_name}")
                  for b in ps.list_borrowers(conn, profile_status="active")]
        fields = [
            {"name": "borrower_id", "label": "Borrower", "type": "select", "options": active},
            {"name": "amount", "label": "Requested amount", "type": "number", "step": "any"},
            {"name": "term_months", "label": "Repayment term (months)", "type": "number"},
            {"name": "purpose", "label": "Purpose (optional)"},
        ]
        if request.method == "POST":
            try:
                borrower_id = int(request.form.get("borrower_id", ""))
                request_id = ps.create_loan_request(conn, borrower_id, request.form)
                flash(f"Loan request #{request_id} created.", "success")
                return redirect(url_for("profiles.requests"))
            except ValueError:
                flash("Please choose a borrower (only active borrowers can request loans).", "danger")
            except ValidationError as exc:
                _flash_errors(exc)
    return render_template("form.html", title="New loan request", fields=fields,
                           values=request.form, submit_label="Submit request")


# ---------------------------------------------------------------------------
@bp.route("/lenders")
def lenders():
    with db_conn() as conn:
        rows = []
        for lender in ps.list_lenders(conn):
            row = lender.to_dict()
            row["_actions"] = _status_actions("lender", lender.lender_id, lender.profile_status)
            rows.append(row)
        columns = [("lender_id", "ID"), ("full_name", "Name"), ("email", "Email"), ("risk_appetite", "Risk"),
                   ("available_amount", "Available"), ("min_loan_amount", "Min loan"), ("max_loan_amount", "Max loan"),
                   ("min_duration_months", "Min m"), ("max_duration_months", "Max m"),
                   ("min_expected_return", "Min %"), ("max_expected_return", "Max %"), ("profile_status", "Status")]
        return render_template("table.html", title="Lenders", columns=columns, rows=rows,
                               top_actions=[{"label": "+ Register lender", "url": url_for("profiles.register_lender"),
                                             "method": "get"}])


@bp.route("/borrowers")
def borrowers():
    with db_conn() as conn:
        rows = []
        for borrower in ps.list_borrowers(conn):
            row = borrower.to_dict()
            row["_actions"] = _status_actions("borrower", borrower.borrower_id, borrower.profile_status)
            rows.append(row)
        columns = [("borrower_id", "ID"), ("full_name", "Name"), ("email", "Email"), ("monthly_income", "Income"),
                   ("existing_obligations", "Obligations"), ("credit_score", "Credit"),
                   ("credit_history_years", "History (y)"), ("profile_status", "Status")]
        return render_template("table.html", title="Borrowers", columns=columns, rows=rows,
                               top_actions=[{"label": "+ Register borrower", "url": url_for("profiles.register_borrower"),
                                             "method": "get"}])


@bp.route("/requests")
def requests():
    with db_conn() as conn:
        rows = ps.list_requests(conn)
        for row in rows:
            if row["status"] in ("pending", "matched"):
                row["_actions"] = [{"label": "Cancel", "method": "post", "style": "outline-danger",
                                    "url": url_for("profiles.cancel", request_id=row["request_id"])}]
        columns = [("request_id", "ID"), ("borrower", "Borrower"), ("amount", "Amount"), ("term_months", "Term (m)"),
                   ("purpose", "Purpose"), ("status", "Status"), ("created_at", "Created")]
        return render_template("table.html", title="Loan requests", columns=columns, rows=rows,
                               top_actions=[{"label": "+ New request", "url": url_for("profiles.new_request"),
                                             "method": "get"}])


@bp.route("/profiles/<role>/<int:profile_id>/status", methods=["POST"])
def change_status(role, profile_id):
    new_status = request.args.get("to", "")
    with db_conn() as conn:
        try:
            ps.set_profile_status(conn, role, profile_id, new_status)
            flash(f"{role.capitalize()} #{profile_id} is now '{new_status}'.", "success")
        except ValidationError as exc:
            _flash_errors(exc)
        return redirect(url_for("profiles.lenders" if role == "lender" else "profiles.borrowers"))


@bp.route("/requests/<int:request_id>/cancel", methods=["POST"])
def cancel(request_id):
    with db_conn() as conn:
        try:
            ps.cancel_request(conn, request_id)
            flash(f"Request #{request_id} cancelled.", "success")
        except ValidationError as exc:
            _flash_errors(exc)
        return redirect(url_for("profiles.requests"))
