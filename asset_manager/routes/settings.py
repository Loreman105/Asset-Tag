"""Administrator settings routes."""

import json
from pathlib import Path
from zipfile import BadZipFile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, current_app, flash, render_template, request, redirect, send_file, url_for
from flask_login import current_user

from asset_manager.database.db import log_activity
from asset_manager.database.models import Category, DepartmentPrefix, Role, Setting, StatusValue
from asset_manager.extensions import db
from asset_manager.routes.auth import roles_required
from asset_manager.utils import PHOTO_EXTENSIONS, save_upload, setting_value
from asset_manager.backup import create_backup, encrypt_secret, restore_backup

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
        elif action == "backup_schedule":
            frequency = request.form.get("backup_frequency", "disabled")
            retention = request.form.get("backup_retention", "10")
            if frequency not in {"disabled", "daily", "weekly"} or not retention.isdigit() or not 1 <= int(retention) <= 100:
                flash("Choose a valid backup schedule and keep 1 to 100 backups.", "danger")
                return redirect(url_for("settings.index"))
            Setting.query.filter_by(key="backup_frequency").first().value = frequency
            Setting.query.filter_by(key="backup_retention").first().value = retention
        elif action == "backup_destination":
            destination = request.form.get("backup_destination", "local")
            if destination not in {"local", "network_share", "sftp", "s3"}:
                flash("Choose a supported backup destination.", "danger")
                return redirect(url_for("settings.index"))
            updates = {
                "backup_destination": destination,
                "backup_network_path": request.form.get("backup_network_path", "").strip(),
                "backup_sftp_host": request.form.get("backup_sftp_host", "").strip(),
                "backup_sftp_port": request.form.get("backup_sftp_port", "22").strip(),
                "backup_sftp_username": request.form.get("backup_sftp_username", "").strip(),
                "backup_sftp_path": request.form.get("backup_sftp_path", "").strip(),
                "backup_s3_endpoint": request.form.get("backup_s3_endpoint", "").strip(),
                "backup_s3_region": request.form.get("backup_s3_region", "us-east-1").strip(),
                "backup_s3_bucket": request.form.get("backup_s3_bucket", "").strip(),
                "backup_s3_prefix": request.form.get("backup_s3_prefix", "inventory-hub").strip(),
                "backup_s3_access_key": request.form.get("backup_s3_access_key", "").strip(),
            }
            if not updates["backup_sftp_port"].isdigit() or not 1 <= int(updates["backup_sftp_port"]) <= 65535:
                flash("Enter a valid SFTP port.", "danger")
                return redirect(url_for("settings.index"))
            for key, value in updates.items():
                Setting.query.filter_by(key=key).first().value = value
            for form_key, setting_key in (("backup_sftp_password", "backup_sftp_password"), ("backup_s3_secret_key", "backup_s3_secret_key")):
                secret = request.form.get(form_key, "")
                if secret:
                    existing = Setting.query.filter_by(key=setting_key).first()
                    if existing:
                        existing.value = encrypt_secret(secret)
                    else:
                        db.session.add(Setting(key=setting_key, value=encrypt_secret(secret)))
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
        backup_frequency=setting_value("backup_frequency", "disabled"),
        backup_retention=setting_value("backup_retention", "10"),
        backup_last_run=setting_value("backup_last_run"),
        backup_destination=setting_value("backup_destination", "local"),
        backup_network_path=setting_value("backup_network_path"),
        backup_sftp_host=setting_value("backup_sftp_host"),
        backup_sftp_port=setting_value("backup_sftp_port", "22"),
        backup_sftp_username=setting_value("backup_sftp_username"),
        backup_sftp_path=setting_value("backup_sftp_path"),
        backup_s3_endpoint=setting_value("backup_s3_endpoint"),
        backup_s3_region=setting_value("backup_s3_region", "us-east-1"),
        backup_s3_bucket=setting_value("backup_s3_bucket"),
        backup_s3_prefix=setting_value("backup_s3_prefix", "inventory-hub"),
        backup_s3_access_key=setting_value("backup_s3_access_key"),
        backup_remote_status=setting_value("backup_remote_status", "Not configured"),
        prefixes=DepartmentPrefix.query.order_by(DepartmentPrefix.code).all(),
        categories=Category.query.order_by(Category.name).all(),
        statuses=StatusValue.query.order_by(StatusValue.name).all(),
    )


@bp.get("/backup/export")
@roles_required(Role.ADMIN)
def export_backup():
    archive = create_backup()
    log_activity(current_user.id, "Backup Export", "System", "Backup", "Downloaded full system backup")
    return send_file(
        archive,
        mimetype="application/zip",
        as_attachment=True,
        download_name="inventory-hub-backup.zip",
    )


@bp.post("/backup/import")
@roles_required(Role.ADMIN)
def import_backup():
    if request.form.get("confirmation", "").strip().upper() != "RESTORE":
        flash("Type RESTORE to confirm replacing the current system data.", "danger")
        return redirect(url_for("settings.index"))
    upload = request.files.get("backup_file")
    if not upload or not upload.filename:
        flash("Choose an Inventory Hub backup ZIP file.", "danger")
        return redirect(url_for("settings.index"))
    try:
        restore_backup(upload)
    except (BadZipFile, ValueError, OSError, json.JSONDecodeError) as error:
        flash(f"Backup restore failed: {error}", "danger")
        return redirect(url_for("settings.index"))
    log_activity(current_user.id, "Backup Restore", "System", "Backup", f"Restored {upload.filename}")
    flash("Backup restored. You are now viewing the restored system.", "success")
    return redirect(url_for("settings.index"))
