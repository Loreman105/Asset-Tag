"""Checkout and check-in routes."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from asset_manager.database.db import log_activity
from asset_manager.database.models import Asset, AssetStatus, Checkout, User, utc_now
from asset_manager.extensions import db
from asset_manager.routes.assets import parse_date
from asset_manager.routes.auth import asset_manager_required
from asset_manager.utils import condition_worsened

bp = Blueprint("checkouts", __name__, url_prefix="/checkouts")


@bp.route("/new/<asset_id>", methods=("GET", "POST"))
@asset_manager_required
def create(asset_id):
    asset = Asset.query.filter_by(asset_id=asset_id).first_or_404()
    users = User.query.filter_by(is_active_account=True).order_by(User.last_name).all()
    if request.method == "POST":
        checkout = Checkout(
            asset=asset,
            user_receiving_id=request.form["user_receiving_id"],
            checked_out_by_id=current_user.id,
            expected_return_date=parse_date(request.form.get("expected_return_date")),
            checkout_condition=request.form["checkout_condition"],
            checkout_notes=request.form["checkout_notes"],
        )
        asset.status = AssetStatus.CHECKED_OUT
        asset.assigned_user_id = checkout.user_receiving_id
        asset.condition = checkout.checkout_condition
        asset.updated_by_id = current_user.id
        db.session.add(checkout)
        db.session.commit()
        log_activity(current_user.id, "Asset Checkout", "Asset", asset.asset_id, "Asset checked out")
        flash("Asset checked out.", "success")
        return redirect(url_for("assets.detail", asset_id=asset.asset_id))
    return render_template("checkout.html", asset=asset, users=users)


@bp.route("/return/<asset_id>", methods=("GET", "POST"))
@asset_manager_required
def return_asset(asset_id):
    asset = Asset.query.filter_by(asset_id=asset_id).first_or_404()
    checkout = (
        Checkout.query.filter_by(asset_id=asset.id, returned_at=None)
        .order_by(Checkout.checked_out_at.desc())
        .first_or_404()
    )
    if request.method == "POST":
        checkout.returned_at = utc_now()
        checkout.returned_by_id = current_user.id
        checkout.return_condition = request.form["return_condition"]
        checkout.return_notes = request.form["return_notes"]
        checkout.condition_worsened = condition_worsened(checkout.checkout_condition, checkout.return_condition)
        asset.status = AssetStatus.DAMAGED if checkout.return_condition == "Damaged" else AssetStatus.AVAILABLE
        asset.assigned_user_id = None
        asset.condition = checkout.return_condition
        asset.updated_by_id = current_user.id
        db.session.commit()
        details = "Condition worsened on return." if checkout.condition_worsened else "Asset returned."
        log_activity(current_user.id, "Asset Return", "Asset", asset.asset_id, details)
        flash(details, "warning" if checkout.condition_worsened else "success")
        return redirect(url_for("assets.detail", asset_id=asset.asset_id))
    return render_template("checkin.html", asset=asset, checkout=checkout)
