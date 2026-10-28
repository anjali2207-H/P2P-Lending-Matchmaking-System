"""Flask application entry point.
Supports automatic blueprint registration, session-based authentication,
and dynamic role navigation across all modules.
"""
import importlib
import os
import sys

# Ensure p2p_lending directory is in Python path even if invoked from parent directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask, jsonify, render_template, session
import config
from database import get_connection, init_db, list_tables
from utils import db_conn

BLUEPRINT_MODULES = [
    "routes.auth",       # Authentication & Login (Session management)
    "routes.profiles",   # Week 2
    "routes.scoring",    # Week 3
    "routes.matching",   # Week 4
    "routes.loans",      # Week 5
    "routes.dashboard",  # Week 6
    "routes.reports",    # Week 6
    "routes.api",        # Week 6
]

# (menu label, endpoint) - a menu item appears only when its endpoint exists
NAV_ITEMS = [
    ("Register Lender", "profiles.register_lender"),
    ("Register Borrower", "profiles.register_borrower"),
    ("Lenders", "profiles.lenders"),
    ("Borrowers", "profiles.borrowers"),
    ("Requests", "profiles.requests"),
    ("Risk Scores", "scoring.risk_scores"),
    ("Scored Pairs", "scoring.pairs"),
    ("Recommendations", "matching.recommendations"),
    ("Pending Funding", "loans.pending"),
    ("Loans", "loans.loans"),
    ("Admin", "dashboard.admin"),
    ("Audit", "reports.audit_log"),
]


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    if db_path:
        config.DATABASE_PATH = db_path
    init_db()

    for module_name in BLUEPRINT_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:  # a genuine error inside an existing module
                raise
            continue  # this week's file does not exist yet
        app.register_blueprint(module.bp)

    @app.context_processor
    def inject_navigation():
        return {
            "nav_items": [(label, ep) for label, ep in NAV_ITEMS if ep in app.view_functions],
            "current_user_id": session.get("user_id"),
            "current_user_role": session.get("role"),
            "current_user_name": session.get("full_name")
        }

    @app.route("/")
    def home():
        counts = {}
        with db_conn() as conn:
            for table in list_tables():
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return render_template("index.html", counts=counts)

    @app.route("/health")
    def health():
        return jsonify(status="ok", project="P2P Lending Matchmaking System")

    @app.route("/api/tables")
    def api_tables():
        conn = get_connection()
        try:
            return jsonify({t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in list_tables()})
        finally:
            conn.close()

    @app.route("/api/rules")
    def api_rules():
        return jsonify(
            rate_by_risk=config.RATE_BY_RISK,
            score_weights=config.SCORE_WEIGHTS,
            max_debt_to_income=config.MAX_DEBT_TO_INCOME,
            loan_amount_limits=[config.MIN_LOAN_AMOUNT, config.MAX_LOAN_AMOUNT],
            term_limits_months=[config.MIN_TERM_MONTHS, config.MAX_TERM_MONTHS],
        )

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=True)
