"""Week 6 - Flask REST API: the web interface and external tools talk to the
profile, scoring, matching and loan modules through these JSON endpoints."""
from flask import Blueprint, jsonify, request
import loan_service as ls
import profile_service as ps
import queries
import reports
import scoring
from matching_engine import MatchingEngine
from models import ValidationError
from utils import db_conn

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.errorhandler(ValidationError)
def handle_validation_error(exc):
    return jsonify(error="validation_failed", messages=exc.errors), 400


def _body():
    return request.get_json(silent=True) or {}


# ---- read ------------------------------------------------------------------
@bp.route("/lenders")
def lenders():
    with db_conn() as conn:
        return jsonify([l.to_dict() for l in ps.list_lenders(conn)])


@bp.route("/borrowers")
def borrowers():
    with db_conn() as conn:
        return jsonify([b.to_dict() for b in ps.list_borrowers(conn)])


@bp.route("/requests")
def requests_list():
    with db_conn() as conn:
        return jsonify(ps.list_requests(conn, status=request.args.get("status")))


@bp.route("/risk-scores")
def risk_scores():
    with db_conn() as conn:
        return jsonify(queries.list_risk_scores(conn))


@bp.route("/matches")
def matches():
    with db_conn() as conn:
        return jsonify(queries.list_pairs(conn, status=request.args.get("status"),
                                          request_id=request.args.get("request_id", type=int)))


@bp.route("/loans")
def loans():
    with db_conn() as conn:
        return jsonify(ls.list_loans(conn))


@bp.route("/loans/<int:loan_id>/repayments")
def repayments(loan_id):
    with db_conn() as conn:
        if ls.get_loan(conn, loan_id) is None:
            return jsonify(error="not_found"), 404
        return jsonify(ls.get_repayments(conn, loan_id))


@bp.route("/stats")
def stats():
    with db_conn() as conn:
        return jsonify({label: value for label, value in reports.system_stats(conn)})


# ---- write -----------------------------------------------------------------
@bp.route("/lenders", methods=["POST"])
def create_lender():
    with db_conn() as conn:
        return jsonify(lender_id=ps.register_lender(conn, _body())), 201


@bp.route("/borrowers", methods=["POST"])
def create_borrower():
    with db_conn() as conn:
        return jsonify(borrower_id=ps.register_borrower(conn, _body())), 201


@bp.route("/profiles/<role>/<int:profile_id>/status", methods=["POST"])
def profile_status(role, profile_id):
    with db_conn() as conn:
        ps.set_profile_status(conn, role, profile_id, _body().get("status", ""))
        return jsonify(ok=True)


@bp.route("/requests", methods=["POST"])
def create_request():
    data = _body()
    with db_conn() as conn:
        try:
            borrower_id = int(data.get("borrower_id"))
        except (TypeError, ValueError):
            raise ValidationError("borrower_id is required.")
        return jsonify(request_id=ps.create_loan_request(conn, borrower_id, data)), 201


@bp.route("/scoring/run", methods=["POST"])
def run_scoring():
    with db_conn() as conn:
        return jsonify(scoring.score_all(conn, allow_partial=bool(_body().get("partial"))))


@bp.route("/matching/run", methods=["POST"])
def run_matching():
    with db_conn() as conn:
        return jsonify(MatchingEngine(conn, allow_partial=bool(_body().get("partial"))).run())


@bp.route("/loans/accept/<int:request_id>", methods=["POST"])
def accept(request_id):
    with db_conn() as conn:
        return jsonify(loan_ids=ls.accept_request(conn, request_id)), 201


@bp.route("/loans/<int:loan_id>/simulate", methods=["POST"])
def simulate(loan_id):
    data = _body()
    with db_conn() as conn:
        return jsonify(ls.simulate_loan(conn, loan_id, data.get("scenario", "random"), data.get("seed")))
