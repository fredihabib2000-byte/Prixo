from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse

from central_db import get_client_by_slug, license_state
from db import get_conn
from deps import get_session_client
from security import verify_password
from templating import templates, fmt_date

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_page(r: Request):
    sess = r.session.get("user")
    if sess and "tenant_id" in sess:
        return RedirectResponse("/", 303)
    return templates.TemplateResponse("login.html", {"request": r, "error": None, "tenant": ""})


@router.post("/login")
def login(r: Request, tenant: str = Form(...), username: str = Form(...), password: str = Form(...)):
    tenant = tenant.strip().lower()
    client = get_client_by_slug(tenant)
    state, client = license_state(client)
    if state == "missing":
        return templates.TemplateResponse("login.html", {"request": r, "error": "Unknown company code.", "tenant": tenant})
    if state != "ok":
        r.session["user"] = None  # not logging in, just informing
        return templates.TemplateResponse(
            "license_expired.html",
            {"request": r, "state": state, "company_name": client["company_name"], "expires_at": fmt_date(client["expires_at"])},
        )

    with get_conn() as conn:
        u = conn.execute(
            "SELECT * FROM users WHERE tenant_id=%s AND username=%s", (client["id"], username)
        ).fetchone()
    if not u or not verify_password(password, u["password_hash"]):
        return templates.TemplateResponse("login.html", {"request": r, "error": "Invalid username or password.", "tenant": tenant})

    r.session["user"] = {"username": u["username"], "role": u["role"], "tenant": tenant, "tenant_id": client["id"]}
    return RedirectResponse("/", 303)


@router.get("/logout")
def logout(r: Request):
    r.session.clear()
    return RedirectResponse("/login", 303)


@router.get("/license-expired", response_class=HTMLResponse)
def license_expired_page(r: Request):
    sess = r.session.get("user")
    if not sess or "tenant_id" not in sess:
        return RedirectResponse("/login", 303)
    client = get_session_client(sess)
    state, client = license_state(client)
    if state == "ok":
        return RedirectResponse("/", 303)
    if state == "missing":
        # The session points at a company that no longer exists (deleted client,
        # or stale/reset data) — clear it and send them back to login instead of crashing.
        r.session.clear()
        return RedirectResponse("/login", 303)
    return templates.TemplateResponse(
        "license_expired.html",
        {"request": r, "state": state, "company_name": client["company_name"], "expires_at": fmt_date(client["expires_at"])},
    )
