# Flask + Dash with Entra ID (MSAL)

```
app.py         entry point, builds Flask + Dash, installs the auth guard
auth.py        MSAL auth-code flow (PKCE), /login /auth/redirect /logout, token helper
mock_auth.py   fabricated MSAL result + Graph response for AUTH_MODE=mock
graph.py       Microsoft Graph call using the user's token
tests/         pytest suite (no network)
layout.py      Dash layout (function, reads the signed-in user)
callbacks.py   Dash callbacks (chart + Microsoft Graph call using the user's token)
ids.py         component ids shared by layout and callbacks
config.py      env-based settings
```

## How MSAL is used
Sign-in is not a single call: the user must authenticate on Microsoft's site, so the app makes
two MSAL calls with a browser redirect in between (all in `auth.py`). A third call is used later
to obtain tokens for APIs. `ConfidentialClientApplication` is created per request in `_msal_app()`;
all state lives in the Flask session, not in the MSAL object.

```
Browser                         Flask app (auth.py)                        Microsoft Entra
  │ GET /  (no session)               │                                          │
  │──────────────────────────────────>│ require_login() -> 302 /login            │
  │ GET /login                        │                                          │
  │──────────────────────────────────>│ (1) initiate_auth_code_flow()            │
  │                                   │     builds the sign-in URL + state,      │
  │                                   │     nonce, PKCE verifier -> session["flow"]
  │<── 302 to login.microsoftonline.com ─────────────────────────────────────────│
  │ user signs in (password / MFA) ─────────────────────────────────────────────>│
  │<── 302 to /auth/redirect?code=...&state=... ─────────────────────────────────│
  │ GET /auth/redirect?code=...       │                                          │
  │──────────────────────────────────>│ (2) acquire_token_by_auth_code_flow()    │
  │                                   │     POSTs code + client secret + PKCE    │
  │                                   │     verifier to the token endpoint       │
  │                                   │<── id_token, access_token, refresh_token │
  │                                   │     MSAL validates the ID token          │
  │                                   │     session["user"] = id_token_claims    │
  │<── 302 to the original page, Set-Cookie: session id                          │
```

| Step | MSAL call | Where | What it does |
|------|-----------|-------|--------------|
| 1 | `initiate_auth_code_flow(scopes, redirect_uri)` | `login()` | Returns a dict with `auth_uri` (where to send the user) plus `state`, `nonce` and the PKCE verifier. Stored in `session["flow"]`. |
| 2 | `acquire_token_by_auth_code_flow(flow, request.args)` | `authorized()` | Checks `state` against the stored flow (CSRF protection; raises `ValueError` on mismatch), exchanges the one-time `code` for tokens, and validates the ID token (signature, issuer, audience, nonce, expiry). On success the result contains `id_token_claims` (`name`, `preferred_username`, `oid`, `tid`, `roles`, ...); on failure it contains `error` / `error_description`. |
| 3 | `acquire_token_silent(scopes, account)` | `get_access_token()` | Returns a cached access token, or uses the refresh token to get a new one. Called from Dash callbacks (see `graph.py`) when the app needs to call Microsoft Graph as the user. |

**What is stored where**
- **Browser cookie:** only an opaque session id. It holds no user data and no tokens.
- **`session["user"]`** (server-side): the decoded ID-token claims. After sign-in, "is the user logged in?" is just `"user" in session`, and no further request goes to Microsoft.
- **`session["token_cache"]`** (server-side): MSAL's `SerializableTokenCache` (access + refresh tokens), loaded and saved around each MSAL call by `_load_cache()` / `_save_cache()`.
- **`session["flow"]`** and **`session["next"]`**: temporary, used only during sign-in (the flow state, and the page the user originally requested).

Server-side sessions (Flask-Session) are used because the token cache is too large for Flask's default
4 KB cookie session and because tokens should not be sent to the browser. They must be shared by all
gunicorn workers (see "Run with gunicorn").

