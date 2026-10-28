"""Week 3 - transparent borrower-risk scoring and lender/borrower compatibility.
1. RiskScorer : rule-based risk score 0-100 (higher = safer) + class low/medium/high
2. CompatibilityScorer : hard-constraint checks + Risk/Amount/Term/Return fit (0-100)
3. score_all() : scores every (active lender x pending request) pair and stores the
 components and a plain-English explanation in the database.
"""
import json
import time
from dataclasses import dataclass, field
import audit
import config
import profile_service
from models import calculate_emi


# ---------------------------------------------------------------------------
# 1. Borrower risk
# ---------------------------------------------------------------------------
@dataclass
class RiskResult:
    score: float
    category: str
    components: dict
    explanation: str
    rate: float = 0.0


class RiskScorer:
    """Rule-based risk score. Every component is shown to the user."""
    def classify(self, score):
        if score >= config.LOW_RISK_MIN_SCORE:
            return "low"
        if score >= config.MEDIUM_RISK_MIN_SCORE:
            return "medium"
        return "high"

    def score(self, borrower, request):
        w = config.RISK_SCORE_WEIGHTS
        credit = (min(max(borrower.credit_score, 300), 900) - 300) / 600 * w["credit"]
        dti = borrower.debt_to_income()
        dti_pts = (1 - min(dti / config.MAX_DEBT_TO_INCOME, 1)) * w["dti"]
        history_pts = min(borrower.credit_history_years, 10) / 10 * w["history"]
        lti = request.amount / (borrower.monthly_income * 12)
        lti_pts = (1 - min(lti, 1)) * w["loan_to_income"]
        components = {"credit": round(credit, 2), "dti": round(dti_pts, 2),
                      "history": round(history_pts, 2), "loan_to_income": round(lti_pts, 2)}
        total = round(sum(components.values()), 2)
        category = self.classify(total)
        rate = config.RATE_BY_RISK[category]
        explanation = (
            f"Risk score {total}/100 -> {category.upper()} risk (low >= {config.LOW_RISK_MIN_SCORE}, "
            f"medium >= {config.MEDIUM_RISK_MIN_SCORE}). "
            f"Credit score {borrower.credit_score}: {components['credit']}/{w['credit']}. "
            f"Debt-to-income {dti:.0%}: {components['dti']}/{w['dti']}. "
            f"Credit history {borrower.credit_history_years:g} years: {components['history']}/{w['history']}. "
            f"Loan is {lti:.0%} of annual income: {components['loan_to_income']}/{w['loan_to_income']}. "
            f"Offered interest rate for {category} risk: {rate:g}% per year.")
        return RiskResult(total, category, components, explanation, rate)


# ---------------------------------------------------------------------------
# 2. Pair compatibility
# ---------------------------------------------------------------------------
@dataclass
class PairResult:
    eligible: bool
    score: float = 0.0
    risk_fit: float = 0.0
    amount_fit: float = 0.0
    term_fit: float = 0.0
    return_fit: float = 0.0
    violations: list = field(default_factory=list)  # list of (code, message)
    explanation: str = ""

    @property
    def violation_codes(self):
        return [code for code, _ in self.violations]


def _centrality(value, low, high, floor):
    """1.0 at the middle of [low, high], falling to `floor` at the edges."""
    half = (high - low) / 2
    if half == 0:
        return 1.0
    return 1 - (1 - floor) * abs(value - (low + high) / 2) / half


