"""Week 2 - OOP domain models: User, Lender, Borrower, LoanRequest, Match, Loan, Repayment.
Every class validates its own data (validate() returns a list of error strings)
and exposes small behaviours that the scoring / matching engines reuse.
"""
import math
import re
from dataclasses import asdict, dataclass
import config

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EXPECTED_RETURN = 50.0  # annual %, sanity limit for lender profiles
PROFILE_STATUSES = ("pending", "active", "inactive", "rejected")
USER_STATUSES = ("active", "inactive", "suspended")


class ValidationError(Exception):
    """Raised by the services when data is missing or invalid."""
    def __init__(self, errors):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def calculate_emi(principal, annual_rate_pct, months):
    """Equated monthly instalment (standard reducing-balance formula)."""
    if months <= 0:
        raise ValueError("months must be positive")
    r = annual_rate_pct / 12.0 / 100.0
    if r == 0:
        return round(principal / months, 2)
    return round(principal * r / (1 - (1 + r) ** (-months)), 2)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class User:
    """Base class for every person in the system."""
    ROLE = "admin"

    def __init__(self, full_name, email, status="active", user_id=None, password_hash=""):
        self.user_id = user_id
        self.full_name = (full_name or "").strip()
        self.email = (email or "").strip().lower()
        self.status = status
        self.password_hash = password_hash

    @property
    def role(self):
        return self.ROLE

    def validate(self):
        errors = []
        if len(self.full_name) < 2:
            errors.append("Full name must have at least 2 characters.")
        if not EMAIL_RE.match(self.email):
            errors.append("A valid email address is required.")
        if self.status not in USER_STATUSES:
            errors.append(f"User status must be one of {USER_STATUSES}.")
        return errors

    def is_active(self):
        return self.status == "active"

    def to_dict(self):
        data = dict(vars(self))
        data.pop("password_hash", None)
        data["role"] = self.role
        return data


class Lender(User):
    ROLE = "lender"

    def __init__(self, full_name, email, risk_appetite, available_amount,
                 min_loan_amount, max_loan_amount, min_duration_months, max_duration_months,
                 min_expected_return, max_expected_return, profile_status="pending",
                 lender_id=None, **user_kwargs):
        super().__init__(full_name, email, **user_kwargs)
        self.lender_id = lender_id
        self.risk_appetite = (risk_appetite or "").strip().lower() if isinstance(risk_appetite, str) else risk_appetite
        self.available_amount = available_amount
        self.min_loan_amount = min_loan_amount
        self.max_loan_amount = max_loan_amount
        self.min_duration_months = min_duration_months
        self.max_duration_months = max_duration_months
        self.min_expected_return = min_expected_return
        self.max_expected_return = max_expected_return
        self.profile_status = profile_status

    # ---- validation --------------------------------------------------------
    def validate(self):
        errors = super().validate()
        if self.risk_appetite not in config.RISK_LEVELS:
            errors.append(f"Risk appetite must be one of {config.RISK_LEVELS}.")
        numeric = {
            "Available amount": self.available_amount, "Minimum loan amount": self.min_loan_amount,
            "Maximum loan amount": self.max_loan_amount, "Minimum duration": self.min_duration_months,
            "Maximum duration": self.max_duration_months, "Minimum expected return": self.min_expected_return,
            "Maximum expected return": self.max_expected_return}
        bad = [label for label, v in numeric.items() if not _is_number(v)]
        if bad:
            return errors + [f"{label} must be a number." for label in bad]
        if self.available_amount <= 0:
            errors.append("Available amount must be greater than 0.")
        if not config.MIN_LOAN_AMOUNT <= self.min_loan_amount <= self.max_loan_amount <= config.MAX_LOAN_AMOUNT:
            errors.append(f"Loan amount preference must satisfy {config.MIN_LOAN_AMOUNT} <= minimum <= "
                          f"maximum <= {config.MAX_LOAN_AMOUNT}.")
        if not config.MIN_TERM_MONTHS <= self.min_duration_months <= self.max_duration_months <= config.MAX_TERM_MONTHS:
            errors.append(f"Duration preference must satisfy {config.MIN_TERM_MONTHS} <= minimum <= "
                          f"maximum <= {config.MAX_TERM_MONTHS} months.")
        if not 0 <= self.min_expected_return <= self.max_expected_return <= MAX_EXPECTED_RETURN:
            errors.append(f"Expected return must satisfy 0 <= minimum <= maximum <= {MAX_EXPECTED_RETURN}%.")
        if self.profile_status not in PROFILE_STATUSES:
            errors.append(f"Profile status must be one of {PROFILE_STATUSES}.")
        return errors

    # ---- behaviour used by the matching engine ----------------------------
    @property
    def risk_level(self):
        return config.RISK_ORDER[self.risk_appetite]

    def is_matchable(self):
        return self.is_active() and self.profile_status == "active"

    def accepts_risk(self, category):
        return config.RISK_ORDER[category] <= self.risk_level

    def accepts_amount(self, amount):
        return self.min_loan_amount <= amount <= self.max_loan_amount

    def accepts_duration(self, months):
        return self.min_duration_months <= months <= self.max_duration_months

    def accepts_rate(self, rate):
        return self.min_expected_return <= rate <= self.max_expected_return

    def can_fund(self, amount):
        return self.available_amount + 1e-9 >= amount

    @classmethod
    def from_row(cls, row):
        return cls(row["full_name"], row["email"], row["risk_appetite"], row["available_amount"],
                   row["min_loan_amount"], row["max_loan_amount"], row["min_duration_months"],
                   row["max_duration_months"], row["min_expected_return"], row["max_expected_return"],
                   profile_status=row["profile_status"], lender_id=row["lender_id"],
                   user_id=row["user_id"], status=row["status"])


