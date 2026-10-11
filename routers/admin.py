from datetime import timedelta

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from central_db import (
    get_superadmin, list_clients, get_client_by_id, create_client,
    set_client_status, set_client_plan, extend_license, regenerate_license_key,
    license_state,
)
from config import PLANS
from db import get_conn, utcnow
from deps import guard_superadmin
from security import verify_password, generate_password
from templating import templates
from tenant_db import init_tenant_db, counts, list_users, reset_user_password

router = APIRouter(prefix="/admin")


@router.get("/login", response_class=HTMLResponse)
def admin_login_page(r: Request):
    if r.session.get("superadmin"):
        return RedirectResponse("/admin", 303)
    return templates.TemplateResponse("admin_login.html", {"request": r, "error": None})


@router.post("/login")
def admin_login(r: Request, username: str = Form(...), password: str = Form(...)):
    a = get_superadmin(username)
    if not a or not verify_password(password, a["password_hash"]):
        return templates.TemplateResponse("admin_login.html", {"request": r, "error": "Invalid credentials."})
    r.session["superadmin"] = {"username": a["username"]}
    return RedirectResponse("/admin", 303)


@router.get("/logout")
def admin_logout(r: Request):
    r.session.pop("superadmin", None)
    return RedirectResponse("/admin/login", 303)


@router.get("", response_class=HTMLResponse)
def admin_dashboard(r: Request):
    if (x := guard_superadmin(r)):
        return x
    clients = list_clients()
    enriched = []
    active_count = expiring_count = inactive_count = 0
    now = utcnow()
    for c in clients:
        state, _ = license_state(c)
        row = dict(c)
        row["computed_state"] = state
        enriched.append(row)
        if state == "ok":
            active_count += 1
            if c["expires_at"] - now < timedelta(days=7):
                expiring_count += 1
        else:
            inactive_count += 1
    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": r, "clients": enriched, "total": len(clients),
            "active_count": active_count, "expiring_count": expiring_count, "inactive_count": inactive_count,
        },
    )


@router.get("/clients/new", response_class=HTMLResponse)
def new_client_form(r: Request):
    if (x := guard_superadmin(r)):
        return x
    return templates.TemplateResponse(
        "admin_client_new.html", {"request": r, "plans": PLANS, "suggested_password": generate_password()}
    )


@router.post("/clients/new")
def new_client_submit(
    r: Request, company_name: str = Form(...), city: str = Form(""), plan: str = Form("basic"),
    contact_email: str = Form(""), contact_phone: str = Form(""), trial_days: int = Form(365),
    admin_username: str = Form("admin"), admin_password: str = Form(...),
):
    if (x := guard_superadmin(r)):
        return x
    # One transaction: either the client AND its first store/admin user are created, or nothing is.
    with get_conn() as conn:
        client = create_client(company_name, city, contact_email, contact_phone, plan, trial_days, conn=conn)
        init_tenant_db(
            client["id"], admin_username, admin_password,
            store_name=f"{company_name} - Main", store_city=city, conn=conn,
        )
    return templates.TemplateResponse(
        "admin_client_created.html",
        {"request": r, "client": client, "admin_username": admin_username, "admin_password": admin_password},
    )


@router.get("/clients/{client_id}", response_class=HTMLResponse)
def client_detail(r: Request, client_id: int):
    if (x := guard_superadmin(r)):
        return x
    client = get_client_by_id(client_id)
    if not client:
        return RedirectResponse("/admin?msg=Client+not+found", 303)
    state, _ = license_state(client)
    usage = counts(client["id"])
    limits = PLANS.get(client["plan"], PLANS["basic"])
    users = list_users(client["id"])
    return templates.TemplateResponse(
        "admin_client_detail.html",
        {"request": r, "client": client, "state": state, "usage": usage, "limits": limits, "plans": PLANS, "users": users},
    )


@router.post("/clients/{client_id}/users/{user_id}/reset-password")
def reset_password(r: Request, client_id: int, user_id: int, new_password: str = Form(...)):
    if (x := guard_superadmin(r)):
        return x
    client = get_client_by_id(client_id)
    if not client:
        return RedirectResponse("/admin?msg=Client+not+found", 303)
    reset_user_password(client["id"], user_id, new_password)
    return RedirectResponse(f"/admin/clients/{client_id}?msg=Password+reset", 303)


@router.post("/clients/{client_id}/renew")
def renew(r: Request, client_id: int, days: int = Form(...)):
    if (x := guard_superadmin(r)):
        return x
    extend_license(client_id, days)
    return RedirectResponse(f"/admin/clients/{client_id}?msg=License+renewed", 303)


@router.post("/clients/{client_id}/plan")
def change_plan(r: Request, client_id: int, plan: str = Form(...)):
    if (x := guard_superadmin(r)):
        return x
    set_client_plan(client_id, plan)
    return RedirectResponse(f"/admin/clients/{client_id}?msg=Plan+updated", 303)


@router.post("/clients/{client_id}/suspend")
def suspend(r: Request, client_id: int):
    if (x := guard_superadmin(r)):
        return x
    set_client_status(client_id, "suspended")
    return RedirectResponse(f"/admin/clients/{client_id}?msg=Client+suspended", 303)


@router.post("/clients/{client_id}/activate")
def activate(r: Request, client_id: int):
    if (x := guard_superadmin(r)):
        return x
    set_client_status(client_id, "active")
    return RedirectResponse(f"/admin/clients/{client_id}?msg=Client+reactivated", 303)


@router.post("/clients/{client_id}/regenerate-key")
def regen_key(r: Request, client_id: int):
    if (x := guard_superadmin(r)):
        return x
    regenerate_license_key(client_id)
    return RedirectResponse(f"/admin/clients/{client_id}?msg=License+key+regenerated", 303)
