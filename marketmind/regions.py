"""US geography and official FRED state-series identifiers; no estimated values."""
STATES = {
    "AL":"Alabama", "AK":"Alaska", "AZ":"Arizona", "AR":"Arkansas", "CA":"California",
    "CO":"Colorado", "CT":"Connecticut", "DE":"Delaware", "DC":"District of Columbia", "FL":"Florida",
    "GA":"Georgia", "HI":"Hawaii", "ID":"Idaho", "IL":"Illinois", "IN":"Indiana", "IA":"Iowa",
    "KS":"Kansas", "KY":"Kentucky", "LA":"Louisiana", "ME":"Maine", "MD":"Maryland", "MA":"Massachusetts",
    "MI":"Michigan", "MN":"Minnesota", "MS":"Mississippi", "MO":"Missouri", "MT":"Montana", "NE":"Nebraska",
    "NV":"Nevada", "NH":"New Hampshire", "NJ":"New Jersey", "NM":"New Mexico", "NY":"New York",
    "NC":"North Carolina", "ND":"North Dakota", "OH":"Ohio", "OK":"Oklahoma", "OR":"Oregon",
    "PA":"Pennsylvania", "RI":"Rhode Island", "SC":"South Carolina", "SD":"South Dakota", "TN":"Tennessee",
    "TX":"Texas", "UT":"Utah", "VT":"Vermont", "VA":"Virginia", "WA":"Washington", "WV":"West Virginia",
    "WI":"Wisconsin", "WY":"Wyoming",
}
def state_series(code):
    if code not in STATES:
        raise ValueError("Unknown US state.")
    return {"Unemployment rate": code+"UR", "Real GDP level": code+"RQGSP", "Nonfarm payroll employment": code+"NA"}

REGIONAL_SERIES = {series for code in STATES for series in state_series(code).values()}
NATIONAL_ONLY = {"CPI inflation · YoY", "Effective federal funds rate · daily", "Fed target range · lower", "Fed target range · upper", "10-year Treasury yield"}

def quarterly_growth(frame):
    """Annualized q/q real GDP growth, with no bridging of missing quarters."""
    import pandas as pd
    result = frame.sort_values("date").copy()
    result['date'] = pd.to_datetime(result['date'], errors='coerce')
    result['value'] = pd.to_numeric(result['value'], errors='coerce')
    gap = result.date.diff().dt.days
    previous = result.value.shift()
    result["value"] = (((result.value / previous) ** 4 - 1) * 100).where(gap.between(75, 105) & (previous > 0))
    return result.dropna(subset=["value"]).reset_index(drop=True)

def format_macro_value(series_id, value):
    if value is None:
        return "Unavailable"
    if series_id == "GDPC1":
        return f"${value:,.1f}B"
    if series_id.endswith("RQGSP"):
        return f"${value / 1000:,.1f}B"
    if series_id == "PAYEMS" or series_id.endswith("NA"):
        return f"{value / 1000:,.2f}M jobs"
    return f"{value:.2f}%"

def series_units(series_id):
    if series_id == "GDPC1": return "Billions of chained 2017 dollars · quarterly SAAR"
    if series_id.endswith("RQGSP"): return "Millions of chained 2017 dollars · quarterly SAAR"
    if series_id == "PAYEMS" or series_id.endswith("NA"): return "Thousands of persons · monthly, seasonally adjusted"
    if series_id == "CPIAUCSL": return "Year-over-year percent · monthly, seasonally adjusted CPI"
    if series_id == "A191RL1Q225SBEA": return "Annualized quarter-over-quarter percent · seasonally adjusted"
    return "Percent · " + ("monthly, seasonally adjusted" if series_id.endswith("UR") or series_id == "UNRATE" else "daily; last available published observation")
