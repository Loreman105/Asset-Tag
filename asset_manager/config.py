"""Application configuration."""

import os
from pathlib import Path


class Config:
    BASE_DIR = Path(__file__).resolve().parent
    INSTANCE_DIR = BASE_DIR / "instance"
    UPLOAD_FOLDER = BASE_DIR / "static" / "uploads"
    BARCODE_FOLDER = BASE_DIR / "static" / "barcodes"
    BACKUP_FOLDER = BASE_DIR / "backups"

    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key-before-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'asset_manager.sqlite3'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    WTF_CSRF_ENABLED = True

    CHURCH_NAME = os.environ.get("CHURCH_NAME", "Church Asset Management")
    REMEMBER_COOKIE_DURATION_DAYS = 30
