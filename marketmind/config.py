"""Environment defaults; Streamlit secrets and per-session inputs are handled by app.py."""
import os
from dotenv import load_dotenv
load_dotenv()
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_DATA_URL = "https://data.sec.gov"
DEFAULT_SEC_USER_AGENT = "MarketMind/0.4 (+https://github.com/bellalnabkel-arch/MarketMind)"
FRED_API_URL = "https://api.stlouisfed.org/fred"
FRED_SERIES = {
    "CPI inflation · YoY": "CPIAUCSL",
    "Real GDP growth": "A191RL1Q225SBEA",
    "Unemployment rate": "UNRATE",
    "Effective federal funds rate · daily": "DFF",
    "Fed target range · lower": "DFEDTARL",
    "Fed target range · upper": "DFEDTARU",
    "10-year Treasury yield": "DGS10",
    "Nonfarm payroll employment": "PAYEMS",
    "Real GDP level": "GDPC1",
}
class Settings:
    sec_user_agent = os.getenv("SEC_USER_AGENT", "")
    fred_api_key = os.getenv("FRED_API_KEY", "")
    request_timeout_seconds = 25
SETTINGS = Settings()
