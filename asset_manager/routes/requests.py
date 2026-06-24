"""Asset request and approval routes."""

from datetime import date, datetime, time

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from asset_manager.database.db import log_activity
from asset_manager.database.models import (
    Asset,
    AssetRequest,
    AssetRequestStatus,
    AssetStatus,
    Reservation,
    ReservationStatus,
    User,
    utc_now,
)
from asset_manager.extensions import db
from asset_manager.routes.auth import asset_manager_required
from asset_manager.routes.reservations import reservation_conflicts

bp = Blueprint("asset_requests", __name__, url_prefix="/requests")


def parse_datetime(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


def requestable_assets():
    return (
        Asset.query.filter(Asset.status.notin_([AssetStatus.RETIRED, AssetStatus.LOST, AssetStatus.DAMAGED]))
        .order_by(Asset.department, Asset.description)
        .all()
    )


@bp.route("/", methods=("GET", "POST"))
@login_required
def index():
    assets = requestable_assets()
    if request.method == "POST":
        starts_at = parse_datetime(request.form.get("starts_at"))
        ends_at = parse_datetime(request.form.get("ends_at"))
        if not starts_at or not ends_at or starts_at >= ends_at:
            flash("Choose a valid start and end time.", "danger")
            return redirect(url_for("asset_requests.index"))

        asset_id = request.form.get("asset_id") or None
        asset = db.session.get(Asset, int(asset_id)) if asset_id else None
        asset_request = AssetRequest(
            asset=asset,
            requested_by_id=current_user.id,
            event_name=request.form["event_name"].strip(),
            starts_at=starts_at,
            ends_at=ends_at,
            requested_asset_description=request.form.get("requested_asset_description"),
            notes=request.form.get("notes"),
        )
        db.session.add(asset_request)
        db.session.commit()
        log_activity(current_user.id, "Asset Request Created", "AssetRequest", asset_request.id, asset_request.event_name)
        flash("Request submitted.", "success")
        return redirect(url_for("asset_requests.index"))

    query = AssetRequest.query
    if not current_user.can_manage_assets():
        query = query.filter_by(requested_by_id=current_user.id)
    requests = query.order_by(AssetRequest.created_at.desc()).all()
    return render_template(
        "asset_requests.html",
        assets=assets,
        requests=requests,
        today=date.today().isoformat(),
        pending_count=AssetRequest.query.filter_by(status=AssetRequestStatus.PENDING).count(),
    )


@bp.post("/<int:request_id>/approve")
@asset_manager_required
def approve(request_id):
    asset_request = AssetRequest.query.get_or_404(request_id)
    if request.form.get("asset_id"):
        asset_request.asset = db.session.get(Asset, int(request.form["asset_id"]))
    asset = asset_request.asset
    if not asset:
        flash("Assign a specific asset before approving this request.", "danger")
        return redirect(url_for("asset_requests.index"))
    if reservation_conflicts(asset.id, asset_request.starts_at, asset_request.ends_at):
        flash(f"{asset.asset_id} is already reserved during that time.", "warning")
        return redirect(url_for("asset_requests.index"))

    reservation = Reservation(
        asset=asset,
        reserved_for_id=asset_request.requested_by_id,
        reserved_by_id=current_user.id,
        event_name=asset_request.event_name,
        starts_at=asset_request.starts_at,
        ends_at=asset_request.ends_at,
        status=ReservationStatus.ACTIVE,
        notes=asset_request.notes,
    )
    asset_request.status = AssetRequestStatus.APPROVED
    asset_request.reviewed_by_id = current_user.id
    asset_request.reviewed_at = utc_now()
    asset_request.review_notes = request.form.get("review_notes")
    asset_request.reservation = reservation
    db.session.add(reservation)
    db.session.commit()
    log_activity(current_user.id, "Asset Request Approved", "AssetRequest", asset_request.id, asset_request.event_name)
    flash("Request approved and reservation created.", "success")
    return redirect(url_for("asset_requests.index"))


@bp.post("/<int:request_id>/deny")
@asset_manager_required
def deny(request_id):
    asset_request = AssetRequest.query.get_or_404(request_id)
    asset_request.status = AssetRequestStatus.DENIED
    asset_request.reviewed_by_id = current_user.id
    asset_request.reviewed_at = utc_now()
    asset_request.review_notes = request.form.get("review_notes")
    db.session.commit()
    log_activity(current_user.id, "Asset Request Denied", "AssetRequest", asset_request.id, asset_request.event_name)
    flash("Request denied.", "success")
    return redirect(url_for("asset_requests.index"))
