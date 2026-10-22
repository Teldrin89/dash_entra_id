"""Entry point: wires Flask (auth + sessions) to Dash (layout + callbacks).

Production:  gunicorn -c gunicorn.conf.py app:server
Development: python app.py              (AUTH_MODE=mock python app.py to skip Entra)
"""
import logging

from dash import Dash
from flask import Flask
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix

import auth
from callbacks import register_callbacks
from config import Config
from layout import serve_layout

log = logging.getLogger(__name__)


def create_app(config_overrides: dict | None = None) -> Dash:
    server = Flask(__name__)
    server.config.from_object(Config)
    server.config.update(config_overrides or {})  # used by the test-suite

    if server.config["AUTH_MODE"] == "mock":
        if server.config["SESSION_COOKIE_SECURE"]:
            raise RuntimeError(
                "AUTH_MODE=mock bypasses authentication and must not be combined "
                "with SESSION_COOKIE_SECURE=1 (production)."
            )
        log.warning("AUTH_MODE=mock: Entra ID is BYPASSED. Do not use in production.")

    # Behind a TLS-terminating proxy, make Flask see the public scheme/host
    # (request.is_secure, request.url_root, url_for(_external=True)) instead of
    # the internal http://127.0.0.1:8050 that gunicorn receives.
    hops = server.config["PROXY_HOPS"]
    if hops:
        server.wsgi_app = ProxyFix(
            server.wsgi_app, x_for=hops, x_proto=hops, x_host=hops, x_prefix=hops
        )

    Session(server)

    server.register_blueprint(auth.bp)
    server.before_request(auth.require_login)  # gates Dash too

    @server.get("/healthz")
    def healthz():
        return {"status": "ok"}

    app = Dash(__name__, server=server, title="Dash + Entra ID")
    app.layout = serve_layout          # function -> evaluated per request
    register_callbacks(app)
    return app


app = create_app()
server = app.server  # gunicorn target: app:server

if __name__ == "__main__":
    app.run(debug=True, port=8050)
