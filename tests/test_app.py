"""Tests run without contacting Microsoft.

* mock mode      - AUTH_MODE=mock, /login signs in a fabricated user
* entra mode     - the REAL /auth/redirect, token-refresh and Graph code, with the
                   MSAL client and `requests` replaced by fakes that return what
                   Entra / Graph would return
"""
import os
import subprocess
import sys

import pytest

import auth
import graph
import mock_auth
from conftest import ROOT

GRAPH_CLICK = {
    "output": "graph-api-output.children",
    "outputs": {"id": "graph-api-output", "property": "children"},
    "inputs": [{"id": "graph-api-button", "property": "n_clicks", "value": 1}],
    "changedPropIds": ["graph-api-button.n_clicks"],
}


def graph_text(resp):
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["response"]["graph-api-output"]["children"]


def user_in_session(client):
    with client.session_transaction() as s:
        return s.get("user")


# ------------------------------------------------------------------ mock mode
@pytest.fixture
def mock_client(make_app):
    return make_app(AUTH_MODE="mock").server.test_client()


def test_anonymous_is_redirected_to_login(mock_client):
    r = mock_client.get("/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_anonymous_dash_requests_get_401(mock_client):
    assert mock_client.get("/_dash-layout").status_code == 401
    assert mock_client.post("/_dash-update-component", json={}).status_code == 401


def test_healthz_is_public(mock_client):
    assert mock_client.get("/healthz").get_json() == {"status": "ok"}


def test_mock_login_creates_session_from_msal_shaped_result(mock_client):
    r = mock_client.get("/login")
    assert r.status_code == 302 and r.headers["Location"] == "/"
    claims = user_in_session(mock_client)
    for key in ("aud", "iss", "exp", "name", "preferred_username", "oid", "tid", "roles"):
        assert key in claims
    assert claims["name"] == "Mock User"
    assert claims["roles"] == ["Dash.User"]


def test_login_returns_to_originally_requested_page(mock_client):
    mock_client.get("/?tab=2")
    assert mock_client.get("/login").headers["Location"] == "/?tab=2"


def test_page_and_layout_show_signed_in_user_and_mock_banner(mock_client):
    mock_client.get("/login")
    assert mock_client.get("/").status_code == 200
    layout = mock_client.get("/_dash-layout").get_data(as_text=True)
    assert "Mock User" in layout and "mock.user@contoso.example" in layout
    assert "MOCK AUTH MODE" in layout


def test_mock_user_is_configurable(make_app):
    c = make_app(
        AUTH_MODE="mock", MOCK_USER_NAME="Ada Lovelace",
        MOCK_USER_EMAIL="ada@corp.example", MOCK_USER_ROLES=["Admin", "Reader"],
    ).server.test_client()
    c.get("/login")
    claims = user_in_session(c)
    assert (claims["name"], claims["roles"]) == ("Ada Lovelace", ["Admin", "Reader"])


def test_chart_callback_works_when_signed_in(mock_client):
    mock_client.get("/login")
    r = mock_client.post("/_dash-update-component", json={
        "output": "life-exp-graph.figure",
        "outputs": {"id": "life-exp-graph", "property": "figure"},
        "inputs": [{"id": "country-dropdown", "property": "value", "value": ["Poland"]}],
        "changedPropIds": ["country-dropdown.value"],
    })
    assert r.status_code == 200 and "Poland" in r.get_data(as_text=True)


def test_graph_button_returns_canned_me_in_mock_mode(mock_client):
    mock_client.get("/login")
    text = graph_text(mock_client.post("/_dash-update-component", json=GRAPH_CLICK))
    assert text.startswith("HTTP 200") and "mock.user@contoso.example" in text


def test_logout_clears_session(mock_client):
    mock_client.get("/login")
    r = mock_client.get("/logout")
    assert r.status_code == 302 and r.headers["Location"].endswith("/signed-out")
    assert user_in_session(mock_client) is None
    assert mock_client.get("/").headers["Location"].endswith("/login")
    assert mock_client.get("/signed-out").status_code == 200


def test_open_redirect_via_double_slash_is_blocked(mock_client):
    mock_client.get("//evil.example/path")
    assert mock_client.get("/login").headers["Location"] == "/"


def test_mock_mode_refuses_to_start_with_secure_cookies(make_app):
    with pytest.raises(RuntimeError, match="must not be combined"):
        make_app(AUTH_MODE="mock", SESSION_COOKIE_SECURE=True)


def test_mock_mode_needs_no_azure_env_vars(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AZURE_", "FLASK_"))}
    env.update(AUTH_MODE="mock", SESSION_FILE_DIR=str(tmp_path))
    code = (
        "from app import server; c = server.test_client();"
        "print(c.get('/login').status_code, c.get('/').status_code)"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                         capture_output=True, text=True)
    assert out.stdout.strip() == "302 200", out.stderr


def test_entra_mode_requires_azure_env_vars(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AZURE_", "FLASK_", "AUTH_MODE"))}
    env["SESSION_FILE_DIR"] = str(tmp_path)
    out = subprocess.run([sys.executable, "-c", "import app"], cwd=ROOT, env=env,
                         capture_output=True, text=True)
    assert out.returncode != 0 and "Missing required environment variable" in out.stderr


# ------------------------------------------- entra mode, real code paths, fake MSAL
class FakeMsal:
    """Stands in for msal.ConfidentialClientApplication."""

    def __init__(self, auth_result=None, raises=None, silent_token="silent-access-token"):
        self.auth_result, self.raises, self.silent_token = auth_result, raises, silent_token
        self.received = None

    def acquire_token_by_auth_code_flow(self, flow, auth_response):
        self.received = (flow, dict(auth_response))
        if self.raises:
            raise self.raises
        return self.auth_result

    def get_accounts(self):
        return [{"home_account_id": "oid.tid"}]

    def acquire_token_silent(self, scopes, account):
        return {"access_token": self.silent_token} if self.silent_token else None


@pytest.fixture
def entra(make_app, monkeypatch):
    app = make_app()  # default AUTH_MODE=entra
    fake = FakeMsal(auth_result=mock_auth.build_mock_auth_result(app.server.config))
    monkeypatch.setattr(auth, "_msal_app", lambda cache=None: fake)
    return app.server.test_client(), fake


def arm_flow(client, next_url=None):
    with client.session_transaction() as s:
        s["flow"] = {"state": "s", "auth_uri": "https://login.example"}
        if next_url:
            s["next"] = next_url


def test_redirect_route_exchanges_code_and_signs_in(entra):
    client, fake = entra
    arm_flow(client, next_url="/?from=deeplink")
    r = client.get("/auth/redirect?code=AUTHCODE&state=s")
    assert r.status_code == 302 and r.headers["Location"] == "/?from=deeplink"
    assert fake.received[1] == {"code": "AUTHCODE", "state": "s"}
    assert user_in_session(client)["name"] == "Mock User"
    assert client.get("/").status_code == 200


def test_redirect_route_reports_entra_errors(entra):
    client, fake = entra
    fake.auth_result = {"error": "invalid_grant", "error_description": "AADSTS70008: code expired"}
    arm_flow(client)
    r = client.get("/auth/redirect?code=old&state=s")
    assert r.status_code == 401 and "AADSTS70008" in r.get_data(as_text=True)
    assert user_in_session(client) is None


def test_redirect_route_state_mismatch_restarts_login(entra):
    client, fake = entra
    fake.raises = ValueError("state mismatch")
    arm_flow(client)
    r = client.get("/auth/redirect?code=x&state=forged")
    assert r.headers["Location"].endswith("/login") and user_in_session(client) is None


def test_redirect_route_without_flow_restarts_login(entra):
    client, _ = entra
    assert client.get("/auth/redirect?code=x").headers["Location"].endswith("/login")


def test_graph_call_uses_silent_token_and_real_graph_path(entra, monkeypatch):
    client, fake = entra
    arm_flow(client)
    client.get("/auth/redirect?code=c&state=s")

    seen = {}

    class FakeResp:
        status_code, content = 200, b"{}"
        def json(self): return {"displayName": "Real Graph User"}

    def fake_get(url, headers, timeout):
        seen.update(url=url, auth=headers["Authorization"])
        return FakeResp()

    monkeypatch.setattr(graph.requests, "get", fake_get)
    text = graph_text(client.post("/_dash-update-component", json=GRAPH_CLICK))
    assert "Real Graph User" in text
    assert seen == {"url": "https://graph.microsoft.com/v1.0/me", "auth": "Bearer silent-access-token"}


def test_graph_call_without_refreshable_token_asks_to_sign_in_again(entra):
    client, fake = entra
    arm_flow(client)
    client.get("/auth/redirect?code=c&state=s")
    fake.silent_token = None
    assert graph_text(client.post("/_dash-update-component", json=GRAPH_CLICK)).startswith("HTTP 401")


def test_entra_mode_has_no_mock_login_or_signed_out_page(entra):
    client, _ = entra
    assert client.get("/signed-out").status_code == 404
