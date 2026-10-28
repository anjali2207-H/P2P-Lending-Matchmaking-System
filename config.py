"""Central configuration and business rules for the P2P Lending Matchmaking System.
Rules defined in Week 1 are reused by the scoring (Week 3) and matching (Week 4) engines."""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "p2p_lending.db")
SECRET_KEY = "change-this-in-production"   # academic project only

# ---------- Allowed values ----------
ROLES = ("lender", "borrower", "admin")
RISK_LEVELS = ("low", "medium", "high")
RISK_ORDER = {"low": 1, "medium": 2, "high": 3}

# ---------- Simulated interest rate (annual %) offered for each borrower risk class ----------
RATE_BY_RISK = {"low": 9.0, "medium": 14.0, "high": 20.0}

# ---------- Hard (mandatory) matching rules: failing any one => pair is rejected ----------
MAX_DEBT_TO_INCOME = 0.60       # existing_obligations / monthly_income
MIN_LOAN_AMOUNT = 1000          # system-wide limits (simulated currency units)
MAX_LOAN_AMOUNT = 1000000
MIN_TERM_MONTHS = 3
MAX_TERM_MONTHS = 60

# ---------- Soft scoring: Compatibility Score = Risk Fit + Amount Fit + Term Fit + Return Fit ----------
SCORE_WEIGHTS = {"risk_fit": 40, "amount_fit": 25, "term_fit": 15, "return_fit": 20}   # total = 100
assert sum(SCORE_WEIGHTS.values()) == 100

# ---------- Borrower risk classification thresholds (risk score 0-100, higher = safer) ----------
LOW_RISK_MIN_SCORE = 70
MEDIUM_RISK_MIN_SCORE = 45      # below this => high risk

# ===========================================================================
# ---- Added in Week 3 (risk and compatibility scoring) ---------------------
# ===========================================================================
# Borrower risk score (0-100, higher = safer). The four parts add up to 100.
RISK_SCORE_WEIGHTS = {"credit": 40, "dti": 30, "history": 15, "loan_to_income": 15}

# Partial funding (optional enhancement): a lender must hold at least this
# fraction of a loan before it may co-fund it.
MIN_PARTIAL_FRACTION = 0.20

# ---- Added in Week 5 (loan simulation) ------------------------------------
LATE_FEE_RATE = 0.02   # late fee = 2% of the instalment
LATE_DAYS = 7          # a late instalment is paid 7 days after the due date
# probability of (paid on time, paid late, defaulted) for each instalment
REPAYMENT_PROBABILITIES = {
    "low": (0.92, 0.07, 0.01),
    "medium": (0.80, 0.15, 0.05),
    "high": (0.65, 0.22, 0.13),
}
