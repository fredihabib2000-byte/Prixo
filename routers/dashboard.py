from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from db import get_conn
from deps import guard_tenant, current_plan
from templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home(r: Request):
    if (x := guard_tenant(r)):
        return x
    sess = r.session["user"]
    client = r.state.client
    t = client["id"]
    with get_conn() as conn:
        stats = conn.execute(
            """SELECT
                 (SELECT COUNT(*) FROM products WHERE tenant_id=%(t)s) AS products,
                 (SELECT COUNT(*) FROM labels   WHERE tenant_id=%(t)s) AS labels,
                 (SELECT COUNT(*) FROM labels   WHERE tenant_id=%(t)s AND status = 'online')  AS online,
                 (SELECT COUNT(*) FROM labels   WHERE tenant_id=%(t)s AND status != 'online') AS offline,
                 (SELECT COUNT(*) FROM gateways WHERE tenant_id=%(t)s) AS gateways,
                 (SELECT COUNT(*) FROM stores   WHERE tenant_id=%(t)s) AS stores""",
            {"t": t},
        ).fetchone()
        recent = conn.execute(
            """SELECT u.*, p.name
               FROM updates u
               LEFT JOIN products p ON p.tenant_id = u.tenant_id AND p.sku = u.sku
               WHERE u.tenant_id = %s
               ORDER BY u.id DESC LIMIT 8""",
            (t,),
        ).fetchall()
    _, plan = current_plan(client)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": r, "active": "dashboard", "stats": stats, "recent": recent,
            "user": sess, "company_name": client["company_name"],
            "plan_label": plan["label"],
        },
    )
