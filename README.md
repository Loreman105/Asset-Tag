# Asset Management System

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

## Inventory Hub local address

To make the server discoverable as `http://InventoryHub.local` on the local
network, start it with the mDNS launcher (use an elevated PowerShell if port
80 is reserved on the host):

```powershell
python run_inventory_hub.py
```

On Windows, [`start_inventory_hub.bat`](start_inventory_hub.bat) provides a
single-click launcher. It creates `.venv` when needed, installs the packages
from `requirements.txt`, starts the app and its built-in mDNS responder, then
opens `http://InventoryHub.local`. Right-click it and choose **Run as
administrator** when using the default port 80.

This advertises the service through mDNS and runs HTTP on port 80. Devices on
the same LAN can open `http://InventoryHub.local`; their operating system must
support mDNS (Windows Bonjour, macOS, iOS, and most Linux distributions do).
The Windows firewall must allow Python on **Private** networks, and the client
must be on the same Wi-Fi/LAN (not a guest network with client isolation). The
Windows launcher adds the required Private-network firewall rules when it is
run as an administrator.
You can override the name, port, or QR destination with `INVENTORY_HOSTNAME`,
`INVENTORY_PORT`, and `INVENTORY_BASE_URL` environment variables.

## QR and Code 128 labels

Each asset record supplies both a Code 128 barcode and a QR code. QR labels
encode the asset's Inventory Hub URL, so scanning one opens that asset record
directly. Batch labels include both formats. Set the organization name, logo,
timezone, and QR base URL in **Admin → Settings**.

## Full system backups

Administrators can download or restore a complete ZIP backup in **Admin →
Settings → Backups**. It includes all database records, documents, photos,
branding, QR codes, and barcodes. Restoring replaces the current inventory and
managed files, so download a fresh backup first.

Set the automatic backup frequency and retention count in the same screen.
Automatic backups can also be copied to a network share/NAS, an SFTP server,
or Amazon S3 and S3-compatible storage such as Backblaze B2, Wasabi,
Cloudflare R2, MinIO, or DigitalOcean Spaces. Configure the selected destination
and its credentials in **Admin → Settings → Backups**; the credentials are
encrypted using `SECRET_KEY`, so keep that key stable for future uploads.
Schedule the following command with Windows Task Scheduler (for example, every
night) to produce a backup when the configured interval is due:

```powershell
flask --app asset_manager.app backup-if-due
```

Default administrator:

```text
Email: admin@managment.local
Password: admin123456
```

Change the default password and `SECRET_KEY` before entering real records.

## Asset IDs

Asset IDs use the  `PPYYNNNNVV` format.

Example: `1024000100`

- `PP`: configurable department prefix
- `YY`: year added
- `NNNN`: sequence number that does not reset yearly
- `VV`: version/reuse counter

## Deployment Notes

The app is suitable for local network access, reverse proxy deployment, HTTPS termination, Tailscale, or Cloudflare Tunnel. It does not require public port forwarding.
