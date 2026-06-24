"""Camera barcode scanner routes."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from asset_manager.database.models import Asset

bp = Blueprint("scanner", __name__, url_prefix="/scanner")


@bp.route("/", methods=("GET", "POST"))
@login_required
def index():
    if request.method == "POST":
        code = request.form.get("asset_code", "").strip()
        asset = Asset.query.filter((Asset.asset_id == code) | (Asset.barcode_value == code)).first()
        if asset:
            action = request.form.get("action", "detail")
            if action == "checkout":
                return redirect(url_for("checkouts.create", asset_id=asset.asset_id))
            if action == "checkin":
                return redirect(url_for("checkouts.return_asset", asset_id=asset.asset_id))
            if action == "maintenance":
                return redirect(url_for("maintenance.create", asset_id=asset.asset_id))
            return redirect(url_for("assets.detail", asset_id=asset.asset_id))
        flash(f"Asset {code or 'number'} was not found.", "danger")
    return render_template("scanner.html")
