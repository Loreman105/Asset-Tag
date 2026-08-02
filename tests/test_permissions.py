from datetime import date

import pytest

from asset_manager.app import create_app
from asset_manager.database.models import Asset, MaintenanceSchedule, Role, User
from asset_manager.extensions import db


@pytest.fixture()
def app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def create_user(email, role):
    user = User(
        first_name="Test",
        last_name="User",
        email=email,
        password_hash="hashed",
        role=role,
    )
    db.session.add(user)
    db.session.commit()
    return user


def test_viewer_can_access_requests_and_own_assets(client):
    viewer = create_user("viewer@example.com", Role.VIEWER)
    with client.session_transaction() as session:
        session["_user_id"] = str(viewer.id)
        session["_fresh"] = True

    response = client.get("/requests/")
    assert response.status_code == 200

    response = client.get("/assets")
    assert response.status_code == 200


def test_moderator_cannot_access_admin_only_routes(client):
    moderator = create_user("moderator@example.com", Role.MODERATOR)
    with client.session_transaction() as session:
        session["_user_id"] = str(moderator.id)
        session["_fresh"] = True

    response = client.get("/reports/")
    assert response.status_code == 302

    response = client.get("/users/")
    assert response.status_code == 302

    response = client.get("/settings/")
    assert response.status_code == 302

    response = client.get("/dashboard")
    assert b">Admin<" not in response.data


def test_moderator_can_schedule_maintenance(client):
    moderator = create_user("scheduler@example.com", Role.MODERATOR)
    asset = Asset(
        asset_id="AV00000001",
        barcode_value="AV00000001",
        description="Camera",
        department="AV",
    )
    db.session.add(asset)
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(moderator.id)
        session["_fresh"] = True

    response = client.post(
        "/maintenance/schedule",
        data={
            "asset_id": asset.id,
            "next_due_date": "2026-10-01",
            "service_type": "Inspection",
            "frequency_days": "90",
            "notes": "Annual check",
        },
    )

    assert response.status_code == 302
    schedule = MaintenanceSchedule.query.filter_by(asset_id=asset.id).one()
    assert schedule.next_due_date == date(2026, 10, 1)
    assert schedule.frequency_days == 90


def test_viewer_dashboard_shows_only_assigned_device_details(client):
    viewer = create_user("viewer-dashboard@example.com", Role.VIEWER)
    assigned_asset = Asset(
        asset_id="AV00000001",
        barcode_value="AV00000001",
        description="Assigned Camera",
        department="AV",
        assigned_user_id=viewer.id,
        warranty_provider="Acme",
        warranty_expiration_date=date(2027, 1, 1),
    )
    other_asset = Asset(
        asset_id="AV00000002",
        barcode_value="AV00000002",
        description="Someone Else's Camera",
        department="AV",
    )
    db.session.add_all([assigned_asset, other_asset])
    db.session.commit()
    db.session.add(
        MaintenanceSchedule(
            asset_id=assigned_asset.id,
            next_due_date=date(2026, 10, 1),
            service_type="Inspection",
        )
    )
    db.session.commit()
    with client.session_transaction() as session:
        session["_user_id"] = str(viewer.id)
        session["_fresh"] = True

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert b"Assigned Camera" in response.data
    assert b"Someone Else's Camera" not in response.data
    assert b"2026-10-01" in response.data
    assert b"Acme" in response.data
