import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Reads a local .env file if present (handy for development; in Docker the
# variables are passed in by docker-compose instead).
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ---- Database ----------------------------------------------------------
# Supabase connection string (Project Settings -> Database -> Connection string).
# Use the "Session pooler" string (port 5432) for a long-running server like this one.
DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-in-production")

# Credentials for the very first owner (superadmin) account. Only used when the
# superadmins table is empty, i.e. on the first start against a fresh database.
BOOTSTRAP_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "owner")
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme123")

# ---- License plans -----------------------------------------------------
# limits use None for "unlimited"
PLANS = {
    "basic": {
        "label": "Basic",
        "price_display": "$49/mo",
        "max_products": 500,
        "max_labels": 100,
        "max_stores": 1,
        "max_users": 3,
    },
    "pro": {
        "label": "Pro",
        "price_display": "$149/mo",
        "max_products": 5000,
        "max_labels": 1000,
        "max_stores": 5,
        "max_users": 10,
    },
    "enterprise": {
        "label": "Enterprise",
        "price_display": "Custom",
        "max_products": None,
        "max_labels": None,
        "max_stores": None,
        "max_users": None,
    },
}

DEFAULT_TRIAL_DAYS = 14
