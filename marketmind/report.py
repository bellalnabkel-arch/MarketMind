"""Deterministic equity-research report generation from sourced data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


def _money(value: Any, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    sign = "-" if float(value) < 0 else ""
    return f"{sign}${abs(float(value)) / 1_000_000_000:,.{decimals}f}B"


def _percent(value: Any, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value) * 100:.{decimals}f}%"


def build_equity_research_report(
    identity: dict[str, str],
    metrics: pd.DataFrame,
    latest: dict[str, Any],
    dcf_inputs: Any | None = None,
    dcf_result: Any | None = None,
    macro_summary: str | None = None,
    source_date: str | None = None,
) -> str:
    """Create a professional Markdown report without inventing unavailable facts."""

    ticker = identity.get("ticker", "Unknown")
    title = identity.get("title", ticker)
    fiscal_year = latest.get("fiscal_year", "latest")
    report_lines = [
        f"# MarketMind Equity Research Report: {ticker}",
        "",
        f"**Issuer:** {title}  \n**Report generated (UTC):** {datetime.now(timezone.utc).isoformat()}  \n**Latest annual period ended:** {latest.get('period_end', 'not loaded')}  \n**Latest filing date among selected facts:** {source_date or 'not reported'}",
        "",
        "> This report is analytical software output, not investment advice. Historical figures are sourced from SEC XBRL facts. Forecasts and valuation outputs are model assumptions, not reported results.",
        "",
        "## Company overview",
        f"{title} ({ticker}) was selected through the SEC EDGAR ticker directory. The platform does not infer business descriptions when a verified filing narrative is not loaded.",
        "",
        "## Financial performance — actual SEC data",
        "",
        f"- Revenue: {_money(latest.get('revenue'))}",
        f"- Revenue growth: {_percent(latest.get('revenue_growth'))}",
        f"- EBITDA: {_money(latest.get('ebitda'))}",
        f"- EBITDA margin: {_percent(latest.get('ebitda_margin'))}",
        f"- Operating margin: {_percent(latest.get('operating_margin'))}",
        f"- Net income: {_money(latest.get('net_income'))}",
        f"- ROE: {_percent(latest.get('roe'))}",
        f"- ROA: {_percent(latest.get('roa'))}",
        f"- Free cash flow: {_money(latest.get('free_cash_flow'))}",
        "",
        "## Valuation — assumptions and projections",
    ]
    if dcf_inputs is not None and dcf_result is not None:
        report_lines.extend(
            [
                "",
                f"The DCF forecasts {dcf_inputs.forecast_years} years of free cash flow using a {dcf_inputs.fcf_growth * 100:.1f}% annual FCF growth assumption, {dcf_inputs.wacc * 100:.1f}% WACC, and {dcf_inputs.terminal_growth * 100:.1f}% terminal growth.",
                "",
                f"- Base unlevered FCF assumption: {_money(dcf_inputs.base_fcf)}",
                f"- Cash / total debt: {_money(dcf_inputs.cash)} / {_money(dcf_inputs.debt)}",
                f"- Shares outstanding assumption: {dcf_inputs.shares_outstanding:,.0f}",
                f"- Enterprise value: {_money(dcf_result.enterprise_value)}",
                f"- Equity value: {_money(dcf_result.equity_value)}",
                f"- Implied share price: ${dcf_result.implied_share_price:,.2f}",
                f"- Net debt used: {_money(dcf_result.net_debt)}",
            ]
        )
    else:
        report_lines.extend(["", "DCF output is unavailable until positive base FCF and shares outstanding are available and assumptions pass validation."])
    report_lines.extend(
        [
            "",
            "## Economic outlook",
            "",
            macro_summary or "Macro commentary is unavailable until a FRED API key is configured and the dashboard series are retrieved.",
            "",
            "## Key risks",
            "",
            "- Historical SEC facts may use issuer-specific fiscal calendars and XBRL tags; comparability should be reviewed before making decisions.",
            "- DCF value is sensitive to WACC, terminal growth, and the starting FCF; small changes can materially affect implied value.",
            "- The model does not provide a market-price target or recommendation without a separately sourced market-price feed.",
            "",
            "## Investment thesis framework",
            "",
            "The thesis should be built by comparing actual operating trends (growth, margins, returns, and FCF) with the valuation assumptions required to support the modeled equity value. This platform deliberately leaves unsupported fields blank rather than fabricating a conclusion.",
            "",
            "## Sources and methodology",
            "",
            "- U.S. Securities and Exchange Commission EDGAR Company Facts API and ticker directory.",
            "- Federal Reserve Bank of St. Louis FRED API, when configured.",
            "- DCF methodology: unlevered FCF discounted at WACC, with terminal value using the Gordon Growth method.",
        ]
    )
    return "\n".join(report_lines)
