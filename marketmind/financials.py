"""Conservative annual US-GAAP/USD extraction with per-fact provenance.

Comparative facts are grouped by their actual end date, never by the fiscal
year of the filing that repeats them. Missing concepts are never imputed.
"""
import math
from datetime import date
import pandas as pd

DURATION_TAGS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "Revenues"),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss",),
    "depreciation_amortization": ("DepreciationDepletionAndAmortization", "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment", "DepreciationAmortizationAndAccretionNet"),
    "cash_from_operations": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
}
INSTANT_TAGS = {
    "assets": ("Assets",), "equity": ("StockholdersEquity",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "shares_outstanding": ("CommonStockSharesOutstanding",),
}
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}

def _records(facts, tags, instant=False, unit="USD"):
    result = {}
    for tag in tags:
        candidates = {}
        for r in facts.get("us-gaap", {}).get(tag, {}).get("units", {}).get(unit, []):
            try:
                end = date.fromisoformat(r["end"])
                date.fromisoformat(r["filed"])
                val = float(r["val"])
                if not math.isfinite(val) or r.get("form") not in ANNUAL_FORMS:
                    continue
                if not instant and not 330 <= (end - date.fromisoformat(r["start"])).days <= 380:
                    continue
            except (ValueError, TypeError, KeyError):
                continue
            previous = candidates.get(r["end"])
            if previous is None or (r["filed"], r.get("accn", "")) > (previous["filed"], previous.get("accn", "")):
                candidates[r["end"]] = {**r, "tag": tag}
        for end, r in candidates.items():
            result.setdefault(end, r)
    return result

def build_annual_financials(company_facts: dict) -> pd.DataFrame:
    if not isinstance(company_facts.get("facts"), dict):
        raise ValueError("Expected an original SEC Company Facts JSON.")
    facts = company_facts["facts"]
    series = {metric: _records(facts, tags) for metric, tags in DURATION_TAGS.items()}
    ends = sorted({end for records in series.values() for end in records})
    series.update({metric: _records(facts, tags, True, "shares" if metric == "shares_outstanding" else "USD") for metric, tags in INSTANT_TAGS.items()})
    rows = []
    for end in ends:
        row = {"period_end": end, "fiscal_year": int(end[:4]), "currency": "USD"}
        for metric, records in series.items():
            r = records.get(end, {})
            row[metric] = float(r["val"]) if r else float("nan")
            row[metric + "_tag"] = r.get("tag")
            row[metric + "_filed"] = r.get("filed")
            row[metric + "_accession"] = r.get("accn")
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).tail(10).reset_index(drop=True)
    frame["ebitda"] = frame.operating_income + frame.depreciation_amortization
    frame["free_cash_flow"] = frame.cash_from_operations - frame.capex
    return frame

def latest_value(frame, column):
    if frame.empty or column not in frame or pd.isna(frame.iloc[-1][column]):
        return None
    return float(frame.iloc[-1][column])

def latest_filed_date(company_facts):
    dates = [r.get("filed", "") for taxonomy in company_facts.get("facts", {}).values() for concept in taxonomy.values() for unit in concept.get("units", {}).values() for r in unit if isinstance(r, dict)]
    return max(dates, default=None)
