"""Report routes with PDF, CSV, and Excel exports."""

from flask import Blueprint, Response, render_template, request, send_file
from flask_login import login_required

from asset_manager.database.models import Asset, AuditLog, Checkout, MaintenanceRecord, Role
from asset_manager.routes.auth import roles_required
from asset_manager.utils import csv_response, pdf_response, xlsx_response

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/")
@login_required
@roles_required("administrator", "moderator")
def index():
    return render_template("reports.html")


@bp.route("/audit-log")
@login_required
@roles_required(Role.ADMIN)
def audit_log():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(500).all()
    return render_template("audit_log.html", logs=logs)


@bp.route("/<report_name>")
@login_required
@roles_required("administrator", "moderator")
def export(report_name):
    rows, headers, title = build_report(report_name)
    file_type = request.args.get("format", "csv")

    if file_type == "pdf":
        return send_file(pdf_response(title, rows, headers), download_name=f"{report_name}.pdf", as_attachment=True)
    if file_type == "xlsx":
        return send_file(
            xlsx_response(rows, headers),
            download_name=f"{report_name}.xlsx",
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return Response(
        csv_response(rows, headers),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={report_name}.csv"},
    )


def build_report(report_name):
    if report_name == "inventory":
        headers = ["Asset ID", "Description", "Department", "Category", "Status", "Location", "Value"]
        rows = [
            (
                asset.asset_id,
                asset.description,
                asset.department,
                asset.category,
                asset.status,
                asset.current_location,
                asset.purchase_cost,
            )
            for asset in Asset.query.order_by(Asset.asset_id).all()
        ]
        return rows, headers, "Inventory Report"

    if report_name == "checkouts":
        headers = ["Asset ID", "Description", "Checked Out To", "Checked Out", "Expected Return", "Condition"]
        rows = [
            (
                checkout.asset.asset_id,
                checkout.asset.description,
                checkout.user_receiving.full_name,
                checkout.checked_out_at,
                checkout.expected_return_date,
                checkout.checkout_condition,
            )
            for checkout in Checkout.query.filter_by(returned_at=None).all()
        ]
        return rows, headers, "Current Checkout Report"

    if report_name == "maintenance":
        headers = ["Asset ID", "Date", "Type", "Description", "Cost", "Performed By"]
        rows = [
            (
                record.asset.asset_id,
                record.service_date,
                record.maintenance_type,
                record.description,
                record.cost,
                record.performed_by.full_name,
            )
            for record in MaintenanceRecord.query.order_by(MaintenanceRecord.service_date.desc()).all()
        ]
        return rows, headers, "Maintenance Report"

    if report_name == "warranty":
        headers = ["Asset ID", "Description", "Provider", "Expiration"]
        rows = [
            (asset.asset_id, asset.description, asset.warranty_provider, asset.warranty_expiration_date)
            for asset in Asset.query.filter(Asset.warranty_expiration_date.isnot(None)).order_by(Asset.warranty_expiration_date).all()
        ]
        return rows, headers, "Warranty Report"

    if report_name == "value":
        headers = ["Department", "Total Value"]
        totals = {}
        for asset in Asset.query.all():
            totals[asset.department] = totals.get(asset.department, 0) + float(asset.purchase_cost or 0)
        return sorted(totals.items()), headers, "Asset Value By Department"

    return [], ["No data"], "Unknown Report"