class Borrower(User):
    ROLE = "borrower"

    def __init__(self, full_name, email, monthly_income, existing_obligations, credit_score,
                 credit_history_years, profile_status="pending", borrower_id=None, **user_kwargs):
        super().__init__(full_name, email, **user_kwargs)
        self.borrower_id = borrower_id
        self.monthly_income = monthly_income
        self.existing_obligations = existing_obligations
        self.credit_score = credit_score
        self.credit_history_years = credit_history_years
        self.profile_status = profile_status

    def validate(self):
        errors = super().validate()
        numeric = {"Monthly income": self.monthly_income, "Existing obligations": self.existing_obligations,
                   "Credit score": self.credit_score, "Credit history": self.credit_history_years}
        bad = [label for label, v in numeric.items() if not _is_number(v)]
        if bad:
            return errors + [f"{label} must be a number." for label in bad]
        if self.monthly_income <= 0:
            errors.append("Monthly income must be greater than 0.")
        if self.existing_obligations < 0:
            errors.append("Existing obligations cannot be negative.")
        if not 300 <= self.credit_score <= 900:
            errors.append("Credit score must be between 300 and 900.")
        if not 0 <= self.credit_history_years <= 60:
            errors.append("Credit history must be between 0 and 60 years.")
        if self.profile_status not in PROFILE_STATUSES:
            errors.append(f"Profile status must be one of {PROFILE_STATUSES}.")
        return errors

    def debt_to_income(self):
        return self.existing_obligations / self.monthly_income

    def is_matchable(self):
        return self.is_active() and self.profile_status == "active"

    @classmethod
    def from_row(cls, row):
        return cls(row["full_name"], row["email"], row["monthly_income"], row["existing_obligations"],
                   row["credit_score"], row["credit_history_years"], profile_status=row["profile_status"],
                   borrower_id=row["borrower_id"], user_id=row["user_id"], status=row["status"])


# ---------------------------------------------------------------------------
# Lending objects
# ---------------------------------------------------------------------------
@dataclass
class LoanRequest:
    borrower_id: int
    amount: float
    term_months: int
    purpose: str = ""
    status: str = "pending"
    request_id: int = None

    def validate(self):
        errors = []
        if not _is_number(self.amount):
            errors.append("Loan amount must be a number.")
        elif not config.MIN_LOAN_AMOUNT <= self.amount <= config.MAX_LOAN_AMOUNT:
            errors.append(f"Loan amount must be between {config.MIN_LOAN_AMOUNT} and {config.MAX_LOAN_AMOUNT}.")
        if not _is_number(self.term_months) or int(self.term_months) != self.term_months:
            errors.append("Repayment term must be a whole number of months.")
        elif not config.MIN_TERM_MONTHS <= self.term_months <= config.MAX_TERM_MONTHS:
            errors.append(f"Repayment term must be between {config.MIN_TERM_MONTHS} and "
                          f"{config.MAX_TERM_MONTHS} months.")
        if len(self.purpose or "") > 200:
            errors.append("Purpose must be at most 200 characters.")
        return errors

    def monthly_instalment(self, annual_rate_pct):
        return calculate_emi(self.amount, annual_rate_pct, int(self.term_months))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_row(cls, row):
        return cls(row["borrower_id"], row["amount"], row["term_months"], row["purpose"] or "",
                   row["status"], row["request_id"])


@dataclass
class Match:
    lender_id: int
    request_id: int
    compatibility_score: float = 0.0
    risk_fit: float = 0.0
    amount_fit: float = 0.0
    term_fit: float = 0.0
    return_fit: float = 0.0
    allocated_amount: float = 0.0
    status: str = "recommended"
    explanation: str = ""
    match_id: int = None

    def is_selected(self):
        return self.status in ("recommended", "accepted") and self.allocated_amount > 0

    def to_dict(self):
        return asdict(self)


@dataclass
class Loan:
    match_id: int
    lender_id: int
    borrower_id: int
    principal: float
    interest_rate: float
    duration_months: int
    outstanding_balance: float = None
    status: str = "active"
    start_date: str = None
    loan_id: int = None

    def monthly_instalment(self):
        return calculate_emi(self.principal, self.interest_rate, self.duration_months)

    def to_dict(self):
        return asdict(self)


@dataclass
class Repayment:
    loan_id: int
    installment_no: int
    due_date: str
    amount_due: float
    amount_paid: float = 0.0
    status: str = "pending"
    paid_date: str = None
    repayment_id: int = None

    def is_settled(self):
        return self.status in ("paid", "late")

    def to_dict(self):
        return asdict(self)
