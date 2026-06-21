"""Database seeding and audit helpers."""

from flask import request

from asset_manager.database.models import (
    AssetStatus,
    AuditLog,
    Category,
    DepartmentPrefix,
    Role,
    Setting,
    StatusValue,
    User,
)
from asset_manager.extensions import bcrypt, db


DEFAULT_PREFIXES = [
    ("10", "AV"),
    ("20", "Children's Ministry"),
    ("30", "Worship"),
    ("40", "Administration"),
    ("50", "IT"),
    ("60", "Facilities"),
]

DEFAULT_CATEGORIES = [
    "Computer",
    "Camera",
    "Audio",
    "Lighting",
    "Networking",
    "Display",
    "Printer",
    "Accessory",
]

DEFAULT_STATUSES = [
    AssetStatus.AVAILABLE,
    AssetStatus.CHECKED_OUT,
    AssetStatus.IN_MAINTENANCE,
    AssetStatus.RETIRED,
    AssetStatus.LOST,
    AssetStatus.DAMAGED,
]


def seed_database():
    for code, name in DEFAULT_PREFIXES:
        if not DepartmentPrefix.query.filter_by(code=code).first():
            db.session.add(DepartmentPrefix(code=code, name=name))

    for name in DEFAULT_CATEGORIES:
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name))

    for name in DEFAULT_STATUSES:
        if not StatusValue.query.filter_by(name=name).first():
            db.session.add(StatusValue(name=name))

    if not Setting.query.filter_by(key="church_name").first():
        db.session.add(Setting(key="church_name", value="Church Asset Management"))

    if not User.query.first():
        db.session.add(
            User(
                first_name="System",
                last_name="Administrator",
                email="admin@church.local",
                password_hash=bcrypt.generate_password_hash("admin123456").decode("utf-8"),
                role=Role.ADMIN,
            )
        )

    db.session.commit()


def log_activity(user_id, action, object_type, object_id, details=None):
    db.session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            object_type=object_type,
            object_id=str(object_id),
            details=details,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        )
    )
    db.session.commit()
