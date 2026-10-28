"""Authentication and session management routes: login, logout, my-dashboard."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from utils import db_conn

bp = Blueprint("auth", __name__)


def _ensure_default_admin(conn):
    """Ensure default admin account exists in database for administrator login."""
    admin = conn.execute("SELECT user_id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
    if not admin:
        pw = generate_password_hash("password123")
        conn.execute(
            "INSERT INTO users (full_name, email, password_hash, role, status) VALUES (?, ?, ?, ?, 'active')",
            ("Administrator", "admin@p2p.test", pw, "admin")
        )
        conn.commit()


@bp.route("/login", methods=["GET", "POST"])
def login():
    demo = request.args.get("demo", "").strip().lower()

    with db_conn() as conn:
        _ensure_default_admin(conn)

        # Quick 1-click login for demo / presentation
        if demo in ("admin", "lender", "borrower"):
            if demo == "admin":
                user = conn.execute("SELECT * FROM users WHERE role = 'admin' LIMIT 1").fetchone()
            elif demo == "lender":
                user = conn.execute("SELECT * FROM users WHERE role = 'lender' LIMIT 1").fetchone()
            else:
                user = conn.execute("SELECT * FROM users WHERE role = 'borrower' LIMIT 1").fetchone()

            if user:
                return _setup_session_and_redirect(conn, user)

        if request.method == "POST":
            email = str(request.form.get("email") or "").strip().lower()
            password = str(request.form.get("password") or "")

            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                if user["status"] != "active":
                    flash(f"Account is {user['status']}. Please contact support.", "danger")
                    return render_template("login.html", email=email)
                return _setup_session_and_redirect(conn, user)

            flash("Invalid email or password.", "danger")
            return render_template("login.html", email=email)

    return render_template("login.html")


def _setup_session_and_redirect(conn, user):
    session.clear()
    session["user_id"] = user["user_id"]
    session["full_name"] = user["full_name"]
    session["email"] = user["email"]
    session["role"] = user["role"]

    flash(f"Welcome, {user['full_name']}! You are logged in as {user['role'].capitalize()}.", "success")

    if user["role"] == "admin":
        return redirect(url_for("dashboard.admin"))
    elif user["role"] == "lender":
        lender = conn.execute("SELECT lender_id FROM lenders WHERE user_id = ?", (user["user_id"],)).fetchone()
        if lender:
            session["lender_id"] = lender["lender_id"]
            return redirect(url_for("dashboard.lender", lender_id=lender["lender_id"]))
        return redirect(url_for("profiles.lenders"))
    elif user["role"] == "borrower":
        borrower = conn.execute("SELECT borrower_id FROM borrowers WHERE user_id = ?", (user["user_id"],)).fetchone()
        if borrower:
            session["borrower_id"] = borrower["borrower_id"]
            return redirect(url_for("dashboard.borrower", borrower_id=borrower["borrower_id"]))
        return redirect(url_for("profiles.borrowers"))

    return redirect(url_for("home"))


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/my-dashboard")
def my_dashboard():
    user_id = session.get("user_id")
    role = session.get("role")

    if not user_id:
        flash("Please log in to view your dashboard.", "info")
        return redirect(url_for("auth.login"))

    with db_conn() as conn:
        if role == "admin":
            return redirect(url_for("dashboard.admin"))
        elif role == "lender":
            lender_id = session.get("lender_id")
            if not lender_id:
                row = conn.execute("SELECT lender_id FROM lenders WHERE user_id = ?", (user_id,)).fetchone()
                lender_id = row["lender_id"] if row else None
            if lender_id:
                return redirect(url_for("dashboard.lender", lender_id=lender_id))
            return redirect(url_for("profiles.lenders"))
        elif role == "borrower":
            borrower_id = session.get("borrower_id")
            if not borrower_id:
                row = conn.execute("SELECT borrower_id FROM borrowers WHERE user_id = ?", (user_id,)).fetchone()
                borrower_id = row["borrower_id"] if row else None
            if borrower_id:
                return redirect(url_for("dashboard.borrower", borrower_id=borrower_id))
            return redirect(url_for("profiles.borrowers"))

    return redirect(url_for("home"))
