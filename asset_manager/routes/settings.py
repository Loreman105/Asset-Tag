"""Administrator settings routes."""

from flask import Blueprint, flash, render_template, request, redirect, url_for
from flask_login import current_user

from asset_manager.database.db import DEFAULT_COLOR_SETTINGS, log_activity
from asset_manager.database.models import Category, DepartmentPrefix, Role, Setting, StatusValue
from asset_manager.extensions import db
from asset_manager.routes.auth import roles_required

bp = Blueprint("settings", __name__, url_prefix="/settings")

COLOR_SETTING_LABELS = {
    "color_primary": "Primary Actions",
    "color_accent": "Links and Accents",
    "color_page_background": "Page Background",
    "color_nav_background": "Navigation Background",
    "color_card_background": "Cards and Panels",
    "color_body_text": "Body Text",
}


def is_hex_color(value):
    if not value or len(value) != 7 or not value.startswith("#"):
        return False
    return all(character in "0123456789abcdefABCDEF" for character in value[1:])


def upsert_setting(key, value):
    setting = Setting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        db.session.add(Setting(key=key, value=value))


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
        elif action == "colors":
            for key in COLOR_SETTING_LABELS:
                value = request.form.get(key, "").strip()
                if not is_hex_color(value):
                    flash(f"{COLOR_SETTING_LABELS[key]} must be a valid hex color.", "danger")
                    return redirect(url_for("settings.index"))
                upsert_setting(key, value.lower())
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
        color_labels=COLOR_SETTING_LABELS,
        color_settings=color_settings(),
    )


def color_settings():
    values = DEFAULT_COLOR_SETTINGS.copy()
    rows = Setting.query.filter(Setting.key.in_(COLOR_SETTING_LABELS)).all()
    for row in rows:
        if row.value:
            values[row.key] = row.value
    return values
