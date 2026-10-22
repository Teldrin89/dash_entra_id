"""Entra ID authentication (MSAL auth-code flow + PKCE) as a Flask blueprint.

Dash runs on top of this Flask server, so protecting Flask protects Dash:
`require_login` is registered as a global before_request hook in app.py and
covers the page, the layout/dependency endpoints and every callback request.

With AUTH_MODE=mock the Microsoft round-trip is skipped: /login feeds a
fabricated MSAL result (mock_auth.py) into the same `_complete_sign_in` that the
real /auth/redirect uses.
"""
from urllib.parse import urlencode

import msal
from flask import (
    Blueprint, abort, current_app, jsonify, redirect, request, session, url_for,
)

import mock_auth

bp = Blueprint("auth", __name__)

# Endpoints reachable without signing in (load-balancer health checks).
PUBLIC_ENDPOINTS = {"healthz"}


def is_mock() -> bool:
    return current_app.config["AUTH_MODE"] == "mock"


# ---------------------------------------------------------------- MSAL helpers
def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if session.get("token_cache"):
        cache.deserialize(session["token_cache"])
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        session["token_cache"] = cache.serialize()


def _msal_app(cache: msal.SerializableTokenCache | None = None):
    cfg = current_app.config
    return msal.ConfidentialClientApplication(
        cfg["CLIENT_ID"],
        authority=cfg["AUTHORITY"],
        client_credential=cfg["CLIENT_SECRET"],
        token_cache=cache,
    )


def get_access_token(scopes: list[str] | None = None) -> str | None:
    """Return a (cached or silently refreshed) access token for the signed-in user.

    Usable from Dash callbacks, since they are ordinary Flask requests.
    """
    if "user" not in session:
        return None
    if is_mock():
        return mock_auth.MOCK_ACCESS_TOKEN
    cache = _load_cache()
    app = _msal_app(cache)
    accounts = app.get_accounts()
    if not accounts:
        return None
    result = app.acquire_token_silent(
        scopes or current_app.config["SCOPES"], account=accounts[0]
    )
    _save_cache(cache)
    return result.get("access_token") if result else None


# ----------------------------------------------------------------- Route guard
def _is_safe_next(path: str) -> bool:
    """Only same-site absolute paths; '//evil.com' would be an open redirect."""
    return path.startswith("/") and not path.startswith(("//", "/\\"))


def require_login():
    """before_request hook: everything except the auth routes needs a session."""
    if request.blueprint == "auth" or request.endpoint in PUBLIC_ENDPOINTS or "user" in session:
        return None

    # Dash's XHR endpoints (/_dash-update-component, ...) can't follow a
    # redirect to Microsoft; answer with 401 and let the user reload the page.
    if request.path.startswith("/_dash-") or request.method != "GET":
        return jsonify(error="unauthenticated"), 401

    target = request.full_path.rstrip("?")
    session["next"] = target if _is_safe_next(target) else "/"
    return redirect(url_for("auth.login"))


# ------------------------------------------------------------------ Sign-in end
def _complete_sign_in(result: dict, cache: msal.SerializableTokenCache | None = None):
    """Final step of sign-in, shared by the real and the mock path.

    `result` is the dict MSAL returns from acquire_token_by_auth_code_flow.
    """
    if "error" in result:
        return (
            f"Sign-in failed: {result.get('error')} - {result.get('error_description')}",
            401,
        )
    next_url = session.pop("next", "/")
    session["user"] = result["id_token_claims"]
    if cache is not None:
        _save_cache(cache)
    return redirect(next_url if _is_safe_next(next_url) else "/")


# ---------------------------------------------------------------------- Routes
@bp.route("/login")
def login():
    if is_mock():
        return _complete_sign_in(mock_auth.build_mock_auth_result(current_app.config))

    cfg = current_app.config
    flow = _msal_app().initiate_auth_code_flow(
        cfg["SCOPES"], redirect_uri=cfg["REDIRECT_URI"]
    )
    session["flow"] = flow  # contains state, nonce and PKCE verifier
    return redirect(flow["auth_uri"])


@bp.route("/auth/redirect")
def authorized():
    flow = session.pop("flow", None)
    if not flow:
        return redirect(url_for("auth.login"))

    cache = _load_cache()
    try:
        result = _msal_app(cache).acquire_token_by_auth_code_flow(flow, request.args)
    except ValueError:  # state mismatch / CSRF
        return redirect(url_for("auth.login"))
    return _complete_sign_in(result, cache)


@bp.route("/logout")
def logout():
    cfg = current_app.config
    session.clear()
    if is_mock():
        return redirect(url_for("auth.signed_out"))
    query = urlencode({"post_logout_redirect_uri": cfg["POST_LOGOUT_URI"]})
    return redirect(f"{cfg['AUTHORITY']}/oauth2/v2.0/logout?{query}")


@bp.route("/signed-out")
def signed_out():
    """Mock-mode landing page (otherwise / would instantly sign the mock user back in)."""
    if not is_mock():
        abort(404)
    return "<p>Signed out (mock mode).</p><p><a href='/login'>Sign in again</a></p>"
