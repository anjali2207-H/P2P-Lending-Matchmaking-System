"""Week 6 routes - administrator, lender and borrower dashboards."""
from flask import Blueprint, abort, render_template, url_for
import profile_service as ps
import reports
from utils import db_conn

bp = Blueprint("dashboard", __name__)


@bp.route("/admin")
def admin():
    with db_conn() as conn:
        lenders = [dict(l.to_dict(), _actions=[{"label": "Dashboard", "url": url_for("dashboard.lender", lender_id=l.lender_id)}])
                   for l in ps.list_lenders(conn)]
        borrowers = [dict(b.to_dict(), _actions=[{"label": "Dashboard", "url": url_for("dashboard.borrower", borrower_id=b.borrower_id)}])
                     for b in ps.list_borrowers(conn)]
        stats, charts = reports.system_stats(conn), reports.admin_charts(conn)
        sections = [
            {"title": "Lenders", "rows": lenders, "columns": [("lender_id", "ID"), ("full_name", "Name"),
                                                               ("risk_appetite", "Risk"), ("available_amount", "Available"), ("profile_status", "Status")]},
            {"title": "Borrowers", "rows": borrowers, "columns": [("borrower_id", "ID"), ("full_name", "Name"),
                                                                   ("monthly_income", "Income"), ("credit_score", "Credit"), ("profile_status", "Status")]}]
        downloads = [("Loans CSV", url_for("reports.loans_csv")), ("Excel report", url_for("reports.loans_xlsx")),
                     ("PDF report", url_for("reports.summary_pdf"))]
        return render_template("dashboard.html", title="Administrator dashboard", stats=stats, charts=charts,
                               sections=sections, downloads=downloads)


@bp.route("/lender/<int:lender_id>")
def lender(lender_id):
    with db_conn() as conn:
        data = reports.lender_dashboard(conn, lender_id)
        if data is None:
            abort(404)
        return render_template("dashboard.html", **data)


@bp.route("/borrower/<int:borrower_id>")
def borrower(borrower_id):
    with db_conn() as conn:
        data = reports.borrower_dashboard(conn, borrower_id)
        if data is None:
            abort(404)
        return render_template("dashboard.html", **data)
