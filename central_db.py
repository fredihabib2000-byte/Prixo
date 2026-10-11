"""Central tables: superadmins + clients (licenses)."""
from datetime import timedelta

from config import BOOTSTRAP_ADMIN_PASSWORD, BOOTSTRAP_ADMIN_USERNAME, DEFAULT_TRIAL_DAYS
from db import get_conn, init_schema, use_conn, utcnow
from security import generate_license_key, hash_password, slugify


def init_central_db():
    """Create the schema and, on a brand-new database, the first owner account."""
    init_schema()
    with get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM superadmins").fetchone()["n"]
        if n == 0:
            conn.execute(
                "INSERT INTO superadmins(username, password_hash) VALUES (%s, %s) "
                "ON CONFLICT (username) DO NOTHING",
                (BOOTSTRAP_ADMIN_USERNAME, hash_password(BOOTSTRAP_ADMIN_PASSWORD)),
            )


def create_client(company_name, city, contact_email, contact_phone, plan, trial_days=None, notes="", conn=None):
    with use_conn(conn) as c:
        base_slug = slugify(company_name)
        slug = base_slug
        i = 2
        while c.execute("SELECT 1 FROM clients WHERE slug=%s", (slug,)).fetchone():
            slug = f"{base_slug}-{i}"
            i += 1
        expires_at = utcnow() + timedelta(days=trial_days or DEFAULT_TRIAL_DAYS)
        return c.execute(
            """INSERT INTO clients(slug, company_name, city, contact_email, contact_phone,
                                   plan, license_key, status, expires_at, notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'active',%s,%s)
               RETURNING *""",
            (slug, company_name, city, contact_email, contact_phone, plan, generate_license_key(), expires_at, notes),
        ).fetchone()


def get_client_by_slug(slug):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM clients WHERE slug=%s", (slug,)).fetchone()


def get_client_by_id(client_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM clients WHERE id=%s", (client_id,)).fetchone()


def list_clients():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM clients ORDER BY id DESC").fetchall()


def set_client_status(client_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE clients SET status=%s WHERE id=%s", (status, client_id))


def set_client_plan(client_id, plan):
    with get_conn() as conn:
        conn.execute("UPDATE clients SET plan=%s WHERE id=%s", (plan, client_id))


def extend_license(client_id, days):
    """Add `days` to the license (from today if it already expired) and reactivate."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE clients
               SET expires_at = GREATEST(expires_at, now()) + make_interval(days => %s),
                   status = 'active'
               WHERE id = %s""",
            (days, client_id),
        )


def regenerate_license_key(client_id):
    new_key = generate_license_key()
    with get_conn() as conn:
        conn.execute("UPDATE clients SET license_key=%s WHERE id=%s", (new_key, client_id))
    return new_key


def license_state(client_row):
    """Returns ('ok'|'expired'|'suspended'|'missing', client_row)"""
    if client_row is None:
        return "missing", None
    if client_row["status"] == "suspended":
        return "suspended", client_row
    expires = client_row["expires_at"]
    if expires is None or expires < utcnow():
        return "expired", client_row
    return "ok", client_row


def get_superadmin(username):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM superadmins WHERE username=%s", (username,)).fetchone()
