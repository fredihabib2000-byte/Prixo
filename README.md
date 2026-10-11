# PRIXO ESL Manager — Licensed SaaS Edition

A multi-tenant, license-gated version of the PRIXO electronic-shelf-label manager, built
so you can sell it as a subscription to individual supermarkets.

## What's new vs. the single-store app you sent

- **One shared Supabase (PostgreSQL) database.** Every customer-owned row carries a `tenant_id`, and the
  foreign keys are composite, so one supermarket's data can never reference another's.
- **Central licensing tables** (`clients`, `superadmins`) that track every client: company
  name, plan, license key, status (active/suspended) and expiry date.
- **An owner console** at `/admin` (separate login from your customers) where *you* create
  new client accounts, pick a plan, set the license length, renew/suspend, and change plans.
- **Live license enforcement** — every page load for a tenant re-checks the central DB. If
  you suspend a client or their subscription expires, they're locked out immediately, mid-session.
- **Plan tiers with usage limits** (Basic / Pro / Enterprise) — product/label/store counts
  are capped per plan and enforced when a customer tries to add more.
- A redesigned dark UI (kept the original functionality: products, CSV import, ESL labels,
  gateways, stores, price-push workflow, REST API).

## Running it

1. Create a Supabase project, then copy **Project Settings → Database → Connection string → Session pooler**.
2. `cp .env.example .env` and fill in `DATABASE_URL`, `SESSION_SECRET`, `PW_SALT`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
3. Start it:

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

On first start the app creates all tables itself (it runs `schema.sql`; you can also paste that file
into the Supabase SQL editor) and creates the owner account from `ADMIN_USERNAME`/`ADMIN_PASSWORD`.
Check the connection at http://127.0.0.1:8000/api/health (`"database": "ok"`).

Open http://127.0.0.1:8000

- **Owner console:** http://127.0.0.1:8000/admin/login → the `ADMIN_USERNAME` / `ADMIN_PASSWORD` from your `.env`
- **Customer login:** http://127.0.0.1:8000/login (company code + username + password —
  you get these when you create a client in the owner console)

No demo client exists yet — create your first one from `/admin/clients/new`.

## Migrating existing data (from the old SQLite version)

Only needed if you already have customers in `data/central.db` + `data/tenants/*.db`.

```bash
python migrate_sqlite_to_supabase.py --sqlite-dir ./data --dry-run   # rehearsal: writes nothing
python migrate_sqlite_to_supabase.py --sqlite-dir ./data             # the real thing
```

It copies owners, clients/licenses and every tenant's users, stores, products, gateways, labels and
price history in a single transaction (all-or-nothing), re-numbers ids safely, and checks the row
counts afterwards. Re-running skips clients that already exist (`--replace` overwrites them).
Passwords keep working as long as `PW_SALT` is the **same value** you used with the SQLite version.
Customers must log in again once (sessions from the old version are invalidated).

## How selling a license works, end to end

1. You log in to `/admin`.
2. Click **New client**, fill in the supermarket's name, pick a plan (Basic/Pro/Enterprise),
   set how many days the license runs, and set an admin username/password for them.
3. The app provisions that supermarket's account (first store + admin user) and shows you a
   one-time page with their login code, username, password and license key — send that to
   your customer.
4. They log in at `/login` with the company code you gave them and start adding products,
   labels, gateways and stores — capped to their plan's limits.
5. Renewals: open their client page in `/admin`, add days, done. Non-payment: hit **Suspend**
   and they're locked out on their very next request.

## Plan limits

Defined in `config.py` (`PLANS` dict) — edit numbers/prices there:

| Plan | Products | Labels | Stores | Users |
|---|---|---|---|---|
| Basic | 500 | 100 | 1 | 3 |
| Pro | 5,000 | 1,000 | 5 | 10 |
| Enterprise | unlimited | unlimited | unlimited | unlimited |

## Project layout

```
main.py            FastAPI app, mounts routers + static files
config.py           Plan tiers, environment settings
db.py                Supabase/PostgreSQL connection pool
schema.sql           All tables, indexes, RLS lockdown (runs automatically at startup)
migrate_sqlite_to_supabase.py   One-off import from the old SQLite files
templating.py        Shared Jinja2 setup + date filters
security.py         Password hashing, license key generation
central_db.py        Superadmins + clients/licenses
tenant_db.py         Tenant helpers (counts, users, default store)
deps.py              Session guards + license/plan-limit checks
routers/
  auth.py            Customer login/logout
  admin.py            Owner console (create/manage clients & licenses)
  dashboard.py         Customer dashboard
  products.py, labels.py, gateways.py, stores.py   Feature pages
  api.py               REST API (/api/health, /api/price)
templates/            Jinja2 HTML templates
static/css/style.css  Styling
```

## Before you sell this to real customers

- Change `SESSION_SECRET` and the `PW_SALT` env var to long random values, and change the
  default owner password immediately.
- Swap the SHA-256 password hashing in `security.py` for bcrypt or argon2
  (`pip install passlib[bcrypt]`).
- Put this behind HTTPS (e.g. a reverse proxy like Caddy or nginx with Let's Encrypt).
- Data is in Supabase/PostgreSQL. Turn on backups (Project Settings → Database → Backups), and keep the
  database password and `.env` out of git. Row Level Security is enabled on every table with no
  policies, so the tables are unreachable through Supabase's public API — the app talks to the
  database directly with your connection string.
- The `FakeGateway.push_price()` in `products.py`/`api.py`/`labels.py` simulates hardware
  communication — replace it with your real ESL vendor's SDK/API when you pick one.
- Add real payment collection (Stripe Billing/Checkout) that calls `extend_license()` on
  successful payment and `set_client_status(..., "suspended")` on failed/cancelled payment,
  instead of doing renewals by hand in the owner console.
- Consider rate-limiting `/login` and `/admin/login` and adding audit logs for admin actions.
