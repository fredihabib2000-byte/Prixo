import hashlib
import os
import re
import secrets
import string


def hash_password(password: str) -> str:
    """Salted SHA-256. Good enough for a demo; swap for bcrypt/argon2 in production."""
    salt = os.getenv("PW_SALT", "prixo-static-salt-change-me")
    return hashlib.sha256((salt + password).encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "client"


def generate_license_key() -> str:
    groups = []
    for _ in range(4):
        groups.append("".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)))
    return "PRIXO-" + "-".join(groups)


def generate_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
