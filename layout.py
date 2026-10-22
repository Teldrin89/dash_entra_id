"""Dash layout only - no callbacks here."""
import json

from dash import dcc, html
from flask import current_app, has_request_context, session

import ids

COUNTRIES = ["Poland", "Germany", "France", "United States", "Japan", "Brazil"]


def serve_layout():
    """Assigned to `app.layout` as a function, so it is re-evaluated on every
    page load and can read the signed-in user from the Flask session."""
    in_request = has_request_context()
    user = session.get("user", {}) if in_request else {}
    mock = in_request and current_app.config["AUTH_MODE"] == "mock"
    name = user.get("name", "Unknown user")
    username = user.get("preferred_username", "")

    return html.Div(
        style={"fontFamily": "system-ui, sans-serif", "maxWidth": "900px", "margin": "0 auto", "padding": "1rem"},
        children=[
            html.Div(
                "MOCK AUTH MODE - Entra ID is bypassed. Development/testing only.",
                style={"background": "#ffe08a", "padding": "0.5rem 1rem", "fontWeight": "bold", "marginBottom": "1rem"},
            ) if mock else None,
            html.Div(
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"},
                children=[
                    html.H2("Dash + Entra ID"),
                    html.Div(
                        [
                            html.Strong(name),
                            html.Span(f" ({username})", style={"color": "#666"}),
                            html.Span(" · "),
                            # plain anchor -> full-page navigation to the Flask route
                            html.A("Sign out", href="/logout"),
                        ]
                    ),
                ],
            ),
            html.Details(
                [
                    html.Summary("ID token claims stored in the session"),
                    html.Pre(json.dumps(user, indent=2, default=str)),
                ]
            ),
            html.Hr(),
            html.H4("Protected chart"),
            dcc.Dropdown(
                id=ids.COUNTRY_DROPDOWN,
                options=COUNTRIES,
                value=["Poland", "Germany"],
                multi=True,
            ),
            dcc.Graph(id=ids.GRAPH),
            html.Hr(),
            html.H4("Call Microsoft Graph as the signed-in user"),
            html.Button("GET /me", id=ids.GRAPH_BTN, n_clicks=0),
            html.Pre(
                id=ids.GRAPH_OUT,
                style={"background": "#f5f5f5", "padding": "1rem", "overflowX": "auto"},
            ),
        ],
    )
