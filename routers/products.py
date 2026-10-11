import csv
import io

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from psycopg import errors

from db import get_conn
from deps import guard_tenant, plan_limit_exceeded, current_plan
from templating import templates
from tenant_db import resolve_store_id, count_resource

router = APIRouter()


class FakeGateway:
    def push_price(self, label_id, product):
        return {"ok": True}


gateway = FakeGateway()


def _like(q: str) -> str:
    """Wrap a search term for LIKE, treating %, _ and \\ literally."""
    q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{q}%"


@router.get("/products", response_class=HTMLResponse)
def products(r: Request, q: str = ""):
    if (x := guard_tenant(r)):
        return x
    sess = r.session["user"]
    client = r.state.client
    t = client["id"]
    like = _like(q)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.*, s.name AS store_name
               FROM products p
               LEFT JOIN stores s ON s.tenant_id = p.tenant_id AND s.id = p.store_id
               WHERE p.tenant_id = %s
                 AND (p.sku ILIKE %s OR p.barcode ILIKE %s OR p.name ILIKE %s)
               ORDER BY p.id DESC""",
            (t, like, like, like),
        ).fetchall()
        stores = conn.execute("SELECT * FROM stores WHERE tenant_id=%s ORDER BY id", (t,)).fetchall()
        limit_hit, limit, current = plan_limit_exceeded(client, "products", conn)
    return templates.TemplateResponse(
        "products.html",
        {
            "request": r, "active": "products", "products": rows, "stores": stores, "q": q,
            "user": sess, "company_name": client["company_name"],
            "limit_hit": limit_hit, "limit": limit,
        },
    )


@router.post("/products")
def add_product(
    r: Request, sku: str = Form(...), barcode: str = Form(""), name: str = Form(...),
    category: str = Form(""), price: float = Form(...), promo_price: str = Form(""), store_id: int | None = Form(None),
):
    if (x := guard_tenant(r)):
        return x
    client = r.state.client
    t = client["id"]
    try:
        promo = float(promo_price) if promo_price.strip() else None
    except ValueError:
        return RedirectResponse("/products?msg=Invalid+promo+price", 303)
    try:
        with get_conn() as conn:
            limit_hit, limit, current = plan_limit_exceeded(client, "products", conn)
            if limit_hit:
                return RedirectResponse(f"/products?msg=Plan+limit+of+{limit}+products+reached", 303)
            sid = resolve_store_id(t, store_id, conn)
            if sid is None:
                return RedirectResponse("/products?msg=Create+a+store+first", 303)
            conn.execute(
                "INSERT INTO products(tenant_id, sku, barcode, name, category, price, promo_price, store_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (t, sku, barcode, name, category, price, promo, sid),
            )
    except errors.UniqueViolation:
        return RedirectResponse("/products?msg=SKU+already+exists", 303)
    return RedirectResponse("/products", 303)


@router.post("/products/{sku}/price")
def push_price(r: Request, sku: str, price: float = Form(...)):
    if (x := guard_tenant(r)):
        return x
    t = r.state.client["id"]
    with get_conn() as conn:
        p = conn.execute("SELECT * FROM products WHERE tenant_id=%s AND sku=%s", (t, sku)).fetchone()
        if not p:
            return JSONResponse({"error": "SKU not found"}, 404)
        old = p["price"]
        conn.execute("UPDATE products SET price=%s, updated_at=now() WHERE tenant_id=%s AND sku=%s", (price, t, sku))
        for l in conn.execute("SELECT * FROM labels WHERE tenant_id=%s AND product_id=%s", (t, p["id"])).fetchall():
            ok = gateway.push_price(l["label_id"], dict(p) | {"price": price})["ok"]
            conn.execute(
                "INSERT INTO updates(tenant_id, label_id, sku, old_price, new_price, status) VALUES (%s,%s,%s,%s,%s,%s)",
                (t, l["label_id"], sku, old, price, "sent" if ok else "failed"),
            )
            conn.execute("UPDATE labels SET status='online', last_update=now() WHERE tenant_id=%s AND id=%s", (t, l["id"]))
    return RedirectResponse("/products", 303)


@router.post("/import")
async def import_csv(r: Request, file: UploadFile = File(...)):
    if (x := guard_tenant(r)):
        return x
    client = r.state.client
    t = client["id"]
    _, plan = current_plan(client)
    limit = plan.get("max_products")
    reader = csv.DictReader(io.StringIO((await file.read()).decode("utf-8-sig")))
    imported = skipped = 0
    with get_conn() as conn:
        store_id = resolve_store_id(t, None, conn)
        if store_id is None:
            return RedirectResponse("/products?msg=Create+a+store+first", 303)
        current = count_resource(t, "products", conn)
        for z in reader:
            if limit is not None and current >= limit:
                break
            sku = (z.get("sku") or "").strip()
            name = (z.get("name") or "").strip()
            if not sku or not name:
                continue
            try:
                promo = (z.get("promo_price") or "").strip()
                promo = float(promo) if promo else None
                price = float(z.get("price") or 0)
            except ValueError:
                skipped += 1
                continue
            row = conn.execute(
                """INSERT INTO products(tenant_id, sku, barcode, name, category, price, promo_price, store_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (tenant_id, sku) DO UPDATE SET
                       barcode = EXCLUDED.barcode, name = EXCLUDED.name, category = EXCLUDED.category,
                       price = EXCLUDED.price, promo_price = EXCLUDED.promo_price, updated_at = now()
                   RETURNING (xmax = 0) AS inserted""",
                (t, sku, z.get("barcode", ""), name, z.get("category", ""), price, promo, store_id),
            ).fetchone()
            if row["inserted"]:
                current += 1
            imported += 1
    msg = f"Imported+{imported}+rows" + (f"+({skipped}+skipped:+bad+numbers)" if skipped else "")
    return RedirectResponse(f"/products?msg={msg}", 303)
