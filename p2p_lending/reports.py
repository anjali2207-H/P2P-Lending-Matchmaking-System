"""Week 6 - dashboard statistics and CSV / Excel / PDF reports."""
import io
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import loan_service
import profile_service
import queries


def _one(conn, sql, params=()):
    value = conn.execute(sql, params).fetchone()[0]
    return value if value is not None else 0


def _counts(conn, sql, params=()):
    rows = conn.execute(sql, params).fetchall()
    return [r[0] for r in rows], [round(r[1], 2) for r in rows]


# ---------------------------------------------------------------------------
# administrator
# ---------------------------------------------------------------------------
def system_stats(conn):
    return [
        ("Active lenders", _one(conn, "SELECT COUNT(*) FROM lenders WHERE profile_status='active'")),
        ("Active borrowers", _one(conn, "SELECT COUNT(*) FROM borrowers WHERE profile_status='active'")),
        ("Pending requests", _one(conn, "SELECT COUNT(*) FROM loan_requests WHERE status='pending'")),
        ("Matched requests", _one(conn, "SELECT COUNT(*) FROM loan_requests WHERE status='matched'")),
        ("Funded requests", _one(conn, "SELECT COUNT(*) FROM loan_requests WHERE status='funded'")),
        ("Recommended matches", _one(conn, "SELECT COUNT(*) FROM matches WHERE status='recommended' AND allocated_amount>0")),
        ("Active loans", _one(conn, "SELECT COUNT(*) FROM loans WHERE status='active'")),
        ("Defaulted loans", _one(conn, "SELECT COUNT(*) FROM loans WHERE status='defaulted'")),
        ("Total principal", f"{_one(conn, 'SELECT SUM(principal) FROM loans'):,.0f}"),
        ("Total outstanding", f"{_one(conn, 'SELECT SUM(outstanding_balance) FROM loans'):,.0f}"),
        ("Audit entries", _one(conn, "SELECT COUNT(*) FROM audit_logs")),
    ]


def admin_charts(conn):
    risk_labels, risk_data = _counts(conn, "SELECT risk_category, COUNT(*) FROM risk_scores GROUP BY risk_category")
    match_labels, match_data = _counts(conn, "SELECT status, COUNT(*) FROM matches GROUP BY status")
    rep_labels, rep_data = _counts(conn, "SELECT status, COUNT(*) FROM repayments GROUP BY status")
    loan_labels, loan_data = _counts(conn, "SELECT status, COUNT(*) FROM loans GROUP BY status")
    return [
        {"id": "riskChart", "title": "Borrower risk classes", "type": "doughnut", "labels": risk_labels, "data": risk_data},
        {"id": "matchChart", "title": "Scored pairs by status", "type": "bar", "labels": match_labels, "data": match_data},
        {"id": "repayChart", "title": "Repayment statuses", "type": "bar", "labels": rep_labels, "data": rep_data},
        {"id": "loanChart", "title": "Loans by status", "type": "doughnut", "labels": loan_labels, "data": loan_data},
    ]


# ---------------------------------------------------------------------------
# lender
# ---------------------------------------------------------------------------
def lender_dashboard(conn, lender_id):
    lender = profile_service.get_lender(conn, lender_id)
    if lender is None:
        return None
    lent = _one(conn, "SELECT SUM(principal) FROM loans WHERE lender_id = ?", (lender_id,))
    interest = _one(conn, "SELECT SUM(r.amount_due) FROM repayments r JOIN loans l ON l.loan_id = r.loan_id "
                          "WHERE l.lender_id = ?", (lender_id,)) - lent if lent else 0
    defaulted = _one(conn, "SELECT SUM(principal) FROM loans WHERE lender_id = ? AND status = 'defaulted'", (lender_id,))
    stats = [("Risk appetite", lender.risk_appetite.capitalize()), ("Profile status", lender.profile_status),
             ("Available funds", f"{lender.available_amount:,.0f}"), ("Total lent", f"{lent:,.0f}"),
             ("Active loans", _one(conn, "SELECT COUNT(*) FROM loans WHERE lender_id=? AND status='active'", (lender_id,))),
             ("Expected interest (scheduled)", f"{interest:,.0f}"),
             ("Defaulted principal", f"{defaulted:,.0f}")]
    r_labels, r_data = _counts(
        conn, "SELECT COALESCE(s.risk_category,'unknown'), SUM(lo.principal) FROM loans lo "
              "JOIN matches m ON m.match_id = lo.match_id LEFT JOIN risk_scores s ON s.request_id = m.request_id "
              "WHERE lo.lender_id = ? GROUP BY 1", (lender_id,))
    p_labels, p_data = _counts(
        conn, "SELECT r.status, COUNT(*) FROM repayments r JOIN loans l ON l.loan_id = r.loan_id "
              "WHERE l.lender_id = ? GROUP BY r.status", (lender_id,))
    charts = [{"id": "portfolio", "title": "Amount lent by borrower risk class", "type": "doughnut",
               "labels": r_labels, "data": r_data},
              {"id": "repay", "title": "Instalment statuses of my loans", "type": "bar",
               "labels": p_labels, "data": p_data}]
    matches = [m for m in queries.list_pairs(conn, lender_id=lender_id)
               if m["status"] in ("recommended", "accepted") and m["allocated_amount"] > 0]
    loans = [l for l in loan_service.list_loans(conn) if l["lender_id"] == lender_id]
    return {"title": f"Lender dashboard - {lender.full_name}", "stats": stats, "charts": charts,
            "sections": [
                {"title": "Recommended / accepted matches", "rows": matches,
                 "columns": [("request_id", "Req"), ("borrower", "Borrower"), ("allocated_amount", "Allocated"),
                             ("score", "Score"), ("status", "Status"), ("explanation", "Why")]},
                {"title": "My loans", "rows": loans,
                 "columns": [("loan_id", "Loan"), ("borrower", "Borrower"), ("principal", "Principal"),
                             ("interest_rate", "Rate %"), ("duration_months", "Months"),
                             ("outstanding_balance", "Outstanding"), ("status", "Status")]}]}


