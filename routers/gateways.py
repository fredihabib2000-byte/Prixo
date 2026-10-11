from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg import errors

from db import get_conn
from deps import guard_tenant
from templating import templates
from tenant_db import resolve_store_id

router = APIRouter()


@router.get("/gateways", response_class=HTMLResponse)
def gateways(r: Request):
    if (x := guard_tenant(r)):
        return x
    sess = r.session["user"]
    client = r.state.client
    t = client["id"]
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT g.*, s.name AS store_name
               FROM gateways g
               LEFT JOIN stores s ON s.tenant_id = g.tenant_id AND s.id = g.store_id
               WHERE g.tenant_id = %s
               ORDER BY g.id""",
            (t,),
        ).fetchall()
        stores = conn.execute("SELECT * FROM stores WHERE tenant_id=%s ORDER BY id", (t,)).fetchall()
    return templates.TemplateResponse(
        "gateways.html",
        {"request": r, "active": "gateways", "gateways": rows, "stores": stores, "user": sess,
         "company_name": client["company_name"]},
    )


@router.post("/gateways")
def add_gateway(r: Request, gateway_id: str = Form(...), model: str = Form(""), ip_address: str = Form(""), store_id: int | None = Form(None)):
    if (x := guard_tenant(r)):
        return x
    t = r.state.client["id"]
    try:
        with get_conn() as conn:
            sid = resolve_store_id(t, store_id, conn)
            conn.execute(
                "INSERT INTO gateways(tenant_id, gateway_id, model, ip_address, store_id, last_seen) "
                "VALUES (%s,%s,%s,%s,%s, now())",
                (t, gateway_id, model, ip_address, sid),
            )
    except errors.UniqueViolation:
        return RedirectResponse("/gateways?msg=Gateway+ID+already+exists", 303)
    return RedirectResponse("/gateways", 303)
