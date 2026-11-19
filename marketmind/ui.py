"""Streamlit presentation helpers for a consistent analyst-style interface."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

NAVY = "#0B1220"
BLUE = "#1D4ED8"
MUTED = "#475569"


def apply_styles() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{ background: #F6F8FB; color: #142033; }}
        [data-testid="stMain"] {{ font-size: 1rem; line-height: 1.6; }}
        [data-testid="stCaptionContainer"] {{ opacity: 1; }}
        [data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3 {{ color: #0F172A; letter-spacing: -.02em; }}
        [data-testid="stMain"] [data-testid="stCaptionContainer"] {{ color: #475569; font-size: .9rem; line-height: 1.6; }}
        [data-testid="stMain"] [data-testid="stWidgetLabel"] p {{ color: #1E293B; font-weight: 650; font-size: .95rem; }}
        [data-testid="stMain"] input, [data-testid="stMain"] textarea {{ color: #142033; background: white; }}
        [data-testid="stMain"] input::placeholder {{ color: #526176; opacity: 1; }}
        [data-testid="stMain"] a {{ color: #1D4ED8; text-decoration: underline; text-underline-offset: 3px; }}
        [data-testid="stMetricValue"] {{ color: #0F172A; font-weight: 700; }}
        [data-testid="stMetricLabel"] p {{ color: #334155; font-weight: 650; }}
        [data-testid="stAlert"] p {{ color: #1E293B; line-height: 1.6; }}
        [data-testid="stMain"] button {{ font-weight: 650; }}
        [data-testid="stMain"] button:focus-visible, [data-testid="stMain"] input:focus-visible {{ outline: 3px solid #1D4ED8; outline-offset: 3px; }}
        [data-testid="stSidebar"] {{ background: {NAVY}; }}
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ color: #CBD5E1; font-size: .9rem; }}
        [data-testid="stSidebar"] label:has(input:checked) {{ background: #1E3A5F; border-radius: .4rem; }}
        [data-testid="stSidebar"] :focus-visible {{ outline-color: #93C5FD; }}
        .mm-kicker {{ color: {BLUE}; font-size: .75rem; font-weight: 700; letter-spacing: .10em; text-transform: uppercase; }}
        .mm-title {{ color: {NAVY}; font-size: 2.35rem; font-weight: 800; line-height: 1.1; margin: 0 0 .35rem 0; }}
        .mm-subtitle {{ color: {MUTED}; font-size: 1rem; margin-bottom: 1.25rem; }}
        .mm-note {{ background: #EEF5FF; border-left: 4px solid {BLUE}; padding: .8rem 1rem; border-radius: .4rem; color: {NAVY}; }}
        div[data-testid="stMetric"] {{ background: white; border: 1px solid #E6EAF0; border-radius: .65rem; padding: .8rem; box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(f'<div class="mm-kicker">{kicker}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="mm-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="mm-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def fmt_money(value: Any, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    value = float(value)
    magnitude = abs(value)
    suffix, divisor = "", 1.0
    if magnitude >= 1_000_000_000:
        suffix, divisor = "B", 1_000_000_000
    elif magnitude >= 1_000_000:
        suffix, divisor = "M", 1_000_000
    elif magnitude >= 1_000:
        suffix, divisor = "K", 1_000
    return f"{'-' if value < 0 else ''}${magnitude / divisor:,.{decimals}f}{suffix}"


def fmt_pct(value: Any, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value) * 100:.{decimals}f}%"


def historical_chart(metrics: pd.DataFrame, columns: list[str], title: str) -> go.Figure:
    labels = {"revenue": "Revenue", "ebitda": "EBITDA", "operating_income": "Operating income", "net_income": "Net income", "free_cash_flow": "Free cash flow"}
    available = [column for column in columns if column in metrics.columns and metrics[column].notna().any()]
    chart_frame = metrics[["fiscal_year", *available]].melt(id_vars="fiscal_year", var_name="metric", value_name="value")
    chart_frame["metric"] = chart_frame["metric"].map(labels).fillna(chart_frame["metric"])
    fig = px.line(chart_frame, x="fiscal_year", y="value", color="metric", markers=True, title=title, template="plotly_white")
    fig.update_layout(legend_title_text="", margin=dict(l=10, r=10, t=50, b=10), hovermode="x unified")
    fig.update_yaxes(tickformat=",.2s")
    return fig


def margin_chart(metrics: pd.DataFrame) -> go.Figure:
    columns = ["ebitda_margin", "operating_margin", "net_margin", "fcf_margin"]
    labels = {"ebitda_margin": "EBITDA margin", "operating_margin": "Operating margin", "net_margin": "Net margin", "fcf_margin": "FCF margin"}
    available = [column for column in columns if column in metrics.columns and metrics[column].notna().any()]
    chart_frame = metrics[["fiscal_year", *available]].melt(id_vars="fiscal_year", var_name="metric", value_name="value")
    chart_frame["metric"] = chart_frame["metric"].map(labels).fillna(chart_frame["metric"])
    fig = px.line(chart_frame, x="fiscal_year", y="value", color="metric", markers=True, title="Margin profile", template="plotly_white")
    fig.update_layout(legend_title_text="", margin=dict(l=10, r=10, t=50, b=10), hovermode="x unified")
    fig.update_yaxes(tickformat=".0%")
    return fig


def macro_chart(data: dict[str, pd.DataFrame], selected: list[str]) -> go.Figure:
    fig = go.Figure()
    for label in selected:
        frame = data.get(label, pd.DataFrame())
        if frame.empty:
            continue
        fig.add_trace(go.Scatter(x=frame["date"], y=frame["value"], mode="lines", name=label))
    fig.update_layout(template="plotly_white", margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified", legend_title_text="")
    return fig


def sensitivity_heatmap(table: pd.DataFrame, base_wacc: float, base_terminal_growth: float) -> go.Figure:
    values = table.to_numpy(dtype=float)
    text = np.vectorize(lambda value: "N/A" if pd.isna(value) else f"${value:,.2f}")(values)
    fig = go.Figure(data=go.Heatmap(z=values, x=[f"{value:.1%}" for value in table.columns], y=[f"{value:.1%}" for value in table.index], colorscale=[[0,'#EFF6FF'],[.5,'#BFDBFE'],[1,'#93C5FD']], text=text, textfont_color='#0F172A', texttemplate="%{text}", hovertemplate="WACC %{y}<br>Terminal growth %{x}<br>Implied price %{text}<extra></extra>", colorbar_title="$/share"))
    fig.update_layout(title=f"Sensitivity table · base case {base_wacc:.1%} WACC / {base_terminal_growth:.1%} terminal growth", template="plotly_white", margin=dict(l=10, r=10, t=60, b=10))
    fig.update_xaxes(title="Terminal growth")
    fig.update_yaxes(title="WACC")
    return fig
