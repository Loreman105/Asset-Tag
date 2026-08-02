from asset_manager.database.models import Role, User


def test_signup_creates_and_signs_in_viewer(client, app):
    response = client.post(
        "/signup",
        data={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ADA@Example.com",
            "phone": "555-0100",
            "password": "secure-pass",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    with app.app_context():
        user = User.query.filter_by(email="ada@example.com").one()
        assert user.first_name == "Ada"
        assert user.last_name == "Lovelace"
        assert user.phone == "555-0100"
        assert user.role == Role.VIEWER


def test_signup_rejects_existing_email(client, app):
    with app.app_context():
        existing_user = User(
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            phone="555-0100",
            password_hash="not-relevant",
            role=Role.VIEWER,
        )
        from asset_manager.extensions import db

        db.session.add(existing_user)
        db.session.commit()

    response = client.post(
        "/signup",
        data={
            "first_name": "Another",
            "last_name": "Person",
            "email": "ADA@example.com",
            "phone": "555-0101",
            "password": "another-pass",
        },
    )

    assert response.status_code == 200
    assert b"already exists" in response.data
    with app.app_context():
        assert User.query.filter_by(email="ada@example.com").count() == 1
