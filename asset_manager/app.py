"""Application factory for the Church Asset Management System."""

import sys
from pathlib import Path

if __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from flask import Flask, redirect, url_for

from asset_manager.config import Config
from asset_manager.database.db import seed_database
from asset_manager.extensions import bcrypt, csrf, db, login_manager, migrate
from asset_manager.routes.assets import bp as assets_bp
from asset_manager.routes.auth import bp as auth_bp
from asset_manager.routes.checkouts import bp as checkouts_bp
from asset_manager.routes.maintenance import bp as maintenance_bp
from asset_manager.routes.reports import bp as reports_bp
from asset_manager.routes.reservations import bp as reservations_bp
from asset_manager.routes.reservations import register_cli as register_reservation_cli
from asset_manager.routes.settings import bp as settings_bp
from asset_manager.routes.users import bp as users_bp


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    for path_key in ("INSTANCE_DIR", "UPLOAD_FOLDER", "BARCODE_FOLDER", "BACKUP_FOLDER"):
        Path(app.config[path_key]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(checkouts_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(reservations_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(users_bp)
    register_reservation_cli(app)

    @app.route("/")
    def index():
        return redirect(url_for("assets.dashboard"))

    with app.app_context():
        db.create_all()
        seed_database()

    return app


if __name__ == "__main__":
    create_app().run(debug=True, host="0.0.0.0")
