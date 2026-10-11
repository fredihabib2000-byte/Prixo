from fastapi import Request
from fastapi.responses import RedirectResponse

from central_db import get_client_by_id, license_state
from config import PLANS
from db import use_conn
from tenant_db import count_resource


def get_session_client(sess):
    """The client row a login session belongs to, or None if it no longer matches."""
    client = get_client_by_id(sess["tenant_id"])
    if client is None or client["slug"] != sess.get("tenant"):
        return None
    return client


def guard_tenant(r: Request):
    """Returns a RedirectResponse if access should be blocked, else None.
    Checks: logged in AND the client's license is currently valid (checked live,
    so a superadmin suspension/expiry takes effect immediately, mid-session).
    On success the client row is stored on r.state.client for the route to reuse."""
    sess = r.session.get("user")
    if not sess:
        return RedirectResponse("/login", 303)
    if "tenant_id" not in sess:  # session created by an older version of the app
        r.session.clear()
        return RedirectResponse("/login", 303)
    state, client = license_state(get_session_client(sess))
    if state != "ok":
        return RedirectResponse("/license-expired", 303)
    r.state.client = client
    return None


def guard_superadmin(r: Request):
    if not r.session.get("superadmin"):
        return RedirectResponse("/admin/login", 303)
    return None


def current_plan(client):
    plan_key = client["plan"] if client else "basic"
    return plan_key, PLANS.get(plan_key, PLANS["basic"])


def plan_limit_exceeded(client, resource: str, conn=None):
    """resource in {'products','labels','stores','users'}. Returns (bool exceeded, limit, current)."""
    _, plan = current_plan(client)
    limit = plan.get(f"max_{resource}")
    if limit is None:
        return False, None, None
    with use_conn(conn) as c:
        current = count_resource(client["id"], resource, c)
    return current >= limit, limit, current
