"""Portable full-system backup and restore helpers."""

import json
import shutil
import base64
import hashlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from flask import current_app
from sqlalchemy import Date, DateTime, Numeric

from asset_manager.database.models import Setting
from asset_manager.extensions import db

BACKUP_FORMAT = 1
FILE_AREAS = {
    "uploads": "UPLOAD_FOLDER",
    "barcodes": "BARCODE_FOLDER",
    "qrcodes": "QR_CODE_FOLDER",
}


def _encode(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _decode(value, column):
    if value is None:
        return None
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Date):
        return date.fromisoformat(value)
    if isinstance(column.type, Numeric):
        return Decimal(value)
    return value


def _database_payload():
    tables = {}
    for table in db.metadata.sorted_tables:
        rows = db.session.execute(table.select()).mappings().all()
        tables[table.name] = [
            {column.name: _encode(row[column.name]) for column in table.columns}
            for row in rows
        ]
    return {"format_version": BACKUP_FORMAT, "created_at": datetime.now(timezone.utc).isoformat(), "tables": tables}


def create_backup():
    """Return a full Inventory Hub backup archive in memory."""
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as zip_file:
        zip_file.writestr("inventory-hub-data.json", json.dumps(_database_payload(), indent=2))
        for archive_area, config_key in FILE_AREAS.items():
            root = Path(current_app.config[config_key])
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file():
                    zip_file.write(path, f"files/{archive_area}/{path.relative_to(root).as_posix()}")
    archive.seek(0)
    return archive


def save_scheduled_backup():
    destination = Path(current_app.config["BACKUP_FOLDER"])
    destination.mkdir(parents=True, exist_ok=True)
    filename = f"inventory-hub-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    path = destination / filename
    path.write_bytes(create_backup().getvalue())
    remote_success = True
    try:
        remote_destination = upload_backup(path)
        _set_setting("backup_remote_status", f"Uploaded to {remote_destination} at {datetime.now(timezone.utc).isoformat()}")
    except Exception as error:
        remote_success = False
        _set_setting("backup_remote_status", f"Upload failed: {error}")
    retention = max(1, int(_setting("backup_retention", "10")))
    backups = sorted(destination.glob("inventory-hub-*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
    for expired in backups[retention:]:
        expired.unlink()
    if remote_success:
        _set_setting("backup_last_run", datetime.now(timezone.utc).isoformat())
    db.session.commit()
    return path


def upload_backup(path):
    """Copy an archive to the configured off-server destination."""
    destination = _setting("backup_destination", "local")
    if destination == "local":
        return "local backup folder"
    if destination == "network_share":
        configured_path = _setting("backup_network_path").strip()
        if not configured_path:
            raise ValueError("Network share path is not configured.")
        remote_folder = Path(configured_path)
        remote_folder.mkdir(parents=True, exist_ok=True)
        remote_path = remote_folder / path.name
        shutil.copy2(path, remote_path)
        return str(remote_path)
    if destination == "sftp":
        return _upload_sftp(path)
    if destination == "s3":
        return _upload_s3(path)
    raise ValueError("Unknown backup destination.")


def _upload_sftp(path):
    import paramiko

    host = _setting("backup_sftp_host")
    username = _setting("backup_sftp_username")
    remote_folder = _setting("backup_sftp_path").rstrip("/")
    password = decrypt_secret(_setting("backup_sftp_password"))
    if not all((host, username, remote_folder, password)):
        raise ValueError("SFTP host, username, password, and folder are required.")
    transport = paramiko.Transport((host, int(_setting("backup_sftp_port", "22"))))
    try:
        transport.connect(username=username, password=password)
        client = paramiko.SFTPClient.from_transport(transport)
        current = ""
        for part in remote_folder.strip("/").split("/"):
            current += f"/{part}"
            try:
                client.stat(current)
            except IOError:
                client.mkdir(current)
        remote_path = f"{remote_folder}/{path.name}"
        client.put(str(path), remote_path)
        return f"sftp://{host}{remote_path}"
    finally:
        transport.close()


def _upload_s3(path):
    import boto3

    bucket = _setting("backup_s3_bucket")
    access_key = _setting("backup_s3_access_key")
    secret_key = decrypt_secret(_setting("backup_s3_secret_key"))
    if not all((bucket, access_key, secret_key)):
        raise ValueError("S3 bucket, access key, and secret key are required.")
    prefix = _setting("backup_s3_prefix").strip("/")
    key = f"{prefix}/{path.name}" if prefix else path.name
    client = boto3.client(
        "s3",
        endpoint_url=_setting("backup_s3_endpoint") or None,
        region_name=_setting("backup_s3_region", "us-east-1"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    client.upload_file(str(path), bucket, key)
    return f"s3://{bucket}/{key}"


def encrypt_secret(value):
    if not value:
        return ""
    from cryptography.fernet import Fernet

    key = base64.urlsafe_b64encode(hashlib.sha256(current_app.config["SECRET_KEY"].encode()).digest())
    return Fernet(key).encrypt(value.encode()).decode()


def decrypt_secret(value):
    if not value:
        return ""
    from cryptography.fernet import Fernet

    key = base64.urlsafe_b64encode(hashlib.sha256(current_app.config["SECRET_KEY"].encode()).digest())
    return Fernet(key).decrypt(value.encode()).decode()


def maybe_create_scheduled_backup():
    frequency = _setting("backup_frequency", "disabled")
    if frequency == "disabled":
        return None
    days = 1 if frequency == "daily" else 7
    last_run = _setting("backup_last_run")
    if last_run:
        try:
            if datetime.now(timezone.utc) - datetime.fromisoformat(last_run) < timedelta(days=days):
                return None
        except ValueError:
            pass
    return save_scheduled_backup()


def restore_backup(upload):
    """Replace app data and managed files with a validated backup archive."""
    with ZipFile(upload) as zip_file:
        if "inventory-hub-data.json" not in zip_file.namelist():
            raise ValueError("This is not an Inventory Hub backup archive.")
        payload = json.loads(zip_file.read("inventory-hub-data.json"))
        if payload.get("format_version") != BACKUP_FORMAT or not isinstance(payload.get("tables"), dict):
            raise ValueError("This backup uses an unsupported format.")
        allowed_files = {"inventory-hub-data.json"}
        for area in FILE_AREAS:
            allowed_files.update(name for name in zip_file.namelist() if name.startswith(f"files/{area}/"))
        if set(zip_file.namelist()) - allowed_files or any(".." in Path(name).parts for name in zip_file.namelist()):
            raise ValueError("The backup contains an unsafe file path.")

        table_by_name = {table.name: table for table in db.metadata.sorted_tables}
        if set(payload["tables"]) != set(table_by_name):
            raise ValueError("The backup database schema does not match this Inventory Hub installation.")
        try:
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            for table in db.metadata.sorted_tables:
                rows = payload["tables"][table.name]
                if rows:
                    decoded_rows = [
                        {column.name: _decode(row.get(column.name), column) for column in table.columns}
                        for row in rows
                    ]
                    db.session.execute(table.insert(), decoded_rows)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        for area, config_key in FILE_AREAS.items():
            root = Path(current_app.config[config_key])
            if root.exists():
                shutil.rmtree(root)
            root.mkdir(parents=True, exist_ok=True)
            prefix = f"files/{area}/"
            for name in zip_file.namelist():
                if name.startswith(prefix) and not name.endswith("/"):
                    destination = root / name.removeprefix(prefix)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with zip_file.open(name) as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target)


def _setting(key, default=""):
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting and setting.value is not None else default


def _set_setting(key, value):
    setting = Setting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        db.session.add(Setting(key=key, value=value))
