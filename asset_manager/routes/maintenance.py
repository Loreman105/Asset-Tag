"""Maintenance routes."""

from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from asset_manager.database.db import log_activity
from asset_manager.database.models import Asset, AssetStatus, MaintenanceRecord, MaintenanceSchedule, MaintenanceType
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
        update_schedule_from_form(asset, record)
        asset.updated_by_id = current_user.id
        db.session.add(record)
        db.session.commit()
        log_activity(current_user.id, "Maintenance Record", "Asset", asset.asset_id, record.description)
        flash("Maintenance record added.", "success")
        return redirect(url_for("assets.detail", asset_id=asset.asset_id))
    return render_template(
        "maintenance.html",
        asset=asset,
        types=types,
        today=date.today().isoformat(),
        schedule=MaintenanceSchedule.query.filter_by(asset_id=asset.id).first(),
    )


@bp.route("/due")
@asset_manager_required
def due():
    today = date.today()
    schedules = (
        MaintenanceSchedule.query.join(Asset)
        .filter(Asset.status != AssetStatus.RETIRED)
        .order_by(MaintenanceSchedule.next_due_date, Asset.asset_id)
        .all()
    )
    due_now = [item for item in schedules if item.next_due_date <= today]
    upcoming = [item for item in schedules if today < item.next_due_date <= today + timedelta(days=30)]
    later = [item for item in schedules if item.next_due_date > today + timedelta(days=30)]
    return render_template("maintenance_due.html", due_now=due_now, upcoming=upcoming, later=later, today=today)


def update_schedule_from_form(asset, record):
    next_due_date = parse_date(request.form.get("next_due_date"))
    frequency_days = request.form.get("frequency_days")
    if request.form.get("use_frequency") and frequency_days:
        next_due_date = record.service_date + timedelta(days=int(frequency_days))
    if not next_due_date:
        return

    schedule = MaintenanceSchedule.query.filter_by(asset_id=asset.id).first()
    if schedule is None:
        schedule = MaintenanceSchedule(asset=asset)
        db.session.add(schedule)
    schedule.next_due_date = next_due_date
    schedule.frequency_days = int(frequency_days) if frequency_days else None
    schedule.service_type = request.form.get("next_service_type") or record.maintenance_type
    schedule.notes = request.form.get("schedule_notes")
    schedule.updated_by_id = current_user.id
