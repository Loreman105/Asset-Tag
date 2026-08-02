"""Camera barcode scanner routes."""

from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from asset_manager.database.models import Asset
from asset_manager.utils import asset_code_from_scan

bp = Blueprint("scanner", __name__, url_prefix="/scanner")


@bp.route("/", methods=("GET", "POST"))
@login_required
def index():
    if request.method == "POST":
        scanned_value = request.form.get("asset_code", "").strip()
        code = asset_code_from_scan(scanned_value)
        asset = Asset.query.filter((Asset.asset_id == code) | (Asset.barcode_value == code)).first()
        if asset:
            # A QR label is intentionally a direct asset link. It should always
            # open the full device record, regardless of the selected action.
            if urlparse(scanned_value).scheme:
                return redirect(url_for("assets.detail", asset_id=asset.asset_id))
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
