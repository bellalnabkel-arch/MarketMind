"""Null-preserving financial ratios based on adjacent reporting periods."""
import numpy as np
import pandas as pd
def calculate_metrics(financials):
    if financials.empty:
        return financials.copy()
    result = financials.sort_values("period_end").reset_index(drop=True).copy()
    gap = pd.to_datetime(result.period_end).diff().dt.days
    adjacent = gap.between(330, 380)
    previous = result.revenue.shift()
    result["revenue_growth"] = (result.revenue / previous - 1).where(adjacent & (previous > 0))
    for name, numerator in {"ebitda_margin": "ebitda", "operating_margin": "operating_income", "net_margin": "net_income", "fcf_margin": "free_cash_flow"}.items():
        result[name] = result[numerator] / result.revenue.replace(0, np.nan)
    for name, denominator in {"roe": "equity", "roa": "assets"}.items():
        average = (result[denominator] + result[denominator].shift()) / 2
        result[name] = (result.net_income / average).where(adjacent & (average > 0))
    return result

def latest_metrics(metrics):
    if metrics.empty:
        return {}
    row = metrics.iloc[-1]
    return {key: (None if pd.isna(value) else value.item() if hasattr(value, "item") else value) for key, value in row.items()}
