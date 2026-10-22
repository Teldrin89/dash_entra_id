"""Microsoft Graph access on behalf of the signed-in user."""
import requests
from flask import session

import mock_auth
from auth import get_access_token, is_mock


def get_me() -> tuple[int, dict]:
    """GET /me with the user's access token. Returns (http_status, json_body)."""
    token = get_access_token()
    if not token:
        return 401, {"error": "No valid token - reload the page to sign in again."}
    if is_mock():
        return 200, mock_auth.mock_graph_me(session["user"])
    resp = requests.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    return resp.status_code, (resp.json() if resp.content else {})
