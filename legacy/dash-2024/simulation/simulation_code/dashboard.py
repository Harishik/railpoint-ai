"""FaultForce 2024 simulation dashboard - repaired.

Original defects fixed here: DBD-01 .. DBD-06 (see docs/BUGS.md).
"""

from __future__ import annotations

import argparse
import logging
import os

import pandas as pd
import plotly.express as px
import requests
from dash import Dash, Input, Output, dash_table, dcc, html

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("faultforce.dashboard")

SERVER_URL = os.environ.get("FAULTFORCE_SERVER_URL", "http://127.0.0.1:5001")
REQUEST_TIMEOUT_S = 4.0  # DBD-02: the original had no timeout at all.
TOP_N_MACHINES = 12

app = Dash(__name__, title="FaultForce simulation (repaired)")

app.layout = html.Div(
    [
        html.H1("Real-Time PMD Simulation Dashboard"),
        html.Div(
            [
                html.Span("Status: ", style={"fontWeight": "bold", "fontSize": "18px"}),
                html.Span(
                    id="status-indicator",
                    style={
                        "display": "inline-block",
                        "width": "20px",
                        "height": "20px",
                        "borderRadius": "50%",
                        "backgroundColor": "gray",
                        "marginRight": "10px",
                    },
                ),
                html.Span(id="live-status", style={"fontSize": "18px"}),
            ],
            style={"marginBottom": "20px"},
        ),
        dcc.Graph(id="real-time-plot-value"),
        dcc.Graph(id="real-time-plot-voltage"),
        dcc.Graph(id="real-time-plot-current"),
        html.H2("Logs"),
        dash_table.DataTable(
            id="logs-table",
            columns=[
                {"name": "Timestamp", "id": "timestamp"},
                {"name": "PMD", "id": "pmd_type"},
                {"name": "Voltage (V)", "id": "ac_volt"},
                {"name": "Current (A)", "id": "ac_curr"},
                {"name": "Power (VA)", "id": "value"},
                {"name": "Status", "id": "status"},
            ],
            # DBD-06: page_size was 10 on a table only ever handed df.tail(10),
            # so the pagination was decorative. It now receives a real window.
            page_size=15,
            sort_action="native",
            filter_action="native",
            style_table={"overflowX": "auto", "height": "420px", "overflowY": "auto"},
            style_header={"fontWeight": "bold", "textAlign": "center"},
            style_cell={"textAlign": "center", "fontSize": "13px"},
            style_data_conditional=[
                {"if": {"filter_query": '{status} = "error"'}, "backgroundColor": "#FFD6D6"}
            ],
        ),
        dcc.Interval(id="interval-component", interval=5000, n_intervals=0),
    ],
    style={"fontFamily": "system-ui, sans-serif", "margin": "20px"},
)


def empty_figure(message: str) -> dict:
    """DBD-04: the original returned a bare {} as a figure, which renders broken
    rather than empty."""
    return {
        "data": [],
        "layout": {
            "annotations": [
                {"text": message, "xref": "paper", "yref": "paper", "showarrow": False, "font": {"size": 15}}
            ],
            "xaxis": {"visible": False},
            "yaxis": {"visible": False},
            "margin": {"l": 40, "r": 20, "t": 40, "b": 30},
        },
    }


def dot(color: str) -> dict:
    return {
        "display": "inline-block",
        "width": "20px",
        "height": "20px",
        "borderRadius": "50%",
        "backgroundColor": color,
        "marginRight": "10px",
    }


@app.callback(
    [
        Output("real-time-plot-value", "figure"),
        Output("real-time-plot-voltage", "figure"),
        Output("real-time-plot-current", "figure"),
        Output("logs-table", "data"),
        Output("live-status", "children"),
        Output("status-indicator", "style"),
    ],
    Input("interval-component", "n_intervals"),
)
def update_dashboard(_n):
    # DBD-03: a single bare `except Exception` collapsed every distinct failure
    # into one red dot with no logging. Each failure mode is now distinguished.
    try:
        response = requests.get(f"{SERVER_URL}/data", params={"limit": 1000}, timeout=REQUEST_TIMEOUT_S)
        response.raise_for_status()
        data = response.json()
    except requests.Timeout:
        log.warning("simulation server timed out after %ss", REQUEST_TIMEOUT_S)
        msg = f"Simulation server timed out ({REQUEST_TIMEOUT_S}s)."
        return (empty_figure(msg),) * 3 + ([], msg, dot("orange"))
    except requests.ConnectionError:
        log.warning("cannot reach simulation server at %s", SERVER_URL)
        msg = f"Cannot reach the simulation server at {SERVER_URL}."
        return (empty_figure(msg),) * 3 + ([], msg, dot("red"))
    except requests.HTTPError as exc:
        log.error("simulation server returned %s", exc.response.status_code)
        msg = f"Simulation server error: HTTP {exc.response.status_code}."
        return (empty_figure(msg),) * 3 + ([], msg, dot("red"))
    except ValueError:
        log.exception("simulation server returned a non-JSON body")
        msg = "Simulation server returned an invalid response."
        return (empty_figure(msg),) * 3 + ([], msg, dot("red"))

    if not data:
        msg = "Connected, but the server has not produced any data yet."
        return (empty_figure(msg),) * 3 + ([], msg, dot("orange"))

    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp")

    # DBD-05: the original rebuilt three 56-category bar charts every 5 s from a
    # rolling window that mixed machines, so the bars jittered meaninglessly.
    # Show the time series for the busiest machines, plus a ranked snapshot.
    busiest = df["pmd_type"].value_counts().head(TOP_N_MACHINES).index.tolist()
    focus = df[df["pmd_type"].isin(busiest)]

    fig_value = px.line(
        focus, x="timestamp", y="value", color="pmd_type",
        title=f"Power over time - {len(busiest)} busiest machines",
        labels={"value": "Power (VA)", "timestamp": "Time"},
    )
    fig_voltage = px.line(
        focus, x="timestamp", y="ac_volt", color="pmd_type",
        title="Supply voltage over time",
        labels={"ac_volt": "Voltage (V)", "timestamp": "Time"},
    )
    ranked = (
        df.groupby("pmd_type")["ac_curr"].max().sort_values(ascending=False).head(TOP_N_MACHINES).reset_index()
    )
    fig_current = px.bar(
        ranked, x="pmd_type", y="ac_curr",
        title=f"Peak current per machine - top {TOP_N_MACHINES}",
        labels={"ac_curr": "Peak current (A)", "pmd_type": "Machine"},
    )

    errors = int((df["status"] == "error").sum())
    status = f"Simulation running: {len(df)} records, {errors} flagged."
    return fig_value, fig_voltage, fig_current, df.tail(200).to_dict("records"), status, dot("green")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaultForce simulation dashboard (repaired)")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--debug", action="store_true", default=os.environ.get("DASH_DEBUG") == "1")
    args = parser.parse_args()
    # DBD-01: app.run_server() was removed in Dash 3.x.
    app.run(host=args.host, port=args.port, debug=args.debug)
