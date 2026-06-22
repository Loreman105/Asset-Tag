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


def find_asset(asset_code):
    code = asset_code.strip()
    return Asset.query.filter((Asset.asset_id == code) | (Asset.barcode_value == code)).first()


@bp.route("/", methods=("GET", "POST"))
@asset_manager_required
def quick():
    users = User.query.filter_by(is_active_account=True).order_by(User.last_name, User.first_name).all()
    mode = request.form.get("mode", "checkout")
    asset_code = request.form.get("asset_code", "").strip()

    if request.method == "POST":
        asset = find_asset(asset_code)
        if not asset:
            flash(f"Asset {asset_code or 'number'} was not found.", "danger")
            return render_template("quick_checkout.html", users=users, mode=mode, asset_code=asset_code)

        if mode == "checkin":
            checkout = (
                Checkout.query.filter_by(asset_id=asset.id, returned_at=None)
                .order_by(Checkout.checked_out_at.desc())
                .first()
            )
            if not checkout:
                flash(f"Asset {asset.asset_id} is not currently checked out.", "warning")
                return render_template("quick_checkout.html", users=users, mode=mode, asset_code=asset_code)

            checkout.returned_at = utc_now()
            checkout.returned_by_id = current_user.id
            checkout.return_condition = asset.condition
            checkout.return_notes = "Quick check-in"
            checkout.condition_worsened = False
            asset.status = AssetStatus.AVAILABLE
            asset.assigned_user_id = None
            asset.updated_by_id = current_user.id
            db.session.commit()
            log_activity(current_user.id, "Asset Return", "Asset", asset.asset_id, "Quick check-in")
            flash(f"Asset {asset.asset_id} checked in.", "success")
            return redirect(url_for("checkouts.quick"))

        if asset.status == AssetStatus.CHECKED_OUT:
            assigned_to = asset.assigned_user.full_name if asset.assigned_user else "another user"
            flash(f"Asset {asset.asset_id} is already checked out to {assigned_to}.", "warning")
            return render_template("quick_checkout.html", users=users, mode=mode, asset_code=asset_code)

        user = db.session.get(User, int(request.form["user_receiving_id"]))
        if not user or not user.is_active:
            flash("Select an active user to receive the asset.", "danger")
            return render_template("quick_checkout.html", users=users, mode=mode, asset_code=asset_code)

        checkout = Checkout(
            asset=asset,
            user_receiving_id=user.id,
            checked_out_by_id=current_user.id,
            checkout_condition=asset.condition,
            checkout_notes="Quick checkout",
        )
        asset.status = AssetStatus.CHECKED_OUT
        asset.assigned_user_id = user.id
        asset.updated_by_id = current_user.id
        db.session.add(checkout)
        db.session.commit()
        log_activity(current_user.id, "Asset Checkout", "Asset", asset.asset_id, f"Quick checkout to {user.full_name}")
        flash(f"Asset {asset.asset_id} checked out to {user.full_name}.", "success")
        return redirect(url_for("checkouts.quick"))

    return render_template("quick_checkout.html", users=users, mode=mode, asset_code=asset_code)


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
