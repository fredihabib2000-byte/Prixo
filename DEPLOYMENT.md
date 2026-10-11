# Going live at www.prixo.com — step by step

Your app is code sitting on your computer right now. To turn it into "www.prixo.com" you need
three separate things: a **domain name**, a **server to run the code 24/7**, and **DNS pointing
the domain at that server**. I've added the files (`Dockerfile`, `docker-compose.yml`,
`Caddyfile`) to this project to make the server part a 10-minute job.

## 1. Buy the domain
Buy `prixo.com` (or whatever name you want) from any registrar — Namecheap, Google Domains,
GoDaddy, OVH. Costs ~$10-15/year.

## 2. Rent a small server (VPS)
You need a machine that's always on. Cheapest reliable options:
- **DigitalOcean** — $6-12/mo droplet, very beginner-friendly
- **Hetzner** — cheapest in Europe/EU-adjacent regions
- **Railway / Render** — even easier (git push to deploy), slightly more per active hour but
  zero server admin

Pick DigitalOcean/Hetzner if you want full control (recommended since you'll be running
a small always-on app server (the database itself now lives in Supabase)). Create an Ubuntu 22.04/24.04 droplet.

## 3. Point the domain at the server
In your registrar's DNS settings, add:
- an **A record**: `www` → your server's IP address
- an **A record**: `@` (root) → your server's IP address

DNS can take a few minutes to a few hours to propagate.

## 4. Install Docker on the server
SSH into the droplet, then:
```bash
curl -fsSL https://get.docker.com | sh
```

## 5. Copy your project to the server and set secrets
```bash
scp -r prixo/ root@YOUR_SERVER_IP:/root/
ssh root@YOUR_SERVER_IP
cd prixo
cat > .env <<EOF
DATABASE_URL=postgresql://postgres.YOUR_REF:YOUR_PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres
SESSION_SECRET=$(openssl rand -hex 32)
PW_SALT=$(openssl rand -hex 32)
ADMIN_USERNAME=owner
ADMIN_PASSWORD=choose-a-strong-password
EOF
```
`DATABASE_URL` comes from Supabase: **Project Settings → Database → Connection string → Session pooler**
(see `.env.example`). The app creates all its tables automatically the first time it starts, and
creates the owner account from `ADMIN_USERNAME` / `ADMIN_PASSWORD`.

> Coming from the old SQLite version? Run the one-time data migration first — see **README.md →
> Migrating existing data**.

## 6. Edit the Caddyfile
Already set to `www.prixo.com` — change to your real domain if different.

## 7. Launch it
```bash
docker compose up -d --build
```
Caddy automatically requests a free HTTPS certificate (Let's Encrypt) for your domain the
first time it starts — no manual cert setup needed.

That's it — `https://www.prixo.com` is now live, and `https://www.prixo.com/admin/login` is
your owner console (log in with the `ADMIN_USERNAME` / `ADMIN_PASSWORD` you put in `.env`).

## 8. Before real customers touch it
- Make sure `ADMIN_PASSWORD` in `.env` is NOT the default `changeme123`.
- `SESSION_SECRET` and `PW_SALT` are now real random values (step 5) — don't skip this,
  it's what keeps sessions and password hashes secure.
- Swap the SHA-256 password hashing in `security.py` for bcrypt/argon2.
- Backups: Supabase takes daily backups on paid plans (Project Settings → Database → Backups). On the free plan, schedule your own `pg_dump`.
- Add Stripe billing so renewals don't have to be done by hand.

## How user access actually works (already built into the app)
- **You** log in at `/admin` — this is where *you* create a new supermarket account, pick a
  plan, and set the license length.
- Creating a client generates a **company code + admin username + password** for that
  supermarket — you hand that to them once, on a one-time confirmation screen.
- **Your customer** (the supermarket) logs in at `/login` with that company code. From inside
  their own dashboard they add their own staff/users (up to their plan's user limit), add
  products, and manage their store(s) — completely isolated from every other client's data
  (every row is tagged with the customer's `tenant_id` and every query is scoped by it).

No extra work needed here — it's already wired up. Once deployed, `www.prixo.com/admin` is you,
`www.prixo.com/login` is every customer.
