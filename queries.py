"""Read-only queries used by several screens (Week 3)."""
_PAIR_SQL = """
SELECT m.match_id, m.lender_id, ul.full_name AS lender, m.request_id, ub.full_name AS borrower,
 r.amount, r.term_months, m.compatibility_score AS score, m.risk_fit, m.amount_fit, m.term_fit,
 m.return_fit, m.allocated_amount, m.status, m.explanation
FROM matches m
JOIN lenders l ON l.lender_id = m.lender_id JOIN users ul ON ul.user_id = l.user_id
JOIN loan_requests r ON r.request_id = m.request_id
JOIN borrowers b ON b.borrower_id = r.borrower_id JOIN users ub ON ub.user_id = b.user_id
"""


def list_pairs(conn, status=None, request_id=None, lender_id=None):
    where, params = [], []
    if status:
        where.append("m.status = ?")
        params.append(status)
    if request_id:
        where.append("m.request_id = ?")
        params.append(request_id)
    if lender_id:
        where.append("m.lender_id = ?")
        params.append(lender_id)
    sql = _PAIR_SQL + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY m.request_id, m.compatibility_score DESC, m.match_id"
    return [dict(r) for r in conn.execute(sql, params)]


def list_risk_scores(conn):
    sql = ("SELECT s.request_id, u.full_name AS borrower, r.amount, r.term_months, s.score,"
           " s.risk_category, s.explanation FROM risk_scores s"
           " JOIN loan_requests r ON r.request_id = s.request_id"
           " JOIN borrowers b ON b.borrower_id = s.borrower_id JOIN users u ON u.user_id = b.user_id"
           " ORDER BY s.request_id")
    return [dict(r) for r in conn.execute(sql)]
