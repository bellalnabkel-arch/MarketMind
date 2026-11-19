"""MarketMind: real Python/Streamlit server with Plotly and JavaScript components.

Run: python -m streamlit run app.py
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from marketmind.analytics import calculate_metrics, latest_metrics
from marketmind.company_search import CompanyDirectory, CompanyIndex
from marketmind.config import FRED_SERIES
from marketmind.dcf import DCFInputs, run_dcf, sensitivity_table
from marketmind.exceptions import MarketMindError
from marketmind.financials import build_annual_financials
from marketmind.data_service import ensure_financial_data, ensure_macro_data
from marketmind.sec_client import resolve_identity
from marketmind.macro_dashboard import render_macro_dashboard
from marketmind.regions import format_macro_value
from marketmind.report import build_equity_research_report
from marketmind.ui import apply_styles, fmt_money, fmt_pct, sensitivity_heatmap
from marketmind.wacc import calculate_wacc

st.set_page_config(page_title="MarketMind | Financial Intelligence", page_icon="📊", layout="wide")
apply_styles()

def secret(name):
    try:
        return st.secrets.get(name, os.getenv(name, ""))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return os.getenv(name, "")

def initialize():
    for key, value in {"selected_company": None, "metrics": pd.DataFrame(), "facts": None, "macro": {}, "macro_errors": {}, "dcf_result": None, "dcf_inputs": None, "financial_source": None, "sec_error": None}.items():
        if key not in st.session_state:
            st.session_state[key] = value

@st.cache_data(ttl=900, show_spinner=False)
def directory_data(_agent=""):
    try:
        declared_agent = resolve_identity(_agent)
    except MarketMindError:
        declared_agent = ""
    return CompanyDirectory().load(declared_agent)

@st.cache_resource(show_spinner=False)
def company_index(companies_json):
    return CompanyIndex(json.loads(companies_json))

def select_company(company):
    previous = st.session_state.selected_company
    if previous and (previous["ticker"], previous["cik"]) == (company["ticker"], company["cik"]):
        return
    st.session_state.selected_company = company
    st.query_params["company"] = company["ticker"]
    for key, value in {"metrics": pd.DataFrame(), "facts": None, "financial_source": None, "dcf_inputs": None, "dcf_result": None, "saved_model_values": {}, "sec_error": None, "sec_error_code": None}.items():
        st.session_state[key] = value
    for key in ("model_fcf", "model_cash", "model_debt", "model_shares"):
        st.session_state.pop(key, None)

def company_selected(index):
    ticker = st.session_state.get("company_result")
    if ticker:
        select_company(index.tickers[ticker])

def show_chart(frame, columns, title, percentage=False):
    available = [c for c in columns if c in frame and frame[c].notna().any()]
    if not available:
        st.info("No reported data is available for this chart.")
        return
    fig = px.line(frame, x="period_end", y=available, markers=True, title=title, template="plotly_white")
    fig.update_layout(legend_title_text="", margin=dict(l=10, r=10, t=50, b=10), hovermode="x unified", xaxis_title="Reporting period ended", yaxis_title="Percent" if percentage else "USD")
    if percentage:
        fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, width="stretch")

initialize()
agent = secret("SEC_USER_AGENT")
fred_key = secret("FRED_API_KEY")
directory = directory_data(agent)
index = company_index(json.dumps(directory["companies"], sort_keys=True))
if st.session_state.selected_company is None:
    restored = st.query_params.get("company")
    if restored and restored in index.tickers:
        select_company(index.tickers[restored])

with st.sidebar:
    st.title("MarketMind")
    st.caption("Financial intelligence")
    if st.session_state.get("workspace") == "Data connections":
        st.session_state.workspace = "Overview"
    page = st.radio("Workspace", ["Overview", "Financials", "DCF valuation", "Macro dashboard", "Research report"], key="workspace")
    st.divider()
    st.caption("Python + Streamlit server")
    st.caption("SEC EDGAR · FRED · Plotly")

st.caption("MARKETMIND / FINANCIAL INTELLIGENCE")
query = st.text_input("Search company by name, ticker or SEC CIK", placeholder="Type a company name, ticker or SEC CIK…", key="company_query", live="300ms")
results = index.search(query) if query else []
if query:
    if results:
        st.selectbox("Company suggestions — use arrow keys and Enter", [c["ticker"] for c in results], index=None, format_func=lambda ticker: f"{ticker} · {index.tickers[ticker]['name']} · CIK {index.tickers[ticker]['cik']} · {index.tickers[ticker].get('exchange') or 'Exchange unavailable'}", key="company_result", on_change=company_selected, args=(index,), placeholder="Select an official SEC company…")
    else:
        st.info("No matching companies. Try another name, ticker or full CIK.")
st.caption(f"{len(directory['companies']):,} SEC listings · Directory downloaded {directory['fetched_at']}")
if directory.get("warning"):
    st.caption("Searching the last downloaded SEC directory; automatic updates will resume when available.")
company = st.session_state.selected_company
if company:
    st.markdown(f"### {escape(company['name'])} · {escape(company['ticker'])}")
    st.caption(f"CIK {company['cik']} · {company.get('exchange') or 'Exchange unavailable'}")
    with st.spinner("Retrieving SEC financials…"):
        ensure_financial_data(st.session_state, company, agent)
    if st.session_state.sec_error:
        st.warning(st.session_state.sec_error)
    st.link_button("Open SEC company filings", f"https://www.sec.gov/edgar/browse/?CIK={company['cik']}&owner=exclude")

if page == "Macro dashboard" or (page == "Research report" and company):
    with st.spinner("Updating economic data from FRED…"):
        ensure_macro_data(st.session_state, fred_key)

metrics = st.session_state.metrics
latest = latest_metrics(metrics)
source = st.session_state.financial_source
if source:
    st.caption(f"{'Imported SEC JSON; retrieval freshness unverified' if source['imported'] else 'Retrieved from SEC'} · {source['retrieved_at']} · Latest period ended {latest['period_end']} · USD")
st.divider()

if page in ("Overview", "Financials"):
    st.title("See the story behind the numbers." if page == "Overview" else "Historical financials")
    if metrics.empty:
        st.info("Search and select a company above. Its available SEC financials will appear automatically.")
    else:
        cards = st.columns(5)
        for col, label, value in zip(cards, ["Revenue", "Revenue growth", "Operating margin", "ROE", "Free cash flow"], [fmt_money(latest.get("revenue")), fmt_pct(latest.get("revenue_growth")), fmt_pct(latest.get("operating_margin")), fmt_pct(latest.get("roe")), fmt_money(latest.get("free_cash_flow"))]):
            col.metric(label, value)
        show_chart(metrics, ["revenue", "operating_income", "net_income", "free_cash_flow"], "Historical financial performance")
        if page == "Financials":
            show_chart(metrics, ["operating_margin", "net_margin", "fcf_margin"], "Margin profile", True)
            visible = ["period_end", "revenue", "revenue_growth", "ebitda", "operating_income", "operating_margin", "net_income", "roe", "roa", "cash_from_operations", "capex", "free_cash_flow", "assets", "equity", "cash", "shares_outstanding"]
            st.dataframe(metrics[visible], hide_index=True, width="stretch")
            st.download_button("Download financial CSV", metrics.to_csv(index=False), f"{company['ticker']}_SEC_financials.csv", "text/csv")
            st.caption("EBITDA is a proxy: EBIT plus reported cash-flow D&A. FCF is CFO minus capex. ROE/ROA require adjacent annual balances; latest-filed comparative values may be restated.")
            with st.expander("SEC tags and filing dates"):
                st.dataframe(metrics[[c for c in metrics if c.endswith(("_tag", "_filed", "_accession")) or c == "period_end"]], hide_index=True)

elif page == "DCF valuation":
    st.title("Discounted cash flow")
    st.caption("All editable values are analyst assumptions. Dollar amounts and shares use millions consistently.")
    cols = st.columns(4)
    saved = st.session_state.get("saved_model_values", {})
    reported_cash = latest.get("cash")
    reported_shares = latest.get("shares_outstanding")
    base = cols[0].number_input("Base unlevered FCF ($M)", value=saved.get("model_fcf"), min_value=0.0, key="model_fcf", placeholder="Required")
    cash = cols[1].number_input("Cash ($M)", value=saved.get("model_cash", reported_cash / 1e6 if reported_cash is not None and reported_cash >= 0 else None), min_value=0.0, key="model_cash", placeholder="Required; verify 0")
    debt = cols[2].number_input("Total debt ($M)", value=saved.get("model_debt"), min_value=0.0, key="model_debt", placeholder="Required; verify 0")
    shares = cols[3].number_input("Shares outstanding (M)", value=saved.get("model_shares", reported_shares / 1e6 if reported_shares is not None and reported_shares > 0 else None), min_value=0.0, key="model_shares", placeholder="Required")
    st.caption("Cash and shares are prefilled from the latest annual SEC facts when available; review share-class coverage. Historical CFO minus capex is not automatically treated as unlevered FCF. Supply a reviewed unlevered-FCF estimate and total-debt assumption.")
    cols = st.columns(3)
    growth = cols[0].number_input("Annual FCF growth (%)", value=saved.get("model_growth", 8.0), min_value=-90.0, max_value=100.0, key="model_growth") / 100
    wacc = cols[1].number_input("WACC (%)", value=saved.get("model_wacc", 9.0), min_value=0.1, max_value=50.0, key="model_wacc") / 100
    terminal = cols[2].number_input("Terminal growth (%)", value=saved.get("model_terminal", 2.5), min_value=-5.0, max_value=10.0, key="model_terminal") / 100
    st.session_state.saved_model_values = {"model_fcf": base, "model_cash": cash, "model_debt": debt, "model_shares": shares, "model_growth": growth * 100, "model_wacc": wacc * 100, "model_terminal": terminal * 100}
    with st.expander("Calculate WACC with CAPM"):
        c = st.columns(3)
        rf = c[0].number_input("Risk-free rate (%)", value=4.0) / 100
        beta = c[1].number_input("Beta", value=1.0)
        erp = c[2].number_input("Equity risk premium (%)", value=5.0, min_value=0.0) / 100
        c = st.columns(3)
        kd = c[0].number_input("Pretax debt cost (%)", value=5.0, min_value=0.0) / 100
        ew = c[1].number_input("Equity market-value weight (%)", value=80.0, min_value=0.0, max_value=100.0) / 100
        tax = c[2].number_input("Marginal tax rate (%)", value=25.0, min_value=0.0, max_value=99.0) / 100
        ke, calculated = calculate_wacc(rf, beta, erp, kd, ew, tax)
        st.write(f"CAPM cost of equity: {ke:.2%} · Calculated WACC: {calculated:.2%}")
        st.caption("Copy the calculated percentage into WACC above. Defaults are assumptions.")
    st.session_state.dcf_result = None
    st.session_state.dcf_inputs = None
    if any(value is None for value in (base, cash, debt, shares)):
        st.info("Complete all four required inputs to calculate value.")
    else:
        try:
            inputs = DCFInputs(base_fcf=base * 1e6, cash=cash * 1e6, debt=debt * 1e6, shares_outstanding=shares * 1e6, fcf_growth=growth, wacc=wacc, terminal_growth=terminal)
            result = run_dcf(inputs)
            st.session_state.dcf_inputs, st.session_state.dcf_result = inputs, result
            c = st.columns(3)
            c[0].metric("Enterprise value", fmt_money(result.enterprise_value))
            c[1].metric("Equity value", fmt_money(result.equity_value))
            c[2].metric("Implied share price", f"${result.implied_share_price:,.2f}")
            fig = px.bar(result.forecast, x="year", y="free_cash_flow", title="Five-year projected unlevered FCF", template="plotly_white")
            st.plotly_chart(fig, width="stretch")
            st.plotly_chart(sensitivity_heatmap(sensitivity_table(inputs), wacc, terminal), width="stretch")
            st.dataframe(result.forecast, hide_index=True, width="stretch")
        except MarketMindError as exc:
            st.error(str(exc))

elif page == "Macro dashboard":
    render_macro_dashboard(st.session_state)

elif page == "Research report":
    st.title("Equity research report")
    if not company:
        st.info("Select a company first.")
    else:
        identity = {**company, "title": company["name"]}
        macro_lines = []
        for label, frame in st.session_state.macro.items():
            if not frame.empty:
                r = frame.iloc[-1]
                macro_lines.append(f"- {label}: {format_macro_value(FRED_SERIES[label], float(r['value']))}, observation {r['date'].date()}. https://fred.stlouisfed.org/series/{FRED_SERIES[label]}")
        selected_dates = [latest[c] for c in latest if c.endswith("_filed") and latest[c]]
        report = build_equity_research_report(identity, metrics, latest, st.session_state.dcf_inputs, st.session_state.dcf_result, "\n".join(macro_lines) or None, max(selected_dates, default=None))
        report += f"\n\nDirectory downloaded: {directory['fetched_at']}\n\nSEC facts: https://data.sec.gov/api/xbrl/companyfacts/CIK{company['cik']}.json\n"
        if source:
            report += f"\n{'File imported; source retrieval freshness is unverified' if source['imported'] else 'Retrieved from SEC'}: {source['retrieved_at']}\n"
        if not metrics.empty:
            for name in ("revenue", "operating_income", "net_income", "cash_from_operations", "capex", "assets", "equity"):
                if latest.get(name + "_filed"):
                    accession = latest.get(name + "_accession") or ""
                    link = f"https://www.sec.gov/Archives/edgar/data/{int(company['cik'])}/{accession.replace('-', '')}/" if accession else ""
                    report += f"\n- {name}: {latest.get(name + '_tag')}, period {latest['period_end']}, filed {latest[name + '_filed']}. {link}\n"
        st.download_button("Download Markdown report", report, f"{company['ticker']}_MarketMind.md", "text/markdown")
        st.markdown(report)

@st.fragment(run_every="60s")
def automatic_refresh_tick():
    now = time.time()
    previous = st.session_state.get("_automatic_refresh_check", now)
    st.session_state.setdefault("_automatic_refresh_check", now)
    if now - previous >= 60:
        st.session_state["_automatic_refresh_check"] = now
        st.rerun()

automatic_refresh_tick()

st.caption("MarketMind · Reported SEC facts / derived metrics / analyst assumptions · Missing data remains unavailable.")
