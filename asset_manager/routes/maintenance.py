"""Maintenance routes."""

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from asset_manager.database.db import log_activity
from asset_manager.database.models import Asset, AssetStatus, MaintenanceRecord, MaintenanceType
from asset_manager.extensions import db
from asset_manager.routes.assets import parse_date
from asset_manager.routes.auth import asset_manager_required

bp = Blueprint("maintenance", __name__, url_prefix="/maintenance")


@bp.route("/new/<asset_id>", methods=("GET", "POST"))
@asset_manager_required
def create(asset_id):
    asset = Asset.query.filter_by(asset_id=asset_id).first_or_404()
    types = [
        MaintenanceType.INSPECTION,
        MaintenanceType.REPAIR,
        MaintenanceType.UPGRADE,
        MaintenanceType.CLEANING,
        MaintenanceType.WARRANTY_SERVICE,
    ]
    if request.method == "POST":
        record = MaintenanceRecord(
            asset=asset,
            service_date=parse_date(request.form.get("service_date")) or date.today(),
            maintenance_type=request.form["maintenance_type"],
            description=request.form["description"],
            cost=request.form.get("cost") or None,
            performed_by_id=current_user.id,
            notes=request.form.get("notes"),
        )
        if request.form.get("mark_in_maintenance"):
            asset.status = AssetStatus.IN_MAINTENANCE
        asset.updated_by_id = current_user.id
        db.session.add(record)
        db.session.commit()
        log_activity(current_user.id, "Maintenance Record", "Asset", asset.asset_id, record.description)
        flash("Maintenance record added.", "success")
        return redirect(url_for("assets.detail", asset_id=asset.asset_id))
    return render_template("maintenance.html", asset=asset, types=types, today=date.today().isoformat())
