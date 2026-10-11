from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from central_db import license_state
from db import get_conn
from deps import get_session_client

router = APIRouter()


class FakeGateway:
    def push_price(self, label_id, product):
        return {"ok": True}


gateway = FakeGateway()


@router.get("/api/health")
def health():
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        db = "ok"
    except Exception:
        db = "error"
    body = {"status": "ok" if db == "ok" else "degraded", "database": db, "product": "PRIXO ESL Manager", "version": "3.1"}
    return JSONResponse(body, 200 if db == "ok" else 503)


class PriceUpdate(BaseModel):
    sku: str
    price: float


@router.post("/api/price")
def api_price(r: Request, d: PriceUpdate):
    sess = r.session.get("user")
    if not sess or "tenant_id" not in sess:
        return JSONResponse({"error": "Authentication required"}, 401)
    state, client = license_state(get_session_client(sess))
    if state != "ok":
        return JSONResponse({"error": f"License {state}"}, 402)
    t = client["id"]

    with get_conn() as conn:
        p = conn.execute("SELECT * FROM products WHERE tenant_id=%s AND sku=%s", (t, d.sku)).fetchone()
        if not p:
            return JSONResponse({"error": "SKU not found"}, 404)
        old = p["price"]
        conn.execute("UPDATE products SET price=%s, updated_at=now() WHERE tenant_id=%s AND sku=%s", (d.price, t, d.sku))
        n = 0
        for l in conn.execute("SELECT * FROM labels WHERE tenant_id=%s AND product_id=%s", (t, p["id"])).fetchall():
            if gateway.push_price(l["label_id"], dict(p) | {"price": d.price})["ok"]:
                n += 1
            conn.execute(
                "INSERT INTO updates(tenant_id, label_id, sku, old_price, new_price, status) VALUES (%s,%s,%s,%s,%s,%s)",
                (t, l["label_id"], d.sku, old, d.price, "sent"),
            )
    return {"ok": True, "sku": d.sku, "price": d.price, "labels_updated": n}
