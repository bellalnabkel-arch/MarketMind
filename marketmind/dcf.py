"""Discounted cash-flow model and sensitivity analysis."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .exceptions import ModelValidationError


@dataclass(frozen=True)
class DCFInputs:
    base_fcf: float
    shares_outstanding: float
    cash: float
    debt: float
    fcf_growth: float = 0.08
    wacc: float = 0.09
    terminal_growth: float = 0.025
    forecast_years: int = 5

    def validate(self) -> None:
        if not all(math.isfinite(v) for v in (self.base_fcf, self.shares_outstanding, self.cash, self.debt, self.fcf_growth, self.wacc, self.terminal_growth)):
            raise ModelValidationError("Complete all required inputs with finite numbers.")
        if self.cash < 0 or self.debt < 0 or self.fcf_growth <= -1 or self.wacc <= 0:
            raise ModelValidationError("Cash and debt must be nonnegative; WACC positive; FCF growth above -100%.")
        if self.base_fcf <= 0:
            raise ModelValidationError("Base free cash flow must be greater than zero.")
        if self.shares_outstanding <= 0:
            raise ModelValidationError("Shares outstanding must be greater than zero.")
        if self.forecast_years != 5:
            raise ModelValidationError("This model uses a five-year forecast.")
        if self.wacc <= self.terminal_growth:
            raise ModelValidationError("WACC must be greater than terminal growth.")
        if self.wacc <= -1 or self.terminal_growth <= -1:
            raise ModelValidationError("Growth and discount assumptions are out of range.")


@dataclass(frozen=True)
class DCFResult:
    forecast: pd.DataFrame
    terminal_value: float
    pv_terminal_value: float
    enterprise_value: float
    equity_value: float
    implied_share_price: float
    net_debt: float


def run_dcf(inputs: DCFInputs) -> DCFResult:
    """Run an unlevered FCF DCF using the supplied assumptions."""

    inputs.validate()
    years = np.arange(1, inputs.forecast_years + 1)
    fcf = inputs.base_fcf * np.power(1 + inputs.fcf_growth, years)
    discount_factor = 1 / np.power(1 + inputs.wacc, years)
    pv_fcf = fcf * discount_factor
    forecast = pd.DataFrame({"year": years, "free_cash_flow": fcf, "discount_factor": discount_factor, "present_value": pv_fcf})
    terminal_value = fcf[-1] * (1 + inputs.terminal_growth) / (inputs.wacc - inputs.terminal_growth)
    pv_terminal_value = terminal_value * discount_factor[-1]
    enterprise_value = float(pv_fcf.sum() + pv_terminal_value)
    net_debt = float(inputs.debt - inputs.cash)
    equity_value = enterprise_value - net_debt
    return DCFResult(
        forecast=forecast,
        terminal_value=float(terminal_value),
        pv_terminal_value=float(pv_terminal_value),
        enterprise_value=enterprise_value,
        equity_value=float(equity_value),
        implied_share_price=float(equity_value / inputs.shares_outstanding),
        net_debt=net_debt,
    )


def sensitivity_table(inputs: DCFInputs, wacc_values: list[float] | None = None, terminal_growth_values: list[float] | None = None) -> pd.DataFrame:
    """Return implied share price across WACC and terminal-growth scenarios."""

    wacc_values = wacc_values or [inputs.wacc - 0.02, inputs.wacc - 0.01, inputs.wacc, inputs.wacc + 0.01, inputs.wacc + 0.02]
    terminal_growth_values = terminal_growth_values or [inputs.terminal_growth - 0.01, inputs.terminal_growth - 0.005, inputs.terminal_growth, inputs.terminal_growth + 0.005, inputs.terminal_growth + 0.01]
    rows: dict[float, list[float]] = {}
    for wacc in wacc_values:
        values: list[float] = []
        for terminal_growth in terminal_growth_values:
            scenario = DCFInputs(
                base_fcf=inputs.base_fcf,
                shares_outstanding=inputs.shares_outstanding,
                fcf_growth=inputs.fcf_growth,
                wacc=float(wacc),
                terminal_growth=float(terminal_growth),
                cash=inputs.cash,
                debt=inputs.debt,
                forecast_years=inputs.forecast_years,
            )
            try:
                values.append(run_dcf(scenario).implied_share_price)
            except ModelValidationError:
                values.append(np.nan)
        rows[round(wacc, 4)] = values
    result = pd.DataFrame.from_dict(rows, orient="index", columns=[round(value, 4) for value in terminal_growth_values])
    result.index.name = "WACC"
    result.columns.name = "Terminal growth"
    return result
