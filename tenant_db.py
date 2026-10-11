"""Tenant data helpers. Every query is scoped by tenant_id (= clients.id)."""
from db import get_conn, use_conn
from security import hash_password

# resource name -> table (whitelist, so the name can safely go into SQL)
_RESOURCE_TABLES = {
    "products": "products",
    "labels": "labels",
    "stores": "stores",
    "users": "users",
}


def init_tenant_db(tenant_id, admin_username, admin_password, store_name="Main Store", store_city="", conn=None):
    """Give a new client its first store and its admin user."""
    with use_conn(conn) as c:
        if c.execute("SELECT COUNT(*) AS n FROM stores WHERE tenant_id=%s", (tenant_id,)).fetchone()["n"] == 0:
            c.execute("INSERT INTO stores(tenant_id, name, city) VALUES (%s,%s,%s)", (tenant_id, store_name, store_city))
        if c.execute("SELECT COUNT(*) AS n FROM users WHERE tenant_id=%s", (tenant_id,)).fetchone()["n"] == 0:
            c.execute(
                "INSERT INTO users(tenant_id, username, password_hash, role) VALUES (%s,%s,%s,'admin')",
                (tenant_id, admin_username, hash_password(admin_password)),
            )


def default_store_id(tenant_id, conn=None):
    """The tenant's first store (used when a form doesn't specify one)."""
    with use_conn(conn) as c:
        row = c.execute("SELECT MIN(id) AS id FROM stores WHERE tenant_id=%s", (tenant_id,)).fetchone()
        return row["id"]


def resolve_store_id(tenant_id, store_id, conn=None):
    """Return store_id if it belongs to this tenant, else the tenant's default store (or None)."""
    with use_conn(conn) as c:
        if store_id is not None:
            ok = c.execute("SELECT 1 FROM stores WHERE tenant_id=%s AND id=%s", (tenant_id, store_id)).fetchone()
            if ok:
                return store_id
        return default_store_id(tenant_id, c)


def list_users(tenant_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, username, role, created_at FROM users WHERE tenant_id=%s ORDER BY id", (tenant_id,)
        ).fetchall()


def reset_user_password(tenant_id, user_id, new_password):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=%s WHERE tenant_id=%s AND id=%s",
            (hash_password(new_password), tenant_id, user_id),
        )


def count_resource(tenant_id, resource, conn=None):
    table = _RESOURCE_TABLES[resource]
    with use_conn(conn) as c:
        return c.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE tenant_id=%s", (tenant_id,)).fetchone()["n"]


def counts(tenant_id):
    with get_conn() as conn:
        return conn.execute(
            """SELECT
                 (SELECT COUNT(*) FROM products WHERE tenant_id=%(t)s) AS products,
                 (SELECT COUNT(*) FROM labels   WHERE tenant_id=%(t)s) AS labels,
                 (SELECT COUNT(*) FROM stores   WHERE tenant_id=%(t)s) AS stores,
                 (SELECT COUNT(*) FROM users    WHERE tenant_id=%(t)s) AS users""",
            {"t": tenant_id},
        ).fetchone()
