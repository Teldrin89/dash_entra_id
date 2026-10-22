"""All Dash callbacks, registered against the app in app.py."""
import json

import plotly.express as px
from dash import Input, Output

import graph
import ids


def register_callbacks(app):
    @app.callback(Output(ids.GRAPH, "figure"), Input(ids.COUNTRY_DROPDOWN, "value"))
    def update_graph(countries):
        df = px.data.gapminder()
        df = df[df["country"].isin(countries or [])]
        return px.line(
            df, x="year", y="lifeExp", color="country", markers=True,
            labels={"lifeExp": "Life expectancy (years)", "year": "Year"},
        )

    @app.callback(
        Output(ids.GRAPH_OUT, "children"),
        Input(ids.GRAPH_BTN, "n_clicks"),
        prevent_initial_call=True,
    )
    def call_graph_api(_):
        status, body = graph.get_me()
        return f"HTTP {status}\n{json.dumps(body, indent=2)}"