# ---------------------------------------------------------------------------
# borrower
# ---------------------------------------------------------------------------
def borrower_dashboard(conn, borrower_id):
    borrower = profile_service.get_borrower(conn, borrower_id)
    if borrower is None:
        return None
    risk = conn.execute("SELECT score, risk_category FROM risk_scores WHERE borrower_id = ? "
                        "ORDER BY risk_score_id DESC LIMIT 1", (borrower_id,)).fetchone()
    stats = [("Profile status", borrower.profile_status), ("Monthly income", f"{borrower.monthly_income:,.0f}"),
             ("Obligations", f"{borrower.existing_obligations:,.0f}"), ("Debt-to-income", f"{borrower.debt_to_income():.0%}"),
             ("Credit score", borrower.credit_score),
             ("Latest risk score", f"{risk['score']} ({risk['risk_category']})" if risk else "not scored yet"),
             ("Total borrowed", f"{_one(conn, 'SELECT SUM(principal) FROM loans WHERE borrower_id=?', (borrower_id,)):,.0f}"),
             ("Outstanding", f"{_one(conn, 'SELECT SUM(outstanding_balance) FROM loans WHERE borrower_id=?', (borrower_id,)):,.0f}")]
    p_labels, p_data = _counts(
        conn, "SELECT r.status, COUNT(*) FROM repayments r JOIN loans l ON l.loan_id = r.loan_id "
              "WHERE l.borrower_id = ? GROUP BY r.status", (borrower_id,))
    requests = [r for r in profile_service.list_requests(conn) if r["borrower_id"] == borrower_id]
    loans = [l for l in loan_service.list_loans(conn) if l["borrower_id"] == borrower_id]
    risks = [dict(r) for r in conn.execute(
        "SELECT request_id, score, risk_category, explanation FROM risk_scores WHERE borrower_id = ?", (borrower_id,))]
    return {"title": f"Borrower dashboard - {borrower.full_name}", "stats": stats,
            "charts": [{"id": "repay", "title": "My instalment statuses", "type": "bar",
                        "labels": p_labels, "data": p_data}],
            "sections": [
                {"title": "My loan requests", "rows": requests,
                 "columns": [("request_id", "ID"), ("amount", "Amount"), ("term_months", "Term"),
                             ("purpose", "Purpose"), ("status", "Status")]},
                {"title": "Why my risk score is what it is", "rows": risks,
                 "columns": [("request_id", "Req"), ("score", "Score"), ("risk_category", "Class"),
                             ("explanation", "Explanation")]},
                {"title": "My loans", "rows": loans,
                 "columns": [("loan_id", "Loan"), ("lender", "Lender"), ("principal", "Principal"),
                             ("interest_rate", "Rate %"), ("outstanding_balance", "Outstanding"), ("status", "Status")]}]}


# ---------------------------------------------------------------------------
# audit + downloads
# ---------------------------------------------------------------------------
def audit_rows(conn, entity_type=None, limit=300):
    sql, params = "SELECT * FROM audit_logs", []
    if entity_type:
        sql += " WHERE entity_type = ?"
        params.append(entity_type)
    sql += " ORDER BY log_id DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]


def loans_dataframe(conn):
    return pd.DataFrame(loan_service.list_loans(conn))


def build_csv(conn):
    return loans_dataframe(conn).to_csv(index=False)


def build_xlsx(conn):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        loans_dataframe(conn).to_excel(writer, sheet_name="Loans", index=False)
        pd.DataFrame([dict(r) for r in conn.execute("SELECT * FROM repayments")]).to_excel(
            writer, sheet_name="Repayments", index=False)
        pd.DataFrame(audit_rows(conn, limit=5000)).to_excel(writer, sheet_name="Audit", index=False)
    return buffer.getvalue()


def build_pdf(conn):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title="P2P Lending Simulation Report")
    styles = getSampleStyleSheet()
    story = [Paragraph("P2P Lending Simulation Report", styles["Title"]),
             Paragraph("Academic simulation - no real money involved.", styles["Italic"]), Spacer(1, 12)]

    def table(data, widths=None):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d6efd")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
        return t

    story += [Paragraph("System summary", styles["Heading2"]),
              table([["Measure", "Value"]] + [[a, str(b)] for a, b in system_stats(conn)], [250, 150]), Spacer(1, 14),
              Paragraph("Loans", styles["Heading2"])]
    loans = loan_service.list_loans(conn)
    rows = [["Loan", "Lender", "Borrower", "Principal", "Rate %", "Months", "Outstanding", "Status"]]
    rows += [[l["loan_id"], l["lender"], l["borrower"], f"{l['principal']:,.0f}", l["interest_rate"],
              l["duration_months"], f"{l['outstanding_balance']:,.0f}", l["status"]] for l in loans[:60]]
    story.append(table(rows) if loans else Paragraph("No loans yet.", styles["Normal"]))
    doc.build(story)
    return buffer.getvalue()
