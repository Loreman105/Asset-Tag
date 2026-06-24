"""Administrator settings routes."""

from flask import Blueprint, flash, render_template, request, redirect, url_for
from flask_login import current_user

from asset_manager.database.db import log_activity
from asset_manager.database.models import Category, DepartmentPrefix, Role, Setting, StatusValue
from asset_manager.extensions import db
from asset_manager.routes.auth import roles_required

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=("GET", "POST"))
@roles_required(Role.ADMIN)
def index():
    if request.method == "POST":
        action = request.form["action"]
        if action == "church":
            setting = Setting.query.filter_by(key="church_name").first()
            setting.value = request.form["church_name"].strip()
        elif action == "prefix":
            db.session.add(DepartmentPrefix(code=request.form["code"].strip(), name=request.form["name"].strip()))
        elif action == "category":
            db.session.add(Category(name=request.form["name"].strip()))
        elif action == "status":
            db.session.add(StatusValue(name=request.form["name"].strip()))
        db.session.commit()
        log_activity(current_user.id, "Settings Update", "Settings", action, "Updated system settings")
        flash("Settings updated.", "success")
        return redirect(url_for("settings.index"))

    return render_template(
        "settings.html",
        church_name=(Setting.query.filter_by(key="church_name").first().value or ""),
        prefixes=DepartmentPrefix.query.order_by(DepartmentPrefix.code).all(),
        categories=Category.query.order_by(Category.name).all(),
        statuses=StatusValue.query.order_by(StatusValue.name).all(),
    )
