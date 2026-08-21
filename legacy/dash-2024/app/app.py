"""FaultForce 2024 capstone dashboard - repaired.

This is the original 2024 Dash dashboard with its 15 defects fixed (see
docs/BUGS.md, entries APP-01 .. APP-15). Structure and visual identity are kept
deliberately close to the original; this directory is a preserved historical
artefact, superseded by the RailPoint-AI system at the repository root.

IMPORTANT: the "Prediction" column here is a HEURISTIC CURRENT THRESHOLD, not a
machine-learning model. The 2024 code never contained a model despite the report
claiming one. That is stated in the UI rather than hidden.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import plotly.graph_objs as go
from dash import Input, Output, dcc, html

# APP-01: paths were hardcoded to C:\Users\singh\... and crashed off that one
# Windows machine. Resolve relative to this file, with an env override.
BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parents[2]
DATA_DIR = Path(os.environ.get("FAULTFORCE_DATA_DIR", REPO_ROOT / "data" / "raw" / "sehwa"))

EVENTS_CSV = DATA_DIR / "pmd_events.csv"
ERROR_CODES_CSV = DATA_DIR / "error_codes.csv"

# APP-03/04: the real dataset used to be loaded and then never referenced. It is
# now the source of both the machine list and the replay mode.
events = pd.read_csv(EVENTS_CSV)

# APP-11: the Korean maintenance table is EUC-KR and rendered as mojibake. It is
# now decoded once, into a KO/EN table.
error_codes = pd.read_csv(ERROR_CODES_CSV)
error_codes["detail"] = (
    error_codes["component_ko"] + " / " + error_codes["component_en"]
)

# APP-15: the dropdowns offered PMD001/014/020 but the data only ever contained
# PMD014 and PMD055. Derive the options from the data instead of guessing.
PMD_OPTIONS = sorted(events["pmd_type"].unique().tolist())

SIGNAL_COLS = ["ac_curr", "ac_volt", "as_volt", "output_n_volt", "output_r_volt"]

# Calibrated to the real traces rather than invented: ac_curr spans 0.01-15.74 A
# (idle ~0.07 A, throw plateau ~9 A) and ac_volt spans 205-230 V. The original
# drew current from uniform(0.1, 300) and then thresholded it at 260, which is
# physically meaningless for this machine.
AC_CURR_IDLE = 0.07
AC_CURR_THROW = 9.0
AC_CURR_MAX = 15.74
AC_VOLT_RANGE = (205.25, 230.49)

# APP-02: an honest name for what this actually is.
HEURISTIC_THRESHOLD_A = 12.0


def event_key(df: pd.DataFrame) -> pd.Series:
    return df["pmd_type"].astype(str) + "#" + df["event_num"].astype(str)


def list_real_events(pmd_type: str) -> list[str]:
    subset = events[events["pmd_type"] == pmd_type]
    return sorted(event_key(subset).unique().tolist())


def load_real_event(key: str) -> pd.DataFrame:
    pmd_type, event_num = key.split("#")
    df = events[
        (events["pmd_type"] == pmd_type) & (events["event_num"].astype(str) == event_num)
    ].copy()
    df = df.sort_values("event_seq").reset_index(drop=True)
    df["Power"] = df["ac_curr"] * df["ac_volt"]
    df["Prediction"] = np.where(df["ac_curr"] > HEURISTIC_THRESHOLD_A, "Abnormal", "Normal")
    df = df.merge(error_codes[["err_code", "detail"]], on="err_code", how="left")
    df["detail"] = df["detail"].fillna("No error details")
    return df


def generate_simulated_data(
    pmd_type: str = "PMD014", num_events: int = 100, seed: int | None = None
) -> pd.DataFrame:
    """Synthetic events, calibrated to the real signal ranges.

    APP-10: the original called np.random.seed() with no argument on every
    callback, reseeding from OS entropy and making the app non-reproducible by
    construction. The seed is now explicit and threaded through.
    """
    rng = np.random.default_rng(seed)

    # A throw is mostly idle current with a plateau in the middle, not uniform
    # noise across the whole range.
    base = rng.normal(AC_CURR_THROW, 1.2, num_events)
    idle_mask = rng.random(num_events) < 0.25
    base[idle_mask] = rng.normal(AC_CURR_IDLE, 0.02, idle_mask.sum())
    spike_mask = rng.random(num_events) < 0.08
    base[spike_mask] = rng.uniform(AC_CURR_THROW, AC_CURR_MAX, spike_mask.sum())
    ac_curr = np.clip(base, 0.01, AC_CURR_MAX)

    # APP-08: err_code used to be built with a None inside np.random.choice,
    # producing an object-dtype column that merged unreliably. Use a sentinel
    # string and convert to NA explicitly.
    codes = error_codes["err_code"].tolist()
    drawn = rng.choice(
        codes + ["__none__"],
        size=num_events,
        p=[0.03] * len(codes) + [1 - 0.03 * len(codes)],
    )
    err_code = pd.Series(drawn).replace("__none__", pd.NA)

    df = pd.DataFrame(
        {
            "event_num": np.arange(1, num_events + 1),
            "pmd_type": [pmd_type] * num_events,
            "direction": rng.choice(["N", "R"], size=num_events),
            "ac_curr": ac_curr,
            "ac_volt": rng.uniform(*AC_VOLT_RANGE, num_events),
            "err_code": err_code,
        }
    )
    df["Power"] = df["ac_curr"] * df["ac_volt"]
    df["Prediction"] = np.where(df["ac_curr"] > HEURISTIC_THRESHOLD_A, "Abnormal", "Normal")
    df = df.merge(error_codes[["err_code", "detail"]], on="err_code", how="left")
    df["detail"] = df["detail"].fillna("No error details")
    return df


# ---------------------------------------------------------------------------
# Layout components
# ---------------------------------------------------------------------------


def pmd_status_indicator(prediction: str) -> html.Span:
    color = {"Normal": "green", "Abnormal": "red"}.get(prediction, "orange")
    return html.Span(
        style={
            "backgroundColor": color,
            "borderRadius": "50%",
            "display": "inline-block",
            "width": "15px",
            "height": "15px",
            "marginRight": "10px",
        }
    )


def create_station_selector(station_name: str, dropdown_id: str, default: str) -> html.Div:
    return html.Div(
        [
            dbc.Label(f"Select PMD for {station_name}"),
            dcc.Dropdown(
                id=dropdown_id,
                options=[{"label": p, "value": p} for p in PMD_OPTIONS],
                value=default,
                clearable=False,
            ),
        ],
        style={"marginBottom": "10px", "width": "100%"},
    )


def make_figure(title: str, traces: list[go.Scatter]) -> dict:
    """APP-07: return a real figure with axis titles and a legend."""
    return {
        "data": traces,
        "layout": go.Layout(
            title=title,
            xaxis_title="Event number",
            yaxis_title="Power (VA)",
            margin=dict(l=50, r=20, t=50, b=40),
            showlegend=True,
        ),
    }


def station_figures(df: pd.DataFrame, station_name: str) -> list[dcc.Graph]:
    normal = df[df["Prediction"] == "Normal"]
    abnormal = df[df["Prediction"] == "Abnormal"]

    # APP-06: the "Normal Data" chart used to plot every row regardless of label.
    normal_fig = make_figure(
        f"{station_name}: Normal events ({len(normal)})",
        [
            go.Scatter(
                x=normal["event_num"],
                y=normal["Power"],
                mode="lines+markers",
                line=dict(color="green"),
                name="Normal",
            )
        ],
    )

    abnormal_fig = make_figure(
        f"{station_name}: Abnormal events ({len(abnormal)})",
        [
            go.Scatter(
                x=abnormal["event_num"],
                y=abnormal["Power"],
                mode="markers",
                marker=dict(color="red", size=8),
                name="Abnormal",
            )
        ],
    )

    # APP-07: the third chart used to be an exact copy of the first, recoloured
    # by row 0's label. It now shows the actual decision: the signal, the
    # threshold that produced each label, and the points that crossed it.
    threshold_power = HEURISTIC_THRESHOLD_A * df["ac_volt"].mean()
    decision_fig = make_figure(
        f"{station_name}: Heuristic decision (threshold {HEURISTIC_THRESHOLD_A} A)",
        [
            go.Scatter(
                x=df["event_num"],
                y=df["Power"],
                mode="lines",
                line=dict(color="#777"),
                name="Signal",
            ),
            go.Scatter(
                x=df["event_num"],
                y=[threshold_power] * len(df),
                mode="lines",
                line=dict(color="orange", dash="dash"),
                name="Threshold",
            ),
            go.Scatter(
                x=abnormal["event_num"],
                y=abnormal["Power"],
                mode="markers",
                marker=dict(color="red", size=9, symbol="x"),
                name="Flagged",
            ),
        ],
    )

    return [
        dcc.Graph(figure=normal_fig, config={"displayModeBar": False}, style={"flex": "1", "minWidth": "320px"}),
        dcc.Graph(figure=abnormal_fig, config={"displayModeBar": False}, style={"flex": "1", "minWidth": "320px"}),
        dcc.Graph(figure=decision_fig, config={"displayModeBar": False}, style={"flex": "1", "minWidth": "320px"}),
    ]


def create_log_table(df: pd.DataFrame) -> dash.dash_table.DataTable:
    """APP-09: the original rebuilt a 200-row Bootstrap HTML table every 4 s.

    A paginated DataTable sends far less markup and is actually navigable.
    """
    cols = ["event_num", "pmd_type", "direction", "Prediction", "err_code", "detail"]
    view = df[cols].copy()
    view["err_code"] = view["err_code"].fillna("-")
    return dash.dash_table.DataTable(
        data=view.to_dict("records"),
        columns=[{"name": c, "id": c} for c in cols],
        page_size=10,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_header={"fontWeight": "bold", "backgroundColor": "#770000", "color": "white"},
        style_cell={"textAlign": "center", "fontSize": "13px", "padding": "6px"},
        style_data_conditional=[
            {
                "if": {"filter_query": '{Prediction} = "Abnormal"'},
                "backgroundColor": "#FFD6D6",
            }
        ],
    )


DISCLAIMER = dbc.Alert(
    [
        html.B("Historical artefact (2024). "),
        "The 'Prediction' column below is a fixed current threshold of "
        f"{HEURISTIC_THRESHOLD_A} A, not a trained model — the 2024 code never "
        "contained one. Superseded by the RailPoint-AI system in this repository.",
    ],
    color="warning",
    style={"width": "95%", "margin": "10px auto", "fontSize": "13px"},
)

# APP-12: every NavLink was href="#", so two of the three pages did nothing.
sidebar = html.Div(
    [
        html.Img(src="/assets/faultforce-logo.png", style={"width": "100%", "padding": "10px"}),
        html.Hr(style={"borderColor": "white"}),
        dbc.Nav(
            [
                dbc.NavLink("Monitoring", href="/", active="exact", style={"color": "white"}),
                dbc.NavLink("Failure Analysis", href="/analysis", active="exact", style={"color": "white"}),
                dbc.NavLink("Reports", href="/reports", active="exact", style={"color": "white"}),
            ],
            vertical=True,
            pills=True,
        ),
    ],
    style={
        "backgroundColor": "darkred",
        "height": "100vh",
        "padding": "20px",
        "borderRight": "2px solid #770000",
        "position": "fixed",
        "top": 0,
        "left": 0,
        "width": "200px",
        "boxSizing": "border-box",
    },
)

top_bar = dbc.Row(
    [dbc.Col(html.H3("PMD Predictive Maintenance", style={"color": "white", "margin": "0"}), md=8)],
    style={"backgroundColor": "darkred", "padding": "10px", "boxSizing": "border-box"},
)

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY], title="FaultForce 2024 (repaired)")

app.layout = html.Div(
    [
        dcc.Location(id="url"),
        sidebar,
        html.Div(
            [top_bar, DISCLAIMER, html.Div(id="page-content")],
            style={
                "backgroundColor": "#FFFDFD",
                "minHeight": "100vh",
                "overflowY": "auto",
                "marginLeft": "200px",
                "boxSizing": "border-box",
            },
        ),
    ]
)


def monitoring_page() -> html.Div:
    default_1 = PMD_OPTIONS[0]
    default_2 = PMD_OPTIONS[1] if len(PMD_OPTIONS) > 1 else PMD_OPTIONS[0]
    return html.Div(
        [
            html.Div(
                html.H4(
                    "PMD Machine Status",
                    style={
                        "textAlign": "center",
                        "color": "white",
                        "backgroundColor": "#770000",
                        "padding": "5px",
                        "borderRadius": "5px",
                    },
                ),
                style={"width": "95%", "margin": "10px auto"},
            ),
            html.Div(
                id="real-time-info",
                style={
                    "padding": "10px",
                    "backgroundColor": "#FFD6D6",
                    "border": "1px solid #770000",
                    "width": "95%",
                    "fontSize": "13px",
                    "borderRadius": "5px",
                    "margin": "10px auto",
                },
            ),
            html.Div(
                [
                    create_station_selector("Station 1", "station-1-dropdown", default_1),
                    create_station_selector("Station 2", "station-2-dropdown", default_2),
                ],
                style={"width": "95%", "margin": "0 auto"},
            ),
            html.Div(id="station-1-graphs-container", style={"display": "flex", "flexWrap": "wrap", "width": "95%", "margin": "10px auto"}),
            html.Div(id="station-2-graphs-container", style={"display": "flex", "flexWrap": "wrap", "width": "95%", "margin": "10px auto"}),
            dcc.Interval(id="interval-component", interval=4000, n_intervals=0),
            html.Div(id="log-table", style={"padding": "20px", "width": "95%", "margin": "0 auto"}),
        ]
    )


def analysis_page() -> html.Div:
    """Real Sehwa traces - the data the 2024 dashboard loaded and never displayed."""
    keys = [k for p in PMD_OPTIONS for k in list_real_events(p)]
    return html.Div(
        [
            html.H4("Failure Analysis - real Sehwa events", style={"padding": "10px 0"}),
            html.P(
                f"{len(keys)} recorded switching events across {len(PMD_OPTIONS)} machines. "
                "Every one of them carries a fault code; there are no normal events in this "
                "extract, which is why it cannot train a supervised model on its own.",
                style={"fontSize": "13px", "color": "#555"},
            ),
            dcc.Dropdown(id="event-dropdown", options=[{"label": k, "value": k} for k in keys], value=keys[0], clearable=False),
            dcc.Graph(id="event-waveform"),
            html.Div(id="event-meta", style={"fontSize": "13px", "padding": "10px"}),
        ],
        style={"width": "95%", "margin": "10px auto"},
    )


def reports_page() -> html.Div:
    counts = events.groupby(["pmd_type", "err_code"]).agg(events=("event_num", "nunique"), samples=("event_seq", "size")).reset_index()
    counts = counts.merge(error_codes[["err_code", "detail"]], on="err_code", how="left")
    return html.Div(
        [
            html.H4("Reports", style={"padding": "10px 0"}),
            dash.dash_table.DataTable(
                data=counts.to_dict("records"),
                columns=[{"name": c, "id": c} for c in counts.columns],
                style_header={"fontWeight": "bold", "backgroundColor": "#770000", "color": "white"},
                style_cell={"textAlign": "center", "padding": "6px", "fontSize": "13px"},
            ),
        ],
        style={"width": "95%", "margin": "10px auto"},
    )


@app.callback(Output("page-content", "children"), Input("url", "pathname"))
def render_page(pathname: str):
    if pathname == "/analysis":
        return analysis_page()
    if pathname == "/reports":
        return reports_page()
    return monitoring_page()


@app.callback(
    [Output("event-waveform", "figure"), Output("event-meta", "children")],
    Input("event-dropdown", "value"),
)
def render_event(key: str):
    df = load_real_event(key)
    traces = [
        go.Scatter(x=df["event_seq"], y=df["ac_curr"], name="ac_curr (A)", yaxis="y1"),
        go.Scatter(x=df["event_seq"], y=df["as_volt"], name="as_volt (V)", yaxis="y2"),
        go.Scatter(x=df["event_seq"], y=df["output_n_volt"], name="output_n_volt (V)", yaxis="y2"),
    ]
    fig = {
        "data": traces,
        "layout": go.Layout(
            title=f"{key} - direction {df['direction'].iloc[0]}, code {df['err_code'].iloc[0]}",
            xaxis_title="Sample index (event_seq)",
            yaxis=dict(title="Current (A)"),
            yaxis2=dict(title="Indication (V)", overlaying="y", side="right"),
            margin=dict(l=60, r=60, t=50, b=40),
        ),
    }
    row = df.iloc[0]
    meta = html.Div(
        [
            html.B("Fault code: "), f"{row['err_code']} - {row['detail']}", html.Br(),
            html.B("Samples: "), f"{len(df)}", html.Br(),
            html.B("Peak current: "), f"{df['ac_curr'].max():.2f} A", html.Br(),
            html.B("Supply voltage: "), f"{df['ac_volt'].min():.1f}-{df['ac_volt'].max():.1f} V",
        ]
    )
    return fig, meta


@app.callback(
    [
        Output("log-table", "children"),
        Output("real-time-info", "children"),
        Output("station-1-graphs-container", "children"),
        Output("station-2-graphs-container", "children"),
    ],
    [
        Input("interval-component", "n_intervals"),
        Input("station-1-dropdown", "value"),
        Input("station-2-dropdown", "value"),
    ],
)
def update_dashboard(n_intervals, pmd_station_1, pmd_station_2):
    # Reproducible per tick rather than reseeded from OS entropy (APP-10).
    d1 = generate_simulated_data(pmd_station_1, seed=1000 + (n_intervals or 0))
    d2 = generate_simulated_data(pmd_station_2, seed=2000 + (n_intervals or 0))

    log_table = create_log_table(pd.concat([d1, d2], ignore_index=True))

    def summary(name, pmd, df):
        worst = "Abnormal" if (df["Prediction"] == "Abnormal").any() else "Normal"
        return html.Div(
            [
                pmd_status_indicator(worst),
                html.Span(
                    f"{name}: {pmd} - {len(df)} events, "
                    f"{int((df['Prediction'] == 'Abnormal').sum())} flagged, "
                    f"{int(df['err_code'].notna().sum())} with a maintenance code"
                ),
            ],
            style={"marginBottom": "5px"},
        )

    info = html.Div([summary("Station 1", pmd_station_1, d1), summary("Station 2", pmd_station_2, d2)])
    return log_table, info, station_figures(d1, "Station 1"), station_figures(d2, "Station 2")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaultForce 2024 dashboard (repaired)")
    parser.add_argument("--port", type=int, default=8051)
    parser.add_argument("--host", default="127.0.0.1")
    # APP-13: debug=True was hardcoded in the entrypoint.
    parser.add_argument("--debug", action="store_true", default=os.environ.get("DASH_DEBUG") == "1")
    args = parser.parse_args()
    # APP-02: app.run_server() was removed in Dash 3.x.
    app.run(host=args.host, port=args.port, debug=args.debug)
