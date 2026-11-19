"""Regression checks for automatic retrieval, cache TTL, outages and no-key FRED."""
from datetime import datetime, timezone
from io import StringIO
import pandas as pd
import pytest
import requests
from streamlit.testing.v1 import AppTest

from marketmind import data_service as service
from marketmind.config import FRED_SERIES
from marketmind.exceptions import DataSourceError
from marketmind.fred_client import FREDClient
from test_marketmind import ROOT, test_payload, stub_automatic_providers

COMPANY = {"name": "Test fixture", "ticker": "AAPL", "cik": "0000320193"}
AGENT = "MarketMind test contact@unit.test"

def stamp(now):
    return datetime.fromtimestamp(now, timezone.utc).isoformat()

def test_company_retrieval_is_automatic_reused_and_expires(monkeypatch):
    now = [1700000000.0]
    calls = []
    def snapshot(cik, token, _user_agent):
        calls.append(cik)
        return {"payload": test_payload(cik), "retrieved_at": stamp(now[0])}
    monkeypatch.setattr(service, "sec_snapshot", snapshot)
    state = {}
    assert service.ensure_financial_data(state, COMPANY, AGENT, now=now[0]) == "ready"
    assert not state["metrics"].empty
    assert service.ensure_financial_data(state, COMPANY, AGENT, now=now[0] + 10) == "ready"
    assert len(calls) == 1
    now[0] += 3601
    service.ensure_financial_data(state, COMPANY, AGENT, now=now[0])
    assert len(calls) == 2

def test_failure_has_cooldown_and_keeps_last_good_data(monkeypatch):
    now = 1700000000.0
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(1)
        raise DataSourceError("provider offline")
    monkeypatch.setattr(service, "sec_snapshot", unavailable)
    previous = pd.DataFrame({"revenue": [123.]})
    state = {"metrics": previous, "financial_source": {"cik": COMPANY["cik"], "retrieved_at": stamp(now - 4000)}}
    service.ensure_financial_data(state, COMPANY, AGENT, now=now)
    service.ensure_financial_data(state, COMPANY, AGENT, now=now + 20)
    assert len(calls) == 1
    assert state["metrics"].equals(previous)
    service.ensure_financial_data(state, COMPANY, AGENT, now=now + 61)
    assert len(calls) == 2

def test_incorrect_cik_is_never_displayed(monkeypatch):
    monkeypatch.setattr(service, "sec_snapshot", lambda *args, **kwargs: {"payload": test_payload("0000789019"), "retrieved_at": stamp(1700000000)})
    state = {}
    assert service.ensure_financial_data(state, COMPANY, AGENT, now=1700000000) == "unavailable"
    assert "metrics" not in state

def test_default_identity_never_requests_visitor_credentials(monkeypatch, stub_automatic_providers):
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    # Explicit empty setting is deterministic even if the test runner has host secrets.
    monkeypatch.setenv("SEC_USER_AGENT", "")
    app.text_input(key="company_query").input("AAPL").run()
    app.selectbox(key="company_result").select("AAPL").run()
    assert not app.exception
    assert not app.session_state["metrics"].empty
    assert app.session_state["sec_error"] is None
    assert len(app.text_input) == 1
    assert "Data connections" not in app.radio(key="workspace").options

def test_switching_companies_cannot_reuse_previous_financials(stub_automatic_providers):
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    for ticker, cik in [("AAPL", "0000320193"), ("MSFT", "0000789019")]:
        app.text_input(key="company_query").input(ticker).run()
        app.selectbox(key="company_result").select(ticker).run()
        assert not app.exception
        assert app.session_state["financial_source"]["cik"] == cik
    assert stub_automatic_providers["sec"] == ["0000320193", "0000789019"]

def test_macro_autoload_uses_cache_and_keeps_partial_results(monkeypatch):
    calls = []
    def snapshot(series_id, source_mode, _api_key):
        calls.append((series_id, source_mode, _api_key))
        if series_id == "DGS10":
            raise DataSourceError("offline")
        frame = pd.DataFrame({"date": pd.to_datetime(["2024-01-01"]), "value": [1.], "series_id": series_id})
        frame.attrs["retrieved_at"] = stamp(1700000000)
        return frame
    monkeypatch.setattr(service, "fred_snapshot", snapshot)
    state = {}
    service.ensure_macro_data(state, now=1700000000)
    assert len(state["macro"]) == len(FRED_SERIES) - 1
    assert len(state["macro_errors"]) == 1
    service.ensure_macro_data(state, now=1700000020)
    assert len(calls) == len(FRED_SERIES)
    service.ensure_macro_data(state, now=1700000061)
    assert len(calls) == len(FRED_SERIES) + 1
    assert all(mode == "csv" and key == "" for _, mode, key in calls)

def test_global_public_sec_cache_avoids_duplicate_provider_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(service.SECClient, "company_facts", lambda self, cik: calls.append(cik) or test_payload(cik))
    service.sec_snapshot.clear()
    try:
        a, b = {}, {}
        service.ensure_financial_data(a, COMPANY, AGENT)
        service.ensure_financial_data(b, COMPANY, AGENT)
        assert calls == [COMPANY["cik"]]
        assert a["metrics"].equals(b["metrics"])
    finally:
        service.sec_snapshot.clear()

def test_fred_csv_requires_no_api_key_and_preserves_dates(monkeypatch):
    class Response:
        text = "observation_date,UNRATE\n2024-01-01,4.0\n2024-02-01,.\n2024-03-01,4.2\n"
        def raise_for_status(self): pass
    calls = []
    def get(url, params, timeout):
        calls.append((url, params))
        return Response()
    monkeypatch.setattr(requests, "get", get)
    frame = FREDClient("").series_observations("UNRATE", "2024-01-01")
    assert len(frame) == 2
    assert "api_key" not in calls[0][1]
    assert frame.iloc[-1].date == pd.Timestamp("2024-03-01")
    assert frame.attrs["source"] == "FRED official CSV"

def test_cpi_csv_uses_twelve_calendar_months_without_filling_gaps(monkeypatch):
    dates = pd.date_range("2024-01-01", "2025-03-01", freq="MS")
    raw = pd.DataFrame({"observation_date": dates, "CPIAUCSL": [100.] * 12 + [110., 111., 112.]})
    raw = raw.loc[raw.observation_date != pd.Timestamp("2024-02-01")]
    class Response:
        text = raw.to_csv(index=False)
        def raise_for_status(self): pass
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())
    frame = FREDClient("").series_observations("CPIAUCSL", "2025-01-01")
    assert list(frame.date) == [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-03-01")]
    assert list(frame.value) == pytest.approx([10., 12.])

def test_fred_api_failure_uses_official_csv(monkeypatch):
    calls = []
    class Response:
        text = "observation_date,UNRATE\n2024-01-01,4.0\n"
        def raise_for_status(self): pass
    def get(url, params, timeout):
        calls.append(url)
        if "api.stlouisfed.org" in url:
            raise requests.ConnectionError("api_key=private")
        return Response()
    monkeypatch.setattr(requests, "get", get)
    frame = FREDClient("a" * 32).series_observations("UNRATE", "2024-01-01")
    assert len(calls) == 2
    assert frame.attrs["source"] == "FRED official CSV"