**Protecting Dash:** Dash runs on the Flask server, so `auth.require_login` is registered as a global
`before_request` hook in `app.py`. It covers the page, Dash's layout/dependency endpoints and every
callback request. Anonymous page requests are redirected to `/login`; anonymous Dash XHR requests get a
`401` (they can't follow a redirect to Microsoft).

**Sign-out:** `/logout` clears the session and redirects to Entra's `/oauth2/v2.0/logout` endpoint with
`post_logout_redirect_uri`, which ends the Microsoft session too.

**Relationship to mock mode and tests:** steps 1 and 2 are the only parts that talk to Microsoft.
Everything after step 2 happens in `_complete_sign_in(result)`, which takes MSAL's result dict. Mock mode
and the tests feed that function the same dict shape, so the session handling is exercised without
Microsoft.

## Testing without Entra ID
**Mock mode** (manual testing in a browser, no Azure needed):
```bash
AUTH_MODE=mock python app.py          # or: AUTH_MODE=mock gunicorn -c gunicorn.conf.py app:server
```
`/login` skips Microsoft and feeds a fabricated MSAL result (`mock_auth.py`, same shape as the
return value of `acquire_token_by_auth_code_flow`) into the same `_complete_sign_in()` the real
`/auth/redirect` uses. A yellow banner is shown, and the Graph button returns a canned `/me`.
Customize the user with `MOCK_USER_NAME`, `MOCK_USER_EMAIL`, `MOCK_USER_ROLES`.
The app refuses to start in mock mode with `SESSION_COOKIE_SECURE=1`, as a guard against deploying it.

**Automated tests** (`pip install -r requirements-dev.txt && pytest`): cover mock mode, and the
*real* `/auth/redirect`, silent-token and Graph code paths with the MSAL client and `requests`
replaced by fakes returning what Entra / Graph would return.

Neither replaces a run against a real tenant: they don't verify your app registration, redirect URI
or real token contents (use `check_entra.py` and a real sign-in for that).

## Entra ID setup
1. Entra admin center -> App registrations -> New registration (single tenant is simplest).
2. Authentication -> Add platform -> **Web** -> redirect URI `http://localhost:8050/auth/redirect`.
3. Certificates & secrets -> New client secret -> copy the **Value** (not the ID).
4. Copy Directory (tenant) ID and Application (client) ID.
5. API permissions: `User.Read` (delegated) is there by default.

## Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill it in
python app.py          # http://localhost:8050
```

## Verify your Entra registration (no browser needed)
```bash
python check_entra.py
```
Checks the tenant, the client id/secret and the redirect URI wiring, then prints the sign-in URL.

## Run with gunicorn
```bash
pip install -r requirements.txt
gunicorn -c gunicorn.conf.py app:server
```
Gunicorn is Linux/macOS only (use WSL or a container on Windows). Tuning is via env vars
(`WEB_CONCURRENCY`, `GUNICORN_THREADS`, `BIND`, `LOG_LEVEL`, ...).

Behind nginx / App Service / an ingress terminating TLS:
```bash
PROXY_HOPS=1 FORWARDED_ALLOW_IPS=<proxy ip> SESSION_COOKIE_SECURE=1 \
REDIRECT_URI=https://your.host/auth/redirect POST_LOGOUT_URI=https://your.host/ \
gunicorn -c gunicorn.conf.py app:server
```
and add `https://your.host/auth/redirect` as a Web redirect URI in Entra.
The proxy must forward `X-Forwarded-Proto` and `X-Forwarded-Host`.

- `/healthz` is public, for load-balancer probes.
- Sessions (including the sign-in flow state) must be shared by all workers: the default
  filesystem store works for workers on one host; set `REDIS_URL` for several hosts/containers.
- Prefer a certificate over a client secret for `client_credential`.
- For authorization beyond "is signed in", check `roles` / `groups` in `session["user"]`.
