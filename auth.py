# auth.py - the auth module shared by every AfyaPlus service:
# password hashing, token creation, and the current_user / require_role doormen.
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import APP_ENV, get_logger

log = get_logger("auth", "auth.log")

ALGORITHM = "HS256"
ISSUER = "afyaplus-platform"
TOKEN_MINUTES = 30

_DEV_ONLY_SECRET = "dev-only-secret-never-use-in-production-0000"
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    if APP_ENV == "production":
        # A default secret lives in Git, so anyone could sign tokens: refuse to boot.
        raise RuntimeError("JWT_SECRET is not set. Inject it at runtime with --env-file.")
    log.warning("JWT_SECRET not set: using the dev-only default (never in production)")
    JWT_SECRET = _DEV_ONLY_SECRET

# Only bcrypt hashes live here, never passwords. Demo credentials are in the README.
USERS = {
    "mercy": {"password_hash": "$2b$12$Ux5hVLI7NaH7kfRIcYjBUujTgR8OaKHMtBFcaTLUacoC0sZYddUwC",
              "role": "coordinator"},
    "guest": {"password_hash": "$2b$12$zaNC1fbtkITkh2bx5ns4eejT0/EDGWmmRxAAcZMc2Aa7rCn5BNnb2",
              "role": "viewer"},
}
# Checked for unknown usernames so a wrong name costs the same time as a wrong password.
_DUMMY_HASH = b"$2b$12$S4Abn8hk37yF.898FmdtUeXK3iyOibuHSv8I/QjGCF12xP4jsRpuO"

_bearer = HTTPBearer(auto_error=False)


def check_password(username: str, password: str) -> bool:
    """True if the password matches the stored bcrypt hash for this user."""
    user = USERS.get(username)
    stored = user["password_hash"].encode() if user else _DUMMY_HASH
    ok = bcrypt.checkpw(password.encode(), stored)
    return ok and user is not None


def create_token(username: str) -> str:
    """Sign a short-lived JWT carrying the username (sub) and role."""
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "role": USERS[username]["role"], "iss": ISSUER,
               "iat": now, "exp": now + timedelta(minutes=TOKEN_MINUTES)}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail,
                         headers={"WWW-Authenticate": "Bearer"})


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    """401 unless the request carries a valid, unexpired bearer token.
    Returns the verified payload: {"sub": ..., "role": ...}."""
    if creds is None:
        raise _unauthorized("Not authenticated. Log in at /token and send 'Authorization: Bearer <token>'.")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[ALGORITHM],
                             issuer=ISSUER, options={"require": ["exp", "sub", "role"]})
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired. Log in again at /token.")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token.")
    return payload


def require_role(*roles: str):
    """Dependency factory: 401 if not logged in, 403 if logged in with the wrong role."""
    def checker(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            log.warning("forbidden user=%s role=%s needed=%s", user["sub"], user["role"], roles)
            raise HTTPException(status_code=403,
                                detail=f"Your role '{user['role']}' may not use this endpoint.")
        return user
    return checker
