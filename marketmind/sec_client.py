"""SEC HTTP client with explicit request identity, timeouts and request pacing."""
import re
import threading
import time
import requests
from urllib.parse import urlparse
from .config import SEC_DATA_URL, SETTINGS, DEFAULT_SEC_USER_AGENT
from .exceptions import DataSourceError
_lock = threading.Lock()
_last_request = 0.0
def validate_identity(value: str) -> str:
    value = value.strip()
    email = re.fullmatch(r".{2,}\s+[^\s@]+@[^\s@]+\.[^\s@]+", value)
    urls = re.findall(r"https://[^\s)]+", value)
    project = any(urlparse(url).hostname and urlparse(url).path.strip('/') for url in urls)
    placeholder = any(part in value.lower() for part in ("@example.", "@domain.com", "your_real_email", "@your-domain.com"))
    if len(value) > 250 or not value.isascii() or "\r" in value or "\n" in value or not (email or (project and value.startswith("MarketMind"))) or placeholder:
        raise DataSourceError("The app's SEC_USER_AGENT setting is invalid. The owner should replace its placeholder with a real contact identity or remove it to use MarketMind's declared project identity.", code="configuration")
    return value

def resolve_identity(value=None):
    return validate_identity(value.strip() if value and value.strip() else DEFAULT_SEC_USER_AGENT)

class SECClient:
    def __init__(self, user_agent: str | None = None):
        self.user_agent = resolve_identity(SETTINGS.sec_user_agent if user_agent is None else user_agent)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent, "Accept": "application/json"})
    def _get_json(self, url: str) -> dict:
        global _last_request
        with _lock:
            time.sleep(max(0, .25 - (time.monotonic() - _last_request)))
            _last_request = time.monotonic()
        try:
            response = self.session.get(url, timeout=SETTINGS.request_timeout_seconds)
            response.raise_for_status()
            value = response.json()
        except requests.RequestException as exc:
            code = exc.response.status_code if exc.response is not None else "unavailable"
            kind = "access_restricted" if code == 403 else "rate_limited" if code == 429 else "not_found" if code == 404 else "network"
            raise DataSourceError(f"SEC request failed ({code}).", code=kind, status=code) from None
        except ValueError:
            raise DataSourceError("SEC returned unreadable JSON.") from None
        if not isinstance(value, dict):
            raise DataSourceError("SEC returned an unexpected response.")
        return value
    @staticmethod
    def _cik(cik: str) -> str:
        if not str(cik).isdigit() or len(str(cik)) > 10 or int(cik) <= 0:
            raise DataSourceError("Invalid SEC CIK.")
        return str(cik).zfill(10)
    def company_facts(self, cik: str) -> dict:
        return self._get_json(f"{SEC_DATA_URL}/api/xbrl/companyfacts/CIK{self._cik(cik)}.json")
    def submissions(self, cik: str) -> dict:
        return self._get_json(f"{SEC_DATA_URL}/submissions/CIK{self._cik(cik)}.json")
