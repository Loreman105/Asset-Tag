"""Authentication routes."""

from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from asset_manager.database.db import log_activity
from asset_manager.database.models import Role, User
from asset_manager.extensions import bcrypt, db
from asset_manager.forms import LoginForm

bp = Blueprint("auth", __name__)


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped_view(**kwargs):
            if current_user.role not in roles:
                flash("You do not have permission to access that page.", "danger")
                return redirect(url_for("assets.dashboard"))
            return view(**kwargs)

        return wrapped_view

    return decorator


def asset_manager_required(view):
    return roles_required(Role.ADMIN, Role.MODERATOR)(view)


@bp.route("/login", methods=("GET", "POST"))
def login():
    if current_user.is_authenticated:
        return redirect(url_for("assets.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user and user.is_active and bcrypt.check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember.data)
            user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            log_activity(user.id, "Login", "User", user.id, "User signed in")
            return redirect(request.args.get("next") or url_for("assets.dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    log_activity(current_user.id, "Logout", "User", current_user.id, "User signed out")
    logout_user()
    return redirect(url_for("auth.login"))
