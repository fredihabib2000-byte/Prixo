from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from psycopg import errors

from db import get_conn
from deps import guard_tenant, plan_limit_exceeded
from templating import templates

router = APIRouter()


@router.get("/labels", response_class=HTMLResponse)
def labels(r: Request):
    if (x := guard_tenant(r)):
        return x
    sess = r.session["user"]
    client = r.state.client
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT l.*, p.sku, p.name, p.price
               FROM labels l
               LEFT JOIN products p ON p.tenant_id = l.tenant_id AND p.id = l.product_id
               WHERE l.tenant_id = %s
               ORDER BY l.id DESC""",
            (client["id"],),
        ).fetchall()
        limit_hit, limit, current = plan_limit_exceeded(client, "labels", conn)
    return templates.TemplateResponse(
        "labels.html",
        {
            "request": r, "active": "labels", "labels": rows, "user": sess,
            "company_name": client["company_name"],
            "limit_hit": limit_hit, "limit": limit,
        },
    )


@router.post("/labels")
def add_label(r: Request, label_id: str = Form(...), model: str = Form("2.66in"), gateway_id: str = Form("gateway-1"), battery: int = Form(100)):
    if (x := guard_tenant(r)):
        return x
    client = r.state.client
    try:
        with get_conn() as conn:
            limit_hit, limit, current = plan_limit_exceeded(client, "labels", conn)
            if limit_hit:
                return RedirectResponse(f"/labels?msg=Plan+limit+of+{limit}+labels+reached", 303)
            conn.execute(
                "INSERT INTO labels(tenant_id, label_id, model, gateway_id, battery, last_update) "
                "VALUES (%s,%s,%s,%s,%s, now())",
                (client["id"], label_id, model, gateway_id, battery),
            )
    except errors.UniqueViolation:
        return RedirectResponse("/labels?msg=Label+ID+already+exists", 303)
    return RedirectResponse("/labels", 303)


@router.post("/labels/assign")
def assign(r: Request, label_id: str = Form(...), sku: str = Form(...)):
    if (x := guard_tenant(r)):
        return x
    t = r.state.client["id"]
    with get_conn() as conn:
        p = conn.execute("SELECT id FROM products WHERE tenant_id=%s AND sku=%s", (t, sku)).fetchone()
        if p:
            conn.execute(
                "UPDATE labels SET product_id=%s WHERE tenant_id=%s AND label_id=%s",
                (p["id"], t, label_id),
            )
    return RedirectResponse("/labels", 303)
