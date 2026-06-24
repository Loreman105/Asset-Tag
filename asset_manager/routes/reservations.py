"""Reservation, overdue reminder, and inventory audit routes."""

from datetime import date, datetime, time
import smtplib
from email.message import EmailMessage

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.cli import with_appcontext
from flask_login import current_user, login_required
from sqlalchemy import and_

from asset_manager.database.db import log_activity
from asset_manager.database.models import (
    Asset,
    AssetStatus,
    AuditSessionStatus,
    Checkout,
    DepartmentPrefix,
    InventoryAuditItem,
    InventoryAuditSession,
    OverdueReminder,
    Reservation,
    ReservationStatus,
    User,
    utc_now,
)
from asset_manager.extensions import db
from asset_manager.routes.assets import parse_date
from asset_manager.routes.auth import asset_manager_required, roles_required

bp = Blueprint("reservations", __name__, url_prefix="/reservations")


def parse_datetime(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M")


def reservation_conflicts(asset_id, starts_at, ends_at, excluded_id=None):
    query = Reservation.query.filter(
        Reservation.asset_id == asset_id,
        Reservation.status == ReservationStatus.ACTIVE,
        Reservation.starts_at < ends_at,
        Reservation.ends_at > starts_at,
    )
    if excluded_id:
        query = query.filter(Reservation.id != excluded_id)
    return query.order_by(Reservation.starts_at).all()


def active_reservable_assets():
    return (
        Asset.query.filter(Asset.status.notin_([AssetStatus.RETIRED, AssetStatus.LOST, AssetStatus.DAMAGED]))
        .order_by(Asset.department, Asset.description)
        .all()
    )


@bp.route("/", methods=("GET", "POST"))
@asset_manager_required
def index():
    users = User.query.filter_by(is_active_account=True).order_by(User.last_name, User.first_name).all()
    assets = active_reservable_assets()
    if request.method == "POST":
        asset = db.session.get(Asset, int(request.form["asset_id"]))
        reserved_for = db.session.get(User, int(request.form["reserved_for_id"]))
        starts_at = parse_datetime(request.form.get("starts_at"))
        ends_at = parse_datetime(request.form.get("ends_at"))
        if not asset or not reserved_for or not starts_at or not ends_at or starts_at >= ends_at:
            flash("Choose an asset, user, and valid event start/end time.", "danger")
            return redirect(url_for("reservations.index"))
        conflicts = reservation_conflicts(asset.id, starts_at, ends_at)
        if conflicts:
            flash(f"{asset.asset_id} is already reserved during that time.", "warning")
            return redirect(url_for("reservations.index"))

        reservation = Reservation(
            asset=asset,
            reserved_for_id=reserved_for.id,
            reserved_by_id=current_user.id,
            event_name=request.form["event_name"].strip(),
            starts_at=starts_at,
            ends_at=ends_at,
            notes=request.form.get("notes"),
        )
        db.session.add(reservation)
        db.session.commit()
        log_activity(
            current_user.id,
            "Asset Reservation",
            "Asset",
            asset.asset_id,
            f"Reserved for {reservation.event_name}",
        )
        flash(f"{asset.asset_id} reserved for {reservation.event_name}.", "success")
        return redirect(url_for("reservations.index"))

    upcoming = (
        Reservation.query.filter(
            Reservation.status == ReservationStatus.ACTIVE,
            Reservation.ends_at >= datetime.combine(date.today(), time.min),
        )
        .order_by(Reservation.starts_at)
        .all()
    )
    overdue_checkouts = overdue_checkout_query().all()
    return render_template(
        "reservations.html",
        assets=assets,
        users=users,
        upcoming=upcoming,
        overdue_checkouts=overdue_checkouts,
        today=date.today().isoformat(),
    )


@bp.post("/<int:reservation_id>/cancel")
@asset_manager_required
def cancel(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    reservation.status = ReservationStatus.CANCELLED
    db.session.commit()
    log_activity(current_user.id, "Reservation Cancelled", "Asset", reservation.asset.asset_id, reservation.event_name)
    flash("Reservation cancelled.", "success")
    return redirect(url_for("reservations.index"))


@bp.post("/<int:reservation_id>/checkout")
@asset_manager_required
def checkout_reserved(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    asset = reservation.asset
    if asset.status == AssetStatus.CHECKED_OUT:
        flash(f"{asset.asset_id} is already checked out.", "warning")
        return redirect(url_for("reservations.index"))
    checkout = Checkout(
        asset=asset,
        user_receiving_id=reservation.reserved_for_id,
        checked_out_by_id=current_user.id,
        expected_return_date=reservation.ends_at.date(),
        checkout_condition=asset.condition,
        checkout_notes=f"Reserved checkout for {reservation.event_name}",
    )
    asset.status = AssetStatus.CHECKED_OUT
    asset.assigned_user_id = reservation.reserved_for_id
    asset.updated_by_id = current_user.id
    reservation.status = ReservationStatus.FULFILLED
    reservation.fulfilled_checkout = checkout
    db.session.add(checkout)
    db.session.commit()
    log_activity(current_user.id, "Reserved Checkout", "Asset", asset.asset_id, reservation.event_name)
    flash(f"{asset.asset_id} checked out for {reservation.event_name}.", "success")
    return redirect(url_for("reservations.index"))


@bp.route("/overdue")
@login_required
@roles_required("administrator", "moderator")
def overdue():
    overdue_checkouts = overdue_checkout_query().all()
    recent_reminders = OverdueReminder.query.order_by(OverdueReminder.sent_at.desc()).limit(50).all()
    return render_template("overdue.html", overdue_checkouts=overdue_checkouts, recent_reminders=recent_reminders)


@bp.post("/overdue/send-reminders")
@asset_manager_required
def send_reminders():
    sent, skipped = send_overdue_reminders()
    flash(f"Processed overdue reminders: {sent} sent/logged, {skipped} skipped.", "success")
    return redirect(url_for("reservations.overdue"))


@bp.route("/audit", methods=("GET", "POST"))
@asset_manager_required
def audits():
    departments = DepartmentPrefix.query.filter_by(is_active=True).order_by(DepartmentPrefix.name).all()
    if request.method == "POST":
        session = InventoryAuditSession(
            name=request.form["name"].strip(),
            department=request.form.get("department") or None,
            notes=request.form.get("notes"),
            started_by_id=current_user.id,
        )
        db.session.add(session)
        db.session.commit()
        log_activity(current_user.id, "Inventory Audit Started", "Audit", session.id, session.name)
        flash("Inventory audit started.", "success")
        return redirect(url_for("reservations.audit_session", session_id=session.id))

    sessions = InventoryAuditSession.query.order_by(InventoryAuditSession.started_at.desc()).all()
    return render_template("audit_sessions.html", sessions=sessions, departments=departments)


@bp.route("/audit/<int:session_id>", methods=("GET", "POST"))
@asset_manager_required
def audit_session(session_id):
    session = InventoryAuditSession.query.get_or_404(session_id)
    if request.method == "POST":
        asset_code = request.form["asset_code"].strip()
        asset = Asset.query.filter((Asset.asset_id == asset_code) | (Asset.barcode_value == asset_code)).first()
        if not asset:
            flash(f"Asset {asset_code} was not found.", "danger")
            return redirect(url_for("reservations.audit_session", session_id=session.id))
        if session.department and asset.department != session.department:
            flash(f"{asset.asset_id} belongs to {asset.department}, not {session.department}.", "warning")
        existing = InventoryAuditItem.query.filter_by(session_id=session.id, asset_id=asset.id).first()
        if existing:
            existing.scanned_at = utc_now()
            existing.scanned_by_id = current_user.id
            existing.condition = request.form.get("condition") or asset.condition
            existing.location = request.form.get("location") or asset.current_location
            existing.status = request.form.get("status") or asset.status
            existing.notes = request.form.get("notes")
        else:
            db.session.add(
                InventoryAuditItem(
                    session=session,
                    asset=asset,
                    scanned_by_id=current_user.id,
                    condition=request.form.get("condition") or asset.condition,
                    location=request.form.get("location") or asset.current_location,
                    status=request.form.get("status") or asset.status,
                    notes=request.form.get("notes"),
                )
            )
        db.session.commit()
        log_activity(current_user.id, "Asset Audited", "Asset", asset.asset_id, session.name)
        flash(f"{asset.asset_id} verified.", "success")
        return redirect(url_for("reservations.audit_session", session_id=session.id))

    expected_query = Asset.query.filter(Asset.status != AssetStatus.RETIRED)
    if session.department:
        expected_query = expected_query.filter_by(department=session.department)
    expected_assets = expected_query.order_by(Asset.asset_id).all()
    scanned_asset_ids = {item.asset_id for item in session.items}
    missing_assets = [asset for asset in expected_assets if asset.id not in scanned_asset_ids]
    return render_template(
        "audit_session.html",
        session=session,
        expected_assets=expected_assets,
        missing_assets=missing_assets,
    )


@bp.post("/audit/<int:session_id>/close")
@asset_manager_required
def close_audit(session_id):
    session = InventoryAuditSession.query.get_or_404(session_id)
    session.status = AuditSessionStatus.CLOSED
    session.closed_at = utc_now()
    db.session.commit()
    log_activity(current_user.id, "Inventory Audit Closed", "Audit", session.id, session.name)
    flash("Inventory audit closed.", "success")
    return redirect(url_for("reservations.audit_session", session_id=session.id))


def overdue_checkout_query():
    return Checkout.query.filter(
        Checkout.returned_at.is_(None),
        Checkout.expected_return_date.isnot(None),
        Checkout.expected_return_date < date.today(),
    ).order_by(Checkout.expected_return_date)


def send_overdue_reminders():
    sent = 0
    skipped = 0
    for checkout in overdue_checkout_query().all():
        already_sent_today = OverdueReminder.query.filter(
            OverdueReminder.checkout_id == checkout.id,
            OverdueReminder.sent_at >= datetime.combine(date.today(), time.min),
        ).first()
        if already_sent_today:
            skipped += 1
            continue
        reminder = build_overdue_reminder(checkout)
        db.session.add(reminder)
        try:
            deliver_email(reminder.sent_to, reminder.subject, reminder.body)
            reminder.delivery_status = "Sent"
        except RuntimeError as exc:
            reminder.delivery_status = "Logged"
            reminder.error_message = str(exc)
        except smtplib.SMTPException as exc:
            reminder.delivery_status = "Failed"
            reminder.error_message = str(exc)
        sent += 1
    db.session.commit()
    return sent, skipped


def build_overdue_reminder(checkout):
    subject = f"Overdue equipment return: {checkout.asset.asset_id}"
    body = (
        f"Hi {checkout.user_receiving.first_name},\n\n"
        f"{checkout.asset.asset_id} - {checkout.asset.description} was due back on "
        f"{checkout.expected_return_date}.\n\n"
        "Please return it or contact the asset team if it is still needed for ministry use.\n"
    )
    return OverdueReminder(checkout=checkout, sent_to=checkout.user_receiving.email, subject=subject, body=body)


def deliver_email(to_address, subject, body):
    host = current_app.config.get("MAIL_SERVER")
    if not host:
        raise RuntimeError("MAIL_SERVER is not configured; reminder was logged but not emailed.")

    message = EmailMessage()
    message["From"] = current_app.config.get("MAIL_DEFAULT_SENDER", "assets@church.local")
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    port = current_app.config.get("MAIL_PORT", 587)
    username = current_app.config.get("MAIL_USERNAME")
    password = current_app.config.get("MAIL_PASSWORD")
    use_tls = current_app.config.get("MAIL_USE_TLS", True)
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)


def register_cli(app):
    @app.cli.command("send-overdue-reminders")
    @with_appcontext
    def send_overdue_reminders_command():
        sent, skipped = send_overdue_reminders()
        print(f"Processed overdue reminders: {sent} sent/logged, {skipped} skipped.")
