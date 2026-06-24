"""Administrative import, export, and label-printing tools."""

import csv
from datetime import datetime
from io import BytesIO, StringIO

from flask import Blueprint, Response, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from asset_manager.database.db import log_activity
from asset_manager.database.models import Asset, AssetStatus, Category, DepartmentPrefix, Setting
from asset_manager.extensions import db
from asset_manager.routes.assets import parse_date
from asset_manager.routes.auth import roles_required
from asset_manager.utils import csv_response, ensure_barcode, generate_asset_id

bp = Blueprint("admin_tools", __name__, url_prefix="/admin-tools")

IMPORT_FIELDS = [
    "asset_id",
    "description",
    "department",
    "category",
    "manufacturer",
    "model_number",
    "serial_number",
    "current_location",
    "condition",
    "status",
    "purchase_date",
    "purchase_cost",
    "vendor",
    "warranty_provider",
    "warranty_expiration_date",
    "notes",
]


@bp.route("/", methods=("GET", "POST"))
@roles_required("administrator", "moderator")
def index():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "labels":
            asset_ids = request.form.getlist("asset_ids")
            assets = Asset.query.filter(Asset.id.in_(asset_ids)).order_by(Asset.asset_id).all()
            if not assets:
                flash("Select at least one asset to print labels.", "warning")
                return redirect(url_for("admin_tools.index"))
            return send_file(label_pdf(assets), download_name="asset-labels.pdf", as_attachment=True)
        if action == "import":
            return import_assets()

    assets = Asset.query.order_by(Asset.asset_id).all()
    return render_template("admin_tools.html", assets=assets, fields=IMPORT_FIELDS)


@bp.get("/export")
@roles_required("administrator", "moderator")
def export_assets():
    headers = IMPORT_FIELDS
    rows = []
    for asset in Asset.query.order_by(Asset.asset_id).all():
        rows.append(tuple(getattr(asset, field) for field in headers))
    return Response(
        csv_response(rows, headers),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=assets-export.csv"},
    )


@bp.get("/template")
@roles_required("administrator", "moderator")
def template():
    return Response(
        csv_response([], IMPORT_FIELDS),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=assets-import-template.csv"},
    )


def import_assets():
    upload = request.files.get("csv_file")
    if not upload or not upload.filename:
        flash("Choose a CSV file to import.", "danger")
        return redirect(url_for("admin_tools.index"))

    stream = StringIO(upload.stream.read().decode("utf-8-sig"))
    reader = csv.DictReader(stream)
    created = 0
    updated = 0
    skipped = 0

    for row in reader:
        description = (row.get("description") or "").strip()
        department = (row.get("department") or "").strip()
        if not description or not department:
            skipped += 1
            continue

        asset_code = (row.get("asset_id") or "").strip()
        asset = Asset.query.filter_by(asset_id=asset_code).first() if asset_code else None
        if not asset:
            prefix = DepartmentPrefix.query.filter_by(name=department, is_active=True).first()
            if not prefix:
                skipped += 1
                continue
            asset = Asset(
                asset_id=asset_code or generate_asset_id(prefix.code),
                barcode_value=asset_code or "",
                description=description,
                department=department,
                created_by_id=current_user.id,
                updated_by_id=current_user.id,
            )
            if not asset.barcode_value:
                asset.barcode_value = asset.asset_id
            db.session.add(asset)
            created += 1
        else:
            updated += 1

        apply_asset_row(asset, row)
        asset.updated_by_id = current_user.id

    db.session.commit()
    log_activity(current_user.id, "Asset Import", "Asset", "CSV", f"{created} created, {updated} updated, {skipped} skipped")
    flash(f"Import complete: {created} created, {updated} updated, {skipped} skipped.", "success")
    return redirect(url_for("admin_tools.index"))


def apply_asset_row(asset, row):
    text_fields = [
        "description",
        "department",
        "category",
        "manufacturer",
        "model_number",
        "serial_number",
        "current_location",
        "condition",
        "status",
        "vendor",
        "warranty_provider",
        "notes",
    ]
    for field in text_fields:
        value = row.get(field)
        if value is not None:
            setattr(asset, field, value.strip() or None)
    asset.status = asset.status or AssetStatus.AVAILABLE
    asset.condition = asset.condition or "Good"
    asset.purchase_date = parse_date(row.get("purchase_date"))
    asset.warranty_expiration_date = parse_date(row.get("warranty_expiration_date"))
    asset.purchase_cost = row.get("purchase_cost") or None


def label_pdf(assets):
    output = BytesIO()
    page = canvas.Canvas(output, pagesize=letter)
    width, height = letter
    church_name = (Setting.query.filter_by(key="church_name").first().value or "Church Assets")
    label_w = 2.625 * 72
    label_h = 1.0 * 72
    margin_x = 0.1875 * 72
    margin_y = 0.5 * 72
    gap_x = 0.125 * 72
    columns = 3
    rows = 10

    for index, asset in enumerate(assets):
        slot = index % (columns * rows)
        if index and slot == 0:
            page.showPage()
        col = slot % columns
        row = slot // columns
        x = margin_x + col * (label_w + gap_x)
        y = height - margin_y - (row + 1) * label_h
        draw_label(page, asset, church_name, x, y, label_w, label_h)

    page.save()
    output.seek(0)
    return output


def draw_label(page, asset, church_name, x, y, label_w, label_h):
    barcode = ensure_barcode(asset)
    page.setFont("Helvetica-Bold", 7)
    page.drawString(x + 6, y + label_h - 12, church_name[:34])
    page.setFont("Helvetica", 6)
    page.drawString(x + 6, y + label_h - 22, asset.description[:42])
    if barcode:
        page.drawImage(str(barcode), x + 6, y + 14, width=label_w - 12, height=28, preserveAspectRatio=True)
    page.setFont("Helvetica-Bold", 9)
    page.drawCentredString(x + label_w / 2, y + 5, asset.asset_id)
