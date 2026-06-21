"""Utility helpers for asset IDs, uploads, reports, and barcodes."""

import csv
import uuid
from datetime import date
from io import BytesIO, StringIO
from pathlib import Path

from flask import current_app
from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from asset_manager.database.models import Asset, DepartmentPrefix
from asset_manager.extensions import db

PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
DOCUMENT_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "csv", "txt", "jpg", "jpeg", "png", "webp"}
CONDITION_ORDER = {"Excellent": 5, "Good": 4, "Fair": 3, "Poor": 2, "Damaged": 1}


def generate_asset_id(department_code):
    prefix = DepartmentPrefix.query.filter_by(code=department_code, is_active=True).first()
    if prefix is None:
        raise ValueError("Invalid department prefix.")

    year = f"{date.today().year % 100:02d}"
    existing_ids = [
        asset.asset_id
        for asset in Asset.query.filter(Asset.asset_id.like(f"{department_code}%")).all()
        if len(asset.asset_id) == 10 and asset.asset_id.isdigit()
    ]
    sequence = 1
    version = 0
    if existing_ids:
        version = max(int(asset_id[8:10]) for asset_id in existing_ids)
        sequence = max(int(asset_id[4:8]) for asset_id in existing_ids if int(asset_id[8:10]) == version) + 1
        if sequence > 9999:
            sequence = 1
            version += 1
    return f"{department_code}{year}{sequence:04d}{version:02d}"


def allowed_file(filename, extensions):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in extensions


def save_upload(file: FileStorage, subfolder, allowed_extensions):
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename, allowed_extensions):
        raise ValueError("Unsupported file type.")

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]) / subfolder
    upload_root.mkdir(parents=True, exist_ok=True)
    original = secure_filename(file.filename)
    suffix = original.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{suffix}"
    destination = upload_root / stored_name
    file.save(destination)
    return original, stored_name, destination


def make_thumbnail(image_path):
    thumb_name = f"{image_path.stem}_thumb{image_path.suffix}"
    thumb_path = image_path.with_name(thumb_name)
    with Image.open(image_path) as image:
        image.thumbnail((360, 360))
        image.save(thumb_path)
    return thumb_name


def barcode_path(asset):
    return Path(current_app.config["BARCODE_FOLDER"]) / f"{asset.asset_id}.png"


def ensure_barcode(asset):
    path = barcode_path(asset)
    if path.exists():
        return path
    try:
        import barcode
        from barcode.writer import ImageWriter
    except ImportError:
        return None

    code128 = barcode.get("code128", asset.asset_id, writer=ImageWriter())
    code128.save(str(path.with_suffix("")), {"write_text": True, "module_height": 11, "font_size": 8})
    return path


def csv_response(rows, headers):
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue()


def xlsx_response(rows, headers):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(list(row))
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def pdf_response(title, rows, headers):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    output = BytesIO()
    page = canvas.Canvas(output, pagesize=letter)
    width, height = letter
    y = height - 48
    page.setFont("Helvetica-Bold", 14)
    page.drawString(40, y, title)
    y -= 28
    page.setFont("Helvetica-Bold", 8)
    page.drawString(40, y, " | ".join(headers))
    y -= 14
    page.setFont("Helvetica", 8)
    for row in rows:
        if y < 48:
            page.showPage()
            y = height - 48
            page.setFont("Helvetica", 8)
        page.drawString(40, y, " | ".join("" if value is None else str(value) for value in row)[:130])
        y -= 12
    page.save()
    output.seek(0)
    return output


def condition_worsened(checkout_condition, return_condition):
    return CONDITION_ORDER.get(return_condition, 0) < CONDITION_ORDER.get(checkout_condition, 0)


def commit_and_log(log_func, user_id, action, object_type, object_id, details=None):
    db.session.commit()
    log_func(user_id, action, object_type, object_id, details)
