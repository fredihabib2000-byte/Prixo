from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from db import get_conn
from deps import guard_tenant, plan_limit_exceeded
from templating import templates

router = APIRouter()


@router.get("/stores", response_class=HTMLResponse)
def stores(r: Request):
    if (x := guard_tenant(r)):
        return x
    sess = r.session["user"]
    client = r.state.client
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT s.*, COUNT(p.id) AS product_count
               FROM stores s
               LEFT JOIN products p ON p.tenant_id = s.tenant_id AND p.store_id = s.id
               WHERE s.tenant_id = %s
               GROUP BY s.id
               ORDER BY s.id""",
            (client["id"],),
        ).fetchall()
        limit_hit, limit, current = plan_limit_exceeded(client, "stores", conn)
    return templates.TemplateResponse(
        "stores.html",
        {"request": r, "active": "stores", "stores": rows, "user": sess,
         "company_name": client["company_name"],
         "limit_hit": limit_hit, "limit": limit},
    )


@router.post("/stores")
def add_store(r: Request, name: str = Form(...), city: str = Form("")):
    if (x := guard_tenant(r)):
        return x
    client = r.state.client
    with get_conn() as conn:
        limit_hit, limit, current = plan_limit_exceeded(client, "stores", conn)
        if limit_hit:
            return RedirectResponse(f"/stores?msg=Plan+limit+of+{limit}+stores+reached", 303)
        conn.execute("INSERT INTO stores(tenant_id, name, city) VALUES (%s,%s,%s)", (client["id"], name, city))
    return RedirectResponse("/stores", 303)
