"""Week 6 routes - audit screen and downloadable CSV / Excel / PDF reports."""
from flask import Blueprint, Response, render_template, request
import reports
from utils import db_conn

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/audit")
def audit_log():
    entity = request.args.get("entity_type")
    with db_conn() as conn:
        rows = reports.audit_rows(conn, entity_type=entity)
        columns = [("log_id", "#"), ("created_at", "Time"), ("entity_type", "Entity"), ("entity_id", "ID"),
                   ("action", "Action"), ("old_value", "Old"), ("new_value", "New / details"), ("actor", "Actor")]
        return render_template("table.html", title="Audit log (latest 300)", columns=columns, rows=rows,
                               intro="Filter with ?entity_type=loan, repayment, match, loan_request, lender, borrower or system.")


@bp.route("/loans.csv")
def loans_csv():
    with db_conn() as conn:
        data = reports.build_csv(conn)
        return Response(data, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=loans.csv"})


@bp.route("/loans.xlsx")
def loans_xlsx():
    with db_conn() as conn:
        data = reports.build_xlsx(conn)
        return Response(data, headers={"Content-Disposition": "attachment; filename=p2p_report.xlsx"},
                        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/summary.pdf")
def summary_pdf():
    with db_conn() as conn:
        data = reports.build_pdf(conn)
        return Response(data, mimetype="application/pdf", headers={"Content-Disposition": "inline; filename=p2p_report.pdf"})
