"""User management routes."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from asset_manager.database.db import log_activity
from asset_manager.database.models import Role, User
from asset_manager.extensions import bcrypt, db
from asset_manager.forms import UserForm
from asset_manager.routes.auth import roles_required

bp = Blueprint("users", __name__, url_prefix="/users")


@bp.route("/")
@roles_required(Role.ADMIN, Role.MODERATOR)
def list_users():
    return render_template("users.html", users=User.query.order_by(User.last_name, User.first_name).all(), form=UserForm())


@bp.route("/create", methods=("POST",))
@roles_required(Role.ADMIN, Role.MODERATOR)
def create():
    form = UserForm()
    if form.validate_on_submit():
        role = request.form.get("role", Role.VIEWER) if current_user.role == Role.ADMIN else Role.VIEWER
        user = User(
            first_name=form.first_name.data.strip(),
            last_name=form.last_name.data.strip(),
            email=form.email.data.strip().lower(),
            phone=form.phone.data,
            password_hash=bcrypt.generate_password_hash(form.password.data).decode("utf-8"),
            role=role,
        )
        db.session.add(user)
        db.session.commit()
        log_activity(current_user.id, "User Creation", "User", user.id, user.email)
        flash("User created.", "success")
    else:
        flash("User could not be created. Check the form fields.", "danger")
    return redirect(url_for("users.list_users"))


@bp.route("/<int:user_id>/role", methods=("POST",))
@roles_required(Role.ADMIN)
def update_role(user_id):
    user = User.query.get_or_404(user_id)
    user.role = request.form["role"]
    db.session.commit()
    log_activity(current_user.id, "Role Change", "User", user.id, f"Role changed to {user.role}")
    flash("User role updated.", "success")
    return redirect(url_for("users.list_users"))


@bp.route("/<int:user_id>/disable", methods=("POST",))
@roles_required(Role.ADMIN)
def disable(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot disable your own account.", "danger")
    else:
        user.is_active_account = False
        db.session.commit()
        log_activity(current_user.id, "Account Disable", "User", user.id, user.email)
        flash("User disabled.", "success")
    return redirect(url_for("users.list_users"))


@bp.route("/<int:user_id>/enable", methods=("POST",))
@roles_required(Role.ADMIN)
def enable(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active_account = True
    db.session.commit()
    log_activity(current_user.id, "Account Enable", "User", user.id, user.email)
    flash("User enabled.", "success")
    return redirect(url_for("users.list_users"))


@bp.route("/<int:user_id>/reset-password", methods=("POST",))
@roles_required(Role.ADMIN, Role.MODERATOR)
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    password = request.form["password"]
    if len(password) < 10:
        flash("Password must be at least 10 characters.", "danger")
        return redirect(url_for("users.list_users"))
    user.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    db.session.commit()
    log_activity(current_user.id, "Password Reset", "User", user.id, "Password reset by staff")
    flash("Password reset.", "success")
    return redirect(url_for("users.list_users"))
