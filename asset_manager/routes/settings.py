"""Administrator settings routes."""

from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, current_app, flash, render_template, request, redirect, url_for
from flask_login import current_user

from asset_manager.database.db import log_activity
from asset_manager.database.models import Category, DepartmentPrefix, Role, Setting, StatusValue
from asset_manager.extensions import db
from asset_manager.routes.auth import roles_required
from asset_manager.utils import PHOTO_EXTENSIONS, save_upload, setting_value

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=("GET", "POST"))
@roles_required(Role.ADMIN)
def index():
    if request.method == "POST":
        action = request.form["action"]
        if action == "organization":
            name = request.form["organization_name"].strip()
            timezone_name = request.form["timezone"].strip()
            base_url = request.form["inventory_base_url"].strip().rstrip("/")
            if not name or not base_url:
                flash("Organization name and Inventory Hub URL are required.", "danger")
                return redirect(url_for("settings.index"))
            try:
                ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError:
                flash("Choose a valid IANA timezone, such as America/Chicago.", "danger")
                return redirect(url_for("settings.index"))
            Setting.query.filter_by(key="church_name").first().value = name
            Setting.query.filter_by(key="organization_timezone").first().value = timezone_name
            url_setting = Setting.query.filter_by(key="inventory_base_url").first()
            url_changed = url_setting.value != base_url
            url_setting.value = base_url
            logo = request.files.get("organization_logo")
            if logo and logo.filename:
                _, stored, _ = save_upload(logo, "branding", PHOTO_EXTENSIONS)
                Setting.query.filter_by(key="organization_logo").first().value = f"branding/{stored}"
            if url_changed:
                for qr_code in Path(current_app.config["QR_CODE_FOLDER"]).glob("*.png"):
                    qr_code.unlink()
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
        organization_name=setting_value("church_name", current_app.config["CHURCH_NAME"]),
        timezone_name=setting_value("organization_timezone", current_app.config["DEFAULT_TIMEZONE"]),
        inventory_base_url=setting_value("inventory_base_url", current_app.config["INVENTORY_BASE_URL"]),
        organization_logo=setting_value("organization_logo"),
        prefixes=DepartmentPrefix.query.order_by(DepartmentPrefix.code).all(),
        categories=Category.query.order_by(Category.name).all(),
        statuses=StatusValue.query.order_by(StatusValue.name).all(),
    )
