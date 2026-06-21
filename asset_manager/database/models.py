"""SQLAlchemy models for the Church Asset Management System."""

from datetime import datetime, timezone

from flask_login import UserMixin

from asset_manager.extensions import db, login_manager


def utc_now():
    return datetime.now(timezone.utc)


class Role:
    ADMIN = "administrator"
    MODERATOR = "moderator"
    VIEWER = "viewer"


class AssetStatus:
    AVAILABLE = "Available"
    CHECKED_OUT = "Checked Out"
    IN_MAINTENANCE = "In Maintenance"
    RETIRED = "Retired"
    LOST = "Lost"
    DAMAGED = "Damaged"


class Condition:
    EXCELLENT = "Excellent"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"
    DAMAGED = "Damaged"


class MaintenanceType:
    INSPECTION = "Inspection"
    REPAIR = "Repair"
    UPGRADE = "Upgrade"
    CLEANING = "Cleaning"
    WARRANTY_SERVICE = "Warranty Service"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    phone = db.Column(db.String(40))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, default=Role.VIEWER)
    is_active_account = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    assigned_assets = db.relationship("Asset", back_populates="assigned_user", foreign_keys="Asset.assigned_user_id")

    @property
    def is_active(self):
        return self.is_active_account

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def can_manage_assets(self):
        return self.role in {Role.ADMIN, Role.MODERATOR}

    def can_manage_settings(self):
        return self.role == Role.ADMIN


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class DepartmentPrefix(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(2), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class StatusValue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.String(10), nullable=False, unique=True, index=True)
    barcode_value = db.Column(db.String(10), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(120))
    manufacturer = db.Column(db.String(120))
    model_number = db.Column(db.String(120))
    serial_number = db.Column(db.String(120), index=True)
    department = db.Column(db.String(120), nullable=False)
    ministry = db.Column(db.String(120))
    purchase_date = db.Column(db.Date)
    purchase_cost = db.Column(db.Numeric(10, 2))
    vendor = db.Column(db.String(160))
    status = db.Column(db.String(60), nullable=False, default=AssetStatus.AVAILABLE)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    current_location = db.Column(db.String(160))
    condition = db.Column(db.String(60), nullable=False, default=Condition.GOOD)
    warranty_provider = db.Column(db.String(160))
    warranty_expiration_date = db.Column(db.Date)
    warranty_notes = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    assigned_user = db.relationship("User", back_populates="assigned_assets", foreign_keys=[assigned_user_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])
    photos = db.relationship("AssetPhoto", back_populates="asset", cascade="all, delete-orphan")
    documents = db.relationship("AssetDocument", back_populates="asset", cascade="all, delete-orphan")
    checkouts = db.relationship("Checkout", back_populates="asset", cascade="all, delete-orphan")
    maintenance_records = db.relationship("MaintenanceRecord", back_populates="asset", cascade="all, delete-orphan")

    @property
    def primary_photo(self):
        return next((photo for photo in self.photos if photo.is_primary), None)


class Checkout(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    user_receiving_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    checked_out_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    checked_out_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    expected_return_date = db.Column(db.Date)
    checkout_condition = db.Column(db.String(60), nullable=False)
    checkout_notes = db.Column(db.Text)
    returned_at = db.Column(db.DateTime(timezone=True))
    returned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    return_condition = db.Column(db.String(60))
    return_notes = db.Column(db.Text)
    condition_worsened = db.Column(db.Boolean, nullable=False, default=False)

    asset = db.relationship("Asset", back_populates="checkouts")
    user_receiving = db.relationship("User", foreign_keys=[user_receiving_id])
    checked_out_by = db.relationship("User", foreign_keys=[checked_out_by_id])
    returned_by = db.relationship("User", foreign_keys=[returned_by_id])


class MaintenanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    service_date = db.Column(db.Date, nullable=False)
    maintenance_type = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    cost = db.Column(db.Numeric(10, 2))
    performed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    asset = db.relationship("Asset", back_populates="maintenance_records")
    performed_by = db.relationship("User")


class AssetPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    thumbnail_filename = db.Column(db.String(255))
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    asset = db.relationship("Asset", back_populates="photos")
    uploaded_by = db.relationship("User")


class AssetDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    asset = db.relationship("Asset", back_populates="documents")
    uploaded_by = db.relationship("User")


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(120), nullable=False)
    object_type = db.Column(db.String(80), nullable=False)
    object_id = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(64))

    user = db.relationship("User")


class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), nullable=False, unique=True)
    value = db.Column(db.Text)
