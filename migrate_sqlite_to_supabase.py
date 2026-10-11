#!/usr/bin/env python3
"""One-off migration: old SQLite files -> Supabase/Postgres.

Reads   <sqlite-dir>/central.db           (superadmins + clients)
        <sqlite-dir>/tenants/<slug>.db    (one per client)
Writes  the shared Postgres schema, giving every row of a client its tenant_id.

Everything runs in ONE transaction: if anything fails, nothing is written.

Usage:
    python migrate_sqlite_to_supabase.py --sqlite-dir ./data --dry-run   # test run, writes nothing
    python migrate_sqlite_to_supabase.py --sqlite-dir ./data             # real run
    python migrate_sqlite_to_supabase.py --sqlite-dir ./data --replace   # overwrite clients that already exist

Without --replace, a client whose slug already exists in Postgres is skipped,
so it is safe to run twice.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

from db import get_conn, init_schema, utcnow


def ts(value):
    """SQLite stored ISO strings like 2026-08-19T07:51:00Z -> timezone-aware datetime."""
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def open_sqlite(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(sconn, name):
    return sconn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def migrate_tenant(pg, sconn, tenant_id):
    """Copy one tenant's tables. Old per-file ids are remapped because ids now live in one shared table."""
    n = {}

    store_map = {}
    for s in sconn.execute("SELECT * FROM stores ORDER BY id"):
        row = pg.execute(
            "INSERT INTO stores(tenant_id, name, city, status) VALUES (%s,%s,%s,%s) RETURNING id",
            (tenant_id, s["name"] or "", s["city"] or "", s["status"] or "active"),
        ).fetchone()
        store_map[s["id"]] = row["id"]
    n["stores"] = len(store_map)

    for u in sconn.execute("SELECT * FROM users ORDER BY id"):
        pg.execute(
            "INSERT INTO users(tenant_id, username, password_hash, role, created_at) VALUES (%s,%s,%s,%s,%s)",
            (tenant_id, u["username"], u["password_hash"], u["role"] or "manager", ts(u["created_at"]) or utcnow()),
        )
    n["users"] = sconn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    product_map = {}
    for p in sconn.execute("SELECT * FROM products ORDER BY id"):
        row = pg.execute(
            """INSERT INTO products(tenant_id, sku, barcode, name, category, price, promo_price, store_id, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (tenant_id, p["sku"], p["barcode"] or "", p["name"] or "", p["category"] or "",
             p["price"] if p["price"] is not None else 0, p["promo_price"],
             store_map.get(p["store_id"]), ts(p["updated_at"]) or utcnow()),
        ).fetchone()
        product_map[p["id"]] = row["id"]
    n["products"] = len(product_map)

    for g in sconn.execute("SELECT * FROM gateways ORDER BY id"):
        pg.execute(
            """INSERT INTO gateways(tenant_id, gateway_id, store_id, model, ip_address, status, last_seen)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (tenant_id, g["gateway_id"], store_map.get(g["store_id"]), g["model"] or "", g["ip_address"] or "",
             g["status"] or "offline", ts(g["last_seen"])),
        )
    n["gateways"] = sconn.execute("SELECT COUNT(*) FROM gateways").fetchone()[0]

    for l in sconn.execute("SELECT * FROM labels ORDER BY id"):
        pg.execute(
            """INSERT INTO labels(tenant_id, label_id, model, gateway_id, status, battery, signal, product_id, last_update)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (tenant_id, l["label_id"], l["model"] or "", l["gateway_id"] or "", l["status"] or "offline",
             l["battery"] if l["battery"] is not None else 100, l["signal"] or 0,
             product_map.get(l["product_id"]), ts(l["last_update"])),
        )
    n["labels"] = sconn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]

    for u in sconn.execute("SELECT * FROM updates ORDER BY id"):  # keep original order -> ids stay chronological
        pg.execute(
            "INSERT INTO updates(tenant_id, label_id, sku, old_price, new_price, status, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (tenant_id, u["label_id"], u["sku"], u["old_price"], u["new_price"], u["status"], ts(u["created_at"]) or utcnow()),
        )
    n["updates"] = sconn.execute("SELECT COUNT(*) FROM updates").fetchone()[0]
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sqlite-dir", default="data", help="folder containing central.db and tenants/ (default: ./data)")
    ap.add_argument("--replace", action="store_true", help="overwrite clients that already exist in Postgres")
    ap.add_argument("--dry-run", action="store_true", help="run everything, then roll back")
    args = ap.parse_args()

    central_path = os.path.join(args.sqlite_dir, "central.db")
    if not os.path.exists(central_path):
        sys.exit(f"Cannot find {central_path}")

    init_schema()
    central = open_sqlite(central_path)
    report = []

    with get_conn() as pg:
        # Owners: the old database is the source of truth, so its password hash wins.
        for a in central.execute("SELECT * FROM superadmins"):
            pg.execute(
                "INSERT INTO superadmins(username, password_hash) VALUES (%s,%s) "
                "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash",
                (a["username"], a["password_hash"]),
            )

        for c in central.execute("SELECT * FROM clients ORDER BY id"):
            slug = c["slug"]
            existing = pg.execute("SELECT id FROM clients WHERE slug=%s", (slug,)).fetchone()
            if existing and not args.replace:
                report.append((slug, "SKIPPED (already in Postgres; use --replace to overwrite)", {}))
                continue
            if existing:
                pg.execute("DELETE FROM clients WHERE id=%s", (existing["id"],))  # cascades to all tenant rows

            tenant_id = pg.execute(
                """INSERT INTO clients(slug, company_name, city, contact_email, contact_phone, plan, license_key,
                                       status, expires_at, created_at, notes)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (slug, c["company_name"], c["city"] or "", c["contact_email"] or "", c["contact_phone"] or "",
                 c["plan"] or "basic", c["license_key"], c["status"] or "active",
                 ts(c["expires_at"]) or utcnow(), ts(c["created_at"]) or utcnow(), c["notes"] or ""),
            ).fetchone()["id"]

            tpath = os.path.join(args.sqlite_dir, "tenants", f"{slug}.db")
            if not os.path.exists(tpath):
                report.append((slug, "client created, but NO tenant database file found", {}))
                continue
            sconn = open_sqlite(tpath)
            counts = migrate_tenant(pg, sconn, tenant_id)
            sconn.close()

            # Verify what landed in Postgres matches what was in the SQLite file
            for table, expected in counts.items():
                got = pg.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE tenant_id=%s", (tenant_id,)).fetchone()["n"]
                if got != expected:
                    raise RuntimeError(f"{slug}: {table} has {got} rows in Postgres but {expected} in SQLite")
            report.append((slug, "migrated", counts))

        if args.dry_run:
            pg.rollback()

    print("\nMigration report" + ("  [DRY RUN - nothing was written]" if args.dry_run else ""))
    print("-" * 60)
    for slug, status, counts in report:
        print(f"{slug}: {status}")
        if counts:
            print("    " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print("-" * 60)


if __name__ == "__main__":
    main()
