"""Preflight check for your Entra app registration - run this on a machine with
internet access before starting the app:

    python check_entra.py

It verifies, without needing a browser:
  1. the tenant exists and its OIDC metadata is reachable,
  2. the client id + secret are accepted (client-credentials grant),
  3. MSAL can build the sign-in URL with your redirect URI.
Then it prints the URL so you can confirm the redirect URI is registered
(Entra shows AADSTS50011 in the browser if it is not).
"""
import sys

import msal
import requests

from config import Config as C


def step(msg):
    print(f"\n==> {msg}")


step("Tenant OIDC metadata")
r = requests.get(f"{C.AUTHORITY}/v2.0/.well-known/openid-configuration", timeout=10)
if not r.ok:
    sys.exit(f"FAILED ({r.status_code}): check AZURE_TENANT_ID")
print("OK  issuer:", r.json()["issuer"])

step("Client id / secret (client-credentials grant)")
app = msal.ConfidentialClientApplication(
    C.CLIENT_ID, authority=C.AUTHORITY, client_credential=C.CLIENT_SECRET
)
res = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
if "access_token" not in res:
    sys.exit(f"FAILED: {res.get('error')}: {res.get('error_description')}\n"
             "(AADSTS7000215 = wrong secret: use the secret VALUE, not its ID)")
print("OK  secret accepted")

step("Authorization URL")
flow = app.initiate_auth_code_flow(C.SCOPES, redirect_uri=C.REDIRECT_URI)
print("OK  redirect_uri:", C.REDIRECT_URI)
print("Open this in a browser; you should reach the Microsoft sign-in page,")
print("not an AADSTS50011 redirect-URI error:\n")
print(flow["auth_uri"])
