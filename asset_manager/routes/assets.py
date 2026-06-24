"""Asset inventory routes."""

from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from asset_manager.database.db import log_activity
from asset_manager.database.models import (
    Asset,
    AssetDocument,
    AssetPhoto,
    AssetStatus,
    Category,
    DepartmentPrefix,
    StatusValue,
    User,
)
from asset_manager.extensions import db
from asset_manager.routes.auth import asset_manager_required
from asset_manager.utils import (
    DOCUMENT_EXTENSIONS,
    PHOTO_EXTENSIONS,
    ensure_barcode,
    generate_asset_id,
    make_thumbnail,
    save_upload,
)

bp = Blueprint("assets", __name__)


@bp.route("/dashboard")
@login_required
def dashboard():
    total_assets = Asset.query.count()
    status_counts = {
        status: Asset.query.filter_by(status=status).count()
        for status in [
            AssetStatus.AVAILABLE,
            AssetStatus.CHECKED_OUT,
            AssetStatus.IN_MAINTENANCE,
            AssetStatus.RETIRED,
            AssetStatus.LOST,
            AssetStatus.DAMAGED,
        ]
    }
    warranty_alerts = (
        Asset.query.filter(
            Asset.warranty_expiration_date.isnot(None),
            Asset.warranty_expiration_date <= date.today() + timedelta(days=60),
            Asset.status != AssetStatus.RETIRED,
        )
        .order_by(Asset.warranty_expiration_date.asc())
        .limit(10)
        .all()
    )
    from asset_manager.database.models import (
        AssetRequest,
        AssetRequestStatus,
        AuditLog,
        Checkout,
        MaintenanceSchedule,
        Reservation,
        ReservationStatus,
    )

    overdue_checkouts = (
        Checkout.query.filter(
            Checkout.returned_at.is_(None),
            Checkout.expected_return_date.isnot(None),
            Checkout.expected_return_date < date.today(),
        )
        .order_by(Checkout.expected_return_date)
        .limit(10)
        .all()
    )
    upcoming_reservations = (
        Reservation.query.filter(
            Reservation.status == ReservationStatus.ACTIVE,
            Reservation.ends_at >= datetime.combine(date.today(), datetime.min.time()),
        )
        .order_by(Reservation.starts_at)
        .limit(10)
        .all()
    )
    maintenance_due = (
        MaintenanceSchedule.query.filter(MaintenanceSchedule.next_due_date <= date.today() + timedelta(days=30))
        .order_by(MaintenanceSchedule.next_due_date)
        .limit(10)
        .all()
    )
    pending_requests = (
        AssetRequest.query.filter_by(status=AssetRequestStatus.PENDING)
        .order_by(AssetRequest.created_at.desc())
        .limit(10)
        .all()
    )

    recent_activity = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(20).all()
    return render_template(
        "dashboard.html",
        total_assets=total_assets,
        status_counts=status_counts,
        warranty_alerts=warranty_alerts,
        overdue_checkouts=overdue_checkouts,
        upcoming_reservations=upcoming_reservations,
        maintenance_due=maintenance_due,
        pending_requests=pending_requests,
        recent_activity=recent_activity,
    )


@bp.route("/assets")
@login_required
def list_assets():
    query = Asset.query
    search = request.args.get("q", "").strip()
    department = request.args.get("department", "").strip()
    status = request.args.get("status", "").strip()
    category = request.args.get("category", "").strip()
    warranty = request.args.get("warranty", "").strip()

    if current_user.role == "viewer":
        query = query.filter((Asset.assigned_user_id == current_user.id) | (Asset.status != AssetStatus.RETIRED))
    if search:
        wildcard = f"%{search}%"
        query = query.outerjoin(User, Asset.assigned_user_id == User.id).filter(
            or_(
                Asset.asset_id.ilike(wildcard),
                Asset.description.ilike(wildcard),
                Asset.manufacturer.ilike(wildcard),
                Asset.model_number.ilike(wildcard),
                Asset.serial_number.ilike(wildcard),
                User.first_name.ilike(wildcard),
                User.last_name.ilike(wildcard),
            )
        )
    if department:
        query = query.filter_by(department=department)
    if status:
        query = query.filter_by(status=status)
    if category:
        query = query.filter_by(category=category)
    if warranty == "expiring":
        query = query.filter(Asset.warranty_expiration_date <= date.today() + timedelta(days=60))
    elif warranty == "expired":
        query = query.filter(Asset.warranty_expiration_date < date.today())

    assets = query.order_by(Asset.updated_at.desc()).all()
    return render_template(
        "assets.html",
        assets=assets,
        departments=DepartmentPrefix.query.filter_by(is_active=True).order_by(DepartmentPrefix.name).all(),
        categories=Category.query.filter_by(is_active=True).order_by(Category.name).all(),
        statuses=StatusValue.query.filter_by(is_active=True).order_by(StatusValue.name).all(),
        filters=request.args,
    )


