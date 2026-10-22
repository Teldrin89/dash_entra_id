"""Fabricated Entra ID responses for local development and tests (AUTH_MODE=mock).

`build_mock_auth_result` returns a dict shaped like what
``msal.ConfidentialClientApplication.acquire_token_by_auth_code_flow`` returns on
success - i.e. what the *last* call of the Entra sign-in dance yields - so the
app's post-login code runs unchanged without touching Microsoft.
"""
import time
from collections.abc import Mapping

MOCK_ACCESS_TOKEN = "mock-access-token-not-a-real-jwt"


def build_mock_auth_result(cfg: Mapping) -> dict:
    now = int(time.time())
    tenant, oid = cfg["TENANT_ID"], cfg["MOCK_USER_OID"]
    claims = {
        "aud": cfg["CLIENT_ID"],
        "iss": f"https://login.microsoftonline.com/{tenant}/v2.0",
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
        "name": cfg["MOCK_USER_NAME"],
        "preferred_username": cfg["MOCK_USER_EMAIL"],
        "oid": oid,
        "sub": f"mock-sub-{oid}",
        "tid": tenant,
        "ver": "2.0",
        "roles": list(cfg["MOCK_USER_ROLES"]),
    }
    return {
        "token_type": "Bearer",
        "scope": ["User.Read", "openid", "profile"],
        "expires_in": 3599,
        "access_token": MOCK_ACCESS_TOKEN,
        "refresh_token": "mock-refresh-token",
        "id_token": "mock.id.token",
        "id_token_claims": claims,
        "client_info": {"uid": oid, "utid": tenant},
    }


def mock_graph_me(claims: Mapping) -> dict:
    """Canned stand-in for GET https://graph.microsoft.com/v1.0/me."""
    return {
        "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users/$entity",
        "id": claims["oid"],
        "displayName": claims["name"],
        "userPrincipalName": claims["preferred_username"],
        "mail": claims["preferred_username"],
        "_mock": True,
    }
