import pytest

from asset_manager.app import create_app
from asset_manager.database.models import Role, User
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