@bp.route("/assets/new", methods=("GET", "POST"))
@asset_manager_required
def create_asset():
    if request.method == "POST":
        department_code = request.form["department_code"]
        department = DepartmentPrefix.query.filter_by(code=department_code).first_or_404()
        asset = Asset(
            asset_id=generate_asset_id(department_code),
            barcode_value="",
            description=request.form["description"].strip(),
            category=request.form.get("category"),
            manufacturer=request.form.get("manufacturer"),
            model_number=request.form.get("model_number"),
            serial_number=request.form.get("serial_number"),
            department=department.name,
            ministry=request.form.get("ministry"),
            purchase_date=parse_date(request.form.get("purchase_date")),
            purchase_cost=request.form.get("purchase_cost") or None,
            vendor=request.form.get("vendor"),
            status=request.form.get("status") or AssetStatus.AVAILABLE,
            assigned_user_id=request.form.get("assigned_user_id") or None,
            current_location=request.form.get("current_location"),
            condition=request.form.get("condition") or "Good",
            warranty_provider=request.form.get("warranty_provider"),
            warranty_expiration_date=parse_date(request.form.get("warranty_expiration_date")),
            warranty_notes=request.form.get("warranty_notes"),
            notes=request.form.get("notes"),
            created_by_id=current_user.id,
            updated_by_id=current_user.id,
        )
        asset.barcode_value = asset.asset_id
        db.session.add(asset)
        db.session.commit()
        save_asset_uploads(asset)
        log_activity(current_user.id, "Asset Creation", "Asset", asset.asset_id, asset.description)
        flash(f"Asset {asset.asset_id} created.", "success")
        return redirect(url_for("assets.detail", asset_id=asset.asset_id))

    return render_asset_form("Add Asset", Asset())


@bp.route("/assets/<asset_id>")
@login_required
def detail(asset_id):
    asset = Asset.query.filter_by(asset_id=asset_id).first_or_404()
    if current_user.role == "viewer" and asset.assigned_user_id not in (None, current_user.id):
        flash("You do not have permission to view that asset.", "danger")
        return redirect(url_for("assets.dashboard"))
    ensure_barcode(asset)
    from asset_manager.database.models import MaintenanceSchedule

    return render_template(
        "asset_detail.html",
        asset=asset,
        users=active_users(),
        maintenance_schedule=MaintenanceSchedule.query.filter_by(asset_id=asset.id).first(),
    )


@bp.route("/assets/<asset_id>/edit", methods=("GET", "POST"))
@asset_manager_required
def edit_asset(asset_id):
    asset = Asset.query.filter_by(asset_id=asset_id).first_or_404()
    if request.method == "POST":
        asset.description = request.form["description"].strip()
        asset.category = request.form.get("category")
        asset.manufacturer = request.form.get("manufacturer")
        asset.model_number = request.form.get("model_number")
        asset.serial_number = request.form.get("serial_number")
        asset.ministry = request.form.get("ministry")
        asset.purchase_date = parse_date(request.form.get("purchase_date"))
        asset.purchase_cost = request.form.get("purchase_cost") or None
        asset.vendor = request.form.get("vendor")
        asset.status = request.form.get("status") or AssetStatus.AVAILABLE
        asset.assigned_user_id = request.form.get("assigned_user_id") or None
        asset.current_location = request.form.get("current_location")
        asset.condition = request.form.get("condition") or "Good"
        asset.warranty_provider = request.form.get("warranty_provider")
        asset.warranty_expiration_date = parse_date(request.form.get("warranty_expiration_date"))
        asset.warranty_notes = request.form.get("warranty_notes")
        asset.notes = request.form.get("notes")
        asset.updated_by_id = current_user.id
        save_asset_uploads(asset)
        db.session.commit()
        log_activity(current_user.id, "Asset Modification", "Asset", asset.asset_id, "Updated asset")
        flash("Asset updated.", "success")
        return redirect(url_for("assets.detail", asset_id=asset.asset_id))
    return render_asset_form("Edit Asset", asset)


@bp.route("/assets/<asset_id>/barcode")
@login_required
def barcode(asset_id):
    asset = Asset.query.filter_by(asset_id=asset_id).first_or_404()
    path = ensure_barcode(asset)
    if path is None:
        flash("Barcode dependency is not installed.", "warning")
        return redirect(url_for("assets.detail", asset_id=asset.asset_id))
    return send_file(path, mimetype="image/png", as_attachment=request.args.get("download") == "1")


def render_asset_form(title, asset):
    return render_template(
        "asset_form.html",
        title=title,
        asset=asset,
        departments=DepartmentPrefix.query.filter_by(is_active=True).order_by(DepartmentPrefix.name).all(),
        categories=Category.query.filter_by(is_active=True).order_by(Category.name).all(),
        statuses=StatusValue.query.filter_by(is_active=True).order_by(StatusValue.name).all(),
        users=active_users(),
        today=date.today().isoformat(),
    )


def active_users():
    return User.query.filter_by(is_active_account=True).order_by(User.last_name, User.first_name).all()


def parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def save_asset_uploads(asset):
    photo_files = request.files.getlist("photos")
    for file in photo_files:
        if not file or not file.filename:
            continue
        original, stored, destination = save_upload(file, f"assets/{asset.asset_id}/photos", PHOTO_EXTENSIONS)
        thumbnail = make_thumbnail(Path(destination))
        db.session.add(
            AssetPhoto(
                asset=asset,
                original_filename=original,
                stored_filename=f"assets/{asset.asset_id}/photos/{stored}",
                thumbnail_filename=f"assets/{asset.asset_id}/photos/{thumbnail}",
                is_primary=asset.primary_photo is None,
                uploaded_by_id=current_user.id,
            )
        )

    document_files = request.files.getlist("documents")
    for file in document_files:
        if not file or not file.filename:
            continue
        original, stored, _ = save_upload(file, f"assets/{asset.asset_id}/documents", DOCUMENT_EXTENSIONS)
        db.session.add(
            AssetDocument(
                asset=asset,
                original_filename=original,
                stored_filename=f"assets/{asset.asset_id}/documents/{stored}",
                uploaded_by_id=current_user.id,
            )
        )
