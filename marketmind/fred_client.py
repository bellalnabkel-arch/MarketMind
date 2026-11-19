"""FRED observations; CPI is transformed to year-over-year percent change."""
import re
from io import StringIO, BytesIO
from zipfile import ZipFile, is_zipfile
from datetime import datetime, timezone
import pandas as pd
import requests
from .config import FRED_API_URL, FRED_SERIES, SETTINGS
from .exceptions import DataSourceError, FREDConfigurationError
from .regions import REGIONAL_SERIES

def allowed_series(series_id):
    return series_id in set(FRED_SERIES.values()) | REGIONAL_SERIES

def read_official_csv_download(content):
    """FRED bundles mixed-frequency downloads as a ZIP of CSV files."""
    if isinstance(content, str):
        content = content.encode()
    if len(content) > 30 * 1024 * 1024:
        raise ValueError("FRED download exceeds the supported size.")
    if is_zipfile(BytesIO(content)):
        with ZipFile(BytesIO(content)) as archive:
            members = [i for i in archive.infolist() if i.filename.lower().endswith('.csv')]
            if len(members) > 200 or sum(i.file_size for i in members) > 50 * 1024 * 1024:
                raise ValueError("FRED archive exceeds the supported size.")
            return [pd.read_csv(BytesIO(archive.read(i)), na_values=['.']) for i in members]
    return [pd.read_csv(BytesIO(content), na_values=['.'])]
class FREDClient:
    def __init__(self, api_key=None):
        self.api_key = SETTINGS.fred_api_key if api_key is None else api_key
    @property
    def configured(self):
        return True  # Official CSV retrieval works without credentials.
    def series_observations(self, series_id, start_date="2016-01-01"):
        if not allowed_series(series_id):
            raise DataSourceError("Unsupported FRED series.")
        # FRED's published CSV downloads are available without an API key.
        # A configured API key opts into the JSON API; failures fall back to CSV.
        if not self.api_key or not re.fullmatch(r"[A-Za-z0-9]{32}", self.api_key):
            return self.csv_observations(series_id, start_date)
        try:
            return self.api_observations(series_id, start_date)
        except DataSourceError:
            return self.csv_observations(series_id, start_date)

    def api_observations(self, series_id, start_date):
        params = {"api_key": self.api_key, "series_id": series_id, "file_type": "json", "observation_start": start_date, "units": "pc1" if series_id == "CPIAUCSL" else "lin"}
        try:
            response = requests.get(FRED_API_URL + "/series/observations", params=params, timeout=25)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            # Request exceptions may contain the API key in their URL.
            raise DataSourceError("FRED request failed. Check your key or try again later.") from None
        except ValueError:
            raise DataSourceError("FRED returned unreadable JSON.") from None
        observations = payload.get("observations")
        if not isinstance(observations, list):
            raise DataSourceError("FRED returned no observations.")
        frame = pd.DataFrame(observations)
        if frame.empty:
            return pd.DataFrame(columns=["date", "value", "series_id"])
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        frame["series_id"] = series_id
        return self._with_source(frame[["date", "value", "series_id"]].dropna(subset=["date", "value"]), series_id, "FRED API")

    @staticmethod
    def _with_source(frame, series_id, method):
        if frame.empty:
            raise DataSourceError("No valid FRED observations are available.")
        frame.attrs.update({"source": method, "source_url": f"https://fred.stlouisfed.org/series/{series_id}", "retrieved_at": datetime.now(timezone.utc).isoformat()})
        return frame

    def csv_observations(self, series_id, start_date="2016-01-01"):
        """Retrieve the official graph CSV and derive CPI YoY from 12 calendar months."""
        if not allowed_series(series_id):
            raise DataSourceError("Unsupported FRED series.")
        start = pd.Timestamp(start_date)
        request_start = start - pd.DateOffset(years=1) if series_id == "CPIAUCSL" else start
        try:
            response = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series_id, "cosd": request_start.strftime("%Y-%m-%d")}, timeout=25)
            response.raise_for_status()
            raw = pd.read_csv(StringIO(response.text), na_values=["."])
            date_column = "observation_date" if "observation_date" in raw else "DATE"
            if date_column not in raw or series_id not in raw:
                raise ValueError("Unexpected FRED CSV columns.")
            frame = pd.DataFrame({"date": pd.to_datetime(raw[date_column], errors="coerce"), "value": pd.to_numeric(raw[series_id], errors="coerce")}).dropna(subset=["date"])
            frame = frame.drop_duplicates("date", keep="last").sort_values("date")
            if series_id == "CPIAUCSL" and not frame.empty:
                # Reindex so a missing month never becomes a false 12-month comparison.
                monthly = frame.set_index("date")["value"].reindex(pd.date_range(frame.date.min(), frame.date.max(), freq="MS"))
                frame = (monthly / monthly.shift(12) - 1).mul(100).rename_axis("date").reset_index(name="value")
            frame = frame.loc[frame.date >= start].dropna(subset=["value"]).reset_index(drop=True)
            frame["series_id"] = series_id
        except (requests.RequestException, ValueError, KeyError, TypeError, pd.errors.ParserError):
            raise DataSourceError("FRED data is temporarily unavailable. Automatic retrieval will retry shortly.") from None
        return self._with_source(frame, series_id, "FRED official CSV")

    def batch_csv_observations(self, series_ids, start_date="2015-01-01"):
        """One official request for many series. Each frame retains its own dates."""
        if not series_ids or not all(allowed_series(s) for s in series_ids):
            raise DataSourceError("Unsupported FRED series.")
        try:
            if len(series_ids) > 12:
                raise ValueError("FRED graph downloads support at most 12 requested lines per batch.")
            start = pd.Timestamp(start_date)
            request_start = start - pd.DateOffset(years=1) if 'CPIAUCSL' in series_ids else start
            response = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": ','.join(series_ids), "cosd": request_start.strftime('%Y-%m-%d')}, timeout=25)
            response.raise_for_status()
            tables = read_official_csv_download(response.content)
            result = {}
            for raw in tables:
                date_column = 'observation_date' if 'observation_date' in raw else 'DATE'
                if date_column not in raw: continue
                for series_id in series_ids:
                    if series_id not in raw: continue
                    frame = pd.DataFrame({'date':pd.to_datetime(raw[date_column], errors='coerce'), 'value':pd.to_numeric(raw[series_id], errors='coerce')}).dropna().drop_duplicates('date').sort_values('date')
                    if series_id == 'CPIAUCSL' and not frame.empty:
                        monthly = frame.set_index('date')['value'].reindex(pd.date_range(frame.date.min(),frame.date.max(),freq='MS'))
                        frame = ((monthly / monthly.shift(12)-1)*100).rename_axis('date').reset_index(name='value').dropna()
                    frame = frame.loc[frame.date >= start].reset_index(drop=True)
                    frame['series_id'] = series_id
                    if not frame.empty: result[series_id] = self._with_source(frame.reset_index(drop=True), series_id, 'FRED official CSV')
            return result
        except (requests.RequestException, ValueError, KeyError, TypeError, pd.errors.ParserError):
            raise DataSourceError("The regional FRED download is temporarily unavailable.") from None
