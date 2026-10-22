"""Central configuration, loaded from environment variables / .env."""
import os
from pathlib import Path

from cachelib.file import FileSystemCache
from dotenv import load_dotenv

load_dotenv()

# "entra" = real Microsoft sign-in.  "mock" = DEV/TEST ONLY: skips Entra ID and
# signs in a fabricated user (see mock_auth.py).
AUTH_MODE = os.getenv("AUTH_MODE", "entra").lower()
if AUTH_MODE not in ("entra", "mock"):
    raise RuntimeError("AUTH_MODE must be 'entra' or 'mock'")


def _env(name: str, mock_default: str | None = None) -> str:
    value = os.getenv(name)
    if value:
        return value
    if AUTH_MODE == "mock" and mock_default is not None:
        return mock_default
    raise RuntimeError(f"Missing required environment variable {name} (see .env.example)")


class Config:
    AUTH_MODE = AUTH_MODE

    # --- Flask ---
    SECRET_KEY = _env("FLASK_SECRET_KEY", "mock-mode-insecure-secret")

    # The sign-in flow state is written by one request (/login) and read by
    # another (/auth/redirect), and gunicorn may serve them from different
    # workers, so the store must be shared. Filesystem works for workers on a
    # single host; set REDIS_URL for multiple hosts/containers.
    if os.getenv("REDIS_URL"):
        import redis

        SESSION_TYPE = "redis"
        SESSION_REDIS = redis.from_url(os.environ["REDIS_URL"])
    else:
        SESSION_TYPE = "cachelib"
        SESSION_CACHELIB = FileSystemCache(
            os.getenv("SESSION_FILE_DIR", str(Path(__file__).parent / "flask_session")),
            threshold=500,
        )
    SESSION_PERMANENT = False
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"  # Lax is required so the cookie survives the redirect back from Microsoft

    # --- Entra ID / MSAL ---
    TENANT_ID = _env("AZURE_TENANT_ID", "00000000-0000-0000-0000-000000000000")
    CLIENT_ID = _env("AZURE_CLIENT_ID", "mock-client-id")
    CLIENT_SECRET = _env("AZURE_CLIENT_SECRET", "mock-client-secret")
    AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
    REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8050/auth/redirect")
    POST_LOGOUT_URI = os.getenv("POST_LOGOUT_URI", "http://localhost:8050/")

    # openid / profile / offline_access are added automatically by MSAL
    SCOPES = ["User.Read"]

    # --- Mock user (AUTH_MODE=mock only) ---
    MOCK_USER_NAME = os.getenv("MOCK_USER_NAME", "Mock User")
    MOCK_USER_EMAIL = os.getenv("MOCK_USER_EMAIL", "mock.user@contoso.example")
    MOCK_USER_OID = os.getenv("MOCK_USER_OID", "11111111-2222-3333-4444-555555555555")
    MOCK_USER_ROLES = [r.strip() for r in os.getenv("MOCK_USER_ROLES", "Dash.User").split(",") if r.strip()]

    # Number of reverse proxies in front of gunicorn (nginx, App Service, ingress...).
    # 0 = trust no X-Forwarded-* headers.
    PROXY_HOPS = int(os.getenv("PROXY_HOPS", "0"))