class CompatibilityScorer:
    def __init__(self, allow_partial=False):
        self.allow_partial = allow_partial

    # ---- hard constraints -------------------------------------------------
    def check_constraints(self, lender, borrower, request, risk):
        v = []
        if not lender.is_matchable():
            v.append(("LENDER_INACTIVE", "Lender profile is not active."))
        if not borrower.is_matchable():
            v.append(("BORROWER_INACTIVE", "Borrower profile is not active."))
        if not lender.accepts_risk(risk.category):
            v.append(("RISK_APPETITE", f"Borrower is {risk.category} risk but the lender only accepts up to "
                                       f"{lender.risk_appetite} risk."))
        if not lender.accepts_amount(request.amount):
            v.append(("AMOUNT_RANGE", f"Loan amount {request.amount:,.0f} is outside the lender's range "
                                      f"{lender.min_loan_amount:,.0f}-{lender.max_loan_amount:,.0f}."))
        needed = request.amount * (config.MIN_PARTIAL_FRACTION if self.allow_partial else 1)
        if not lender.can_fund(needed):
            v.append(("INSUFFICIENT_FUNDS", f"Lender has {lender.available_amount:,.0f} available but "
                                            f"{needed:,.0f} is needed."))
        if not lender.accepts_duration(request.term_months):
            v.append(("DURATION_RANGE", f"Term {request.term_months} months is outside the lender's range "
                                        f"{lender.min_duration_months}-{lender.max_duration_months} months."))
        if not lender.accepts_rate(risk.rate):
            v.append(("RETURN_RANGE", f"Rate {risk.rate:g}% for {risk.category} risk is outside the lender's "
                                      f"expected return {lender.min_expected_return:g}-"
                                      f"{lender.max_expected_return:g}%."))
        emi = request.monthly_instalment(risk.rate)
        ratio = (borrower.existing_obligations + emi) / borrower.monthly_income
        if ratio > config.MAX_DEBT_TO_INCOME:
            v.append(("AFFORDABILITY", f"Obligations plus the new instalment ({emi:,.0f}) are {ratio:.0%} of "
                                       f"income, above the {config.MAX_DEBT_TO_INCOME:.0%} limit."))
        return v

    # ---- soft scores ------------------------------------------------------
    def fits(self, lender, request, risk):
        diff = lender.risk_level - config.RISK_ORDER[risk.category]
        risk_fit = {0: 1.0, 1: 0.7}.get(diff, 0.4)
        band = _centrality(request.amount, lender.min_loan_amount, lender.max_loan_amount, 0.5)
        capacity = 1 - 0.5 * min(1.0, request.amount / lender.available_amount)
        amount_fit = (band + capacity) / 2
        term_fit = _centrality(request.term_months, lender.min_duration_months, lender.max_duration_months, 0.6)
        span = lender.max_expected_return - lender.min_expected_return
        return_fit = 1.0 if span == 0 else 0.5 + 0.5 * (risk.rate - lender.min_expected_return) / span
        return risk_fit, amount_fit, term_fit, return_fit

    def evaluate(self, lender, borrower, request, risk):
        violations = self.check_constraints(lender, borrower, request, risk)
        if violations:
            text = "REJECTED: " + " ".join(message for _, message in violations)
            return PairResult(False, violations=violations, explanation=text)
        w = config.SCORE_WEIGHTS
        rf, af, tf, ef = self.fits(lender, request, risk)
        pts = {"risk_fit": round(rf * w["risk_fit"], 2), "amount_fit": round(af * w["amount_fit"], 2),
               "term_fit": round(tf * w["term_fit"], 2), "return_fit": round(ef * w["return_fit"], 2)}
        total = round(sum(pts.values()), 2)
        text = (f"ELIGIBLE: compatibility {total}/100 = risk fit {pts['risk_fit']}/{w['risk_fit']} "
                f"(lender appetite {lender.risk_appetite}, borrower {risk.category}) + amount fit "
                f"{pts['amount_fit']}/{w['amount_fit']} (loan {request.amount:,.0f} vs lender band and funds) + "
                f"term fit {pts['term_fit']}/{w['term_fit']} ({request.term_months} months) + return fit "
                f"{pts['return_fit']}/{w['return_fit']} (rate {risk.rate:g}% in lender's "
                f"{lender.min_expected_return:g}-{lender.max_expected_return:g}% range).")
        return PairResult(True, total, pts["risk_fit"], pts["amount_fit"], pts["term_fit"], pts["return_fit"],
                          [], text)


# ---------------------------------------------------------------------------
# 3. Score every pair and store the result
# ---------------------------------------------------------------------------
def reset_unaccepted_matches(conn):
    """Forget earlier unaccepted results so scoring/matching can be re-run."""
    conn.execute("UPDATE loan_requests SET status = 'pending' WHERE status = 'matched'")
    conn.execute("DELETE FROM matches WHERE status IN ('recommended', 'rejected', 'expired')")


def score_all(conn, allow_partial=False):
    """Score all active lenders against all pending requests. Returns a summary dict."""
    started = time.perf_counter()
    reset_unaccepted_matches(conn)
    lenders = profile_service.list_lenders(conn, profile_status="active")
    requests = [r for r in conn.execute(
        "SELECT request_id FROM loan_requests WHERE status = 'pending' ORDER BY request_id")]
    scorer, risk_scorer = CompatibilityScorer(allow_partial), RiskScorer()
    match_rows, eligible, rejected, skipped = [], 0, 0, 0
    for row in requests:
        request = profile_service.get_request(conn, row["request_id"])
        borrower = profile_service.get_borrower(conn, request.borrower_id)
        if borrower is None or not borrower.is_matchable():
            skipped += 1
            continue
        risk = risk_scorer.score(borrower, request)
        conn.execute("DELETE FROM risk_scores WHERE request_id = ?", (request.request_id,))
        conn.execute("INSERT INTO risk_scores(borrower_id, request_id, score, risk_category, components, explanation)"
                     " VALUES (?, ?, ?, ?, ?, ?)",
                     (request.borrower_id, request.request_id, risk.score, risk.category,
                      json.dumps(risk.components), risk.explanation))
        for lender in lenders:
            result = scorer.evaluate(lender, borrower, request, risk)
            if result.eligible:
                eligible += 1
            else:
                rejected += 1
            match_rows.append((lender.lender_id, request.request_id, result.score, result.risk_fit,
                               result.amount_fit, result.term_fit, result.return_fit, 0.0,
                               "recommended" if result.eligible else "rejected", result.explanation))
    conn.executemany(
        "INSERT INTO matches(lender_id, request_id, compatibility_score, risk_fit, amount_fit, term_fit,"
        " return_fit, allocated_amount, status, explanation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", match_rows)
    audit.log(conn, "system", None, "SCORING_RUN", None,
              details=f"{len(match_rows)} pairs, {eligible} eligible, {rejected} rejected")
    conn.commit()
    return {"requests_scored": len(requests) - skipped, "lenders": len(lenders), "pairs": len(match_rows),
            "eligible": eligible, "rejected": rejected, "seconds": round(time.perf_counter() - started, 4)}
