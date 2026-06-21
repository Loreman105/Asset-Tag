# Church Asset Management System

A Flask-based system for managing church-owned electronic equipment, checkouts, maintenance, warranties, barcode labels, reports, users, and audit logs.

## Stack

- Python 3.13+
- Flask, SQLAlchemy, Flask-Login, Flask-Migrate, Flask-WTF, Flask-Bcrypt
- SQLite for development
- PostgreSQL through `DATABASE_URL` for production
- Bootstrap 5 and Jinja2 templates

## Run Locally

```powershell
pip install -r requirements.txt
flask --app asset_manager.app run --host 0.0.0.0
```

Then open:

```text
http://127.0.0.1:5000
```

Default administrator:

```text
Email: admin@church.local
Password: admin123456
```

Change the default password and `SECRET_KEY` before entering real records.

## Asset IDs

Asset IDs use the requested `PPYYNNNNVV` format.

Example: `1024000100`

- `PP`: configurable department prefix
- `YY`: year added
- `NNNN`: sequence number that does not reset yearly
- `VV`: version/reuse counter

## Deployment Notes

The app is suitable for local network access, reverse proxy deployment, HTTPS termination, Tailscale, or Cloudflare Tunnel. It does not require public port forwarding.
