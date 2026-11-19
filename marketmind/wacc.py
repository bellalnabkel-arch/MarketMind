"""CAPM equity cost and after-tax market-value-weighted cost of capital."""
from math import isfinite
from .exceptions import ModelValidationError

def calculate_wacc(risk_free, beta, equity_risk_premium, cost_of_debt, equity_weight, tax_rate):
    values = (risk_free, beta, equity_risk_premium, cost_of_debt, equity_weight, tax_rate)
    if not all(isfinite(v) for v in values) or not 0 <= equity_weight <= 1 or not 0 <= tax_rate < 1 or cost_of_debt < 0 or equity_risk_premium < 0:
        raise ModelValidationError("Invalid WACC assumptions.")
    cost_equity = risk_free + beta * equity_risk_premium
    wacc = equity_weight * cost_equity + (1 - equity_weight) * cost_of_debt * (1 - tax_rate)
    return cost_equity, wacc
