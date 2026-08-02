from asset_manager.app import create_app
from asset_manager.database.models import Asset, Role, User
from asset_manager.extensions import db
from asset_manager.utils import asset_code_from_scan


def test_qr_url_extracts_asset_id():
    assert asset_code_from_scan("http://InventoryHub.local/assets/1024000100") == "1024000100"
    assert asset_code_from_scan("1024000100") == "1024000100"


def test_qr_code_is_served_to_authenticated_user():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        asset = Asset(asset_id="1024000100", barcode_value="1024000100", description="Camera", department="AV")
        user = User(first_name="Test", last_name="Admin", email="qr@example.com", password_hash="hashed", role=Role.ADMIN)
        db.session.add_all([asset, user])
        db.session.commit()
        user_id = user.id
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True
    response = client.get("/assets/1024000100/qr-code")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
