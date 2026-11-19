import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests
from streamlit.testing.v1 import AppTest

from marketmind.analytics import calculate_metrics
from marketmind.company_search import CompanyDirectory, CompanyIndex
from marketmind.dcf import DCFInputs, run_dcf, sensitivity_table
from marketmind.exceptions import DataSourceError, ModelValidationError
from marketmind.financials import build_annual_financials
from marketmind.fred_client import FREDClient
from marketmind.wacc import calculate_wacc
from marketmind.config import FRED_SERIES
from marketmind import data_service

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = json.loads((ROOT / "data/sec-directory-cache.json").read_text())
INDEX = CompanyIndex(SNAPSHOT["companies"])

@pytest.mark.parametrize("ticker,cik", [("AAPL", "0000320193"), ("TSLA", "0001318605"), ("NVDA", "0001045810"), ("MSFT", "0000789019"), ("JPM", "0000019617"), ("AMZN", "0001018724"), ("GOOGL", "0001652044")])
def test_official_tickers(ticker, cik):
    assert INDEX.search(ticker)[0]["cik"] == cik
    assert INDEX.search(ticker.lower())[0]["ticker"] == ticker

@pytest.mark.parametrize("query,ticker", [("Apple", "AAPL"), ("Micros", "MSFT"), ("Microsfot", "MSFT"), ("JPMorgan Chase", "JPM"), ("NVDIA", "NVDA"), ("0000320193", "AAPL")])
def test_universal_search(query, ticker):
    assert INDEX.search(query)[0]["ticker"] == ticker

def test_empty_and_invalid_search():
    assert INDEX.search("") == []
    assert INDEX.search("ZZZZZZZZZZZZZZZZ") == []
    assert {c["ticker"] for c in INDEX.search("1652044")} >= {"GOOG", "GOOGL"}

def test_api_failure_uses_official_cache(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr(requests, "get", unavailable)
    data = CompanyDirectory(tmp_path / "cache.json").load("Automated test contact@unit.test", force=True)
    assert len(data["companies"]) == len(SNAPSHOT["companies"])
    assert "failed" in data["warning"]

def test_dcf_direction_and_sensitivity():
    inputs = DCFInputs(base_fcf=100, shares_outstanding=10, cash=20, debt=30, wacc=.1, terminal_growth=.02)
    result = run_dcf(inputs)
    assert len(result.forecast) == 5
    assert result.equity_value == pytest.approx(result.enterprise_value - 10)
    assert sensitivity_table(inputs).loc[.1, .02] == pytest.approx(result.implied_share_price)
    assert run_dcf(DCFInputs(**{**vars(inputs), "wacc": .12})).implied_share_price < result.implied_share_price
    assert run_dcf(DCFInputs(**{**vars(inputs), "fcf_growth": .12})).implied_share_price > result.implied_share_price

def test_dcf_rejects_nan_and_invalid_terminal_growth():
    for overrides in ({"cash": np.nan}, {"wacc": .01}, {"shares_outstanding": 0}):
        with pytest.raises(ModelValidationError):
            run_dcf(DCFInputs(**{**dict(base_fcf=100, shares_outstanding=10, cash=0, debt=0), **overrides}))

def test_wacc():
    ke, wacc = calculate_wacc(.04, 1, .05, .05, .8, .25)
    assert ke == pytest.approx(.09)
    assert wacc == pytest.approx(.0795)

def test_comparative_facts_group_by_period_and_preserve_missing_data():
    records = [{"start": f"{year}-01-01", "end": f"{year}-12-31", "val": value, "fy": 2024, "filed": "2025-02-01", "form": "10-K"} for year, value in [(2022, 80), (2023, 100), (2024, 120)]]
    frame = calculate_metrics(build_annual_financials({"facts": {"us-gaap": {"Revenues": {"units": {"USD": records}}}}}))
    assert len(frame) == 3
    assert frame.iloc[0].period_end == "2022-12-31"
    assert frame.iloc[-1].revenue_growth == pytest.approx(.2)
    assert pd.isna(frame.iloc[-1].free_cash_flow)
    assert pd.isna(frame.iloc[0].roe)

def test_fred_errors_do_not_expose_api_key(monkeypatch):
    key = "a" * 32
    def fail(*args, **kwargs):
        raise requests.ConnectionError("private?api_key=" + key)
    monkeypatch.setattr(requests, "get", fail)
    with pytest.raises(DataSourceError) as err:
        FREDClient(key).series_observations("CPIAUCSL")
    assert key not in str(err.value)

@pytest.fixture
def stub_automatic_providers(monkeypatch):
    from marketmind import regional_data
    from marketmind.regions import REGIONAL_SERIES
    calls = {"sec": [], "fred": []}
    def sec(cik, token, _user_agent):
        calls["sec"].append(cik)
        return {"payload": test_payload(cik), "retrieved_at": pd.Timestamp.now(tz="UTC").isoformat()}
    def fred(series_id, source_mode, _api_key):
        calls["fred"].append(series_id)
        frame = pd.DataFrame({"date": pd.to_datetime(["2024-01-01", "2024-02-01"]), "value": [1.0, 2.0], "series_id": series_id})
        frame.attrs.update({"source": "automated test fixture", "retrieved_at": pd.Timestamp.now(tz="UTC").isoformat()})
        return frame
    monkeypatch.setattr(data_service, "sec_snapshot", sec)
    monkeypatch.setattr(data_service, "fred_snapshot", fred)
    def regional():
        frames = {}
        for series in REGIONAL_SERIES:
            frame = pd.DataFrame({'date':pd.to_datetime(['2024-01-01','2024-04-01']), 'value':[100.,101.], 'series_id':series})
            frame.attrs.update({'source':'automated test fixture','retrieved_at':pd.Timestamp.now(tz='UTC').isoformat()})
            frames[series] = frame
        return {'frames':frames,'errors':[],'retrieved_at':pd.Timestamp.now(tz='UTC').isoformat()}
    monkeypatch.setattr(regional_data, 'regional_snapshot', regional)
    monkeypatch.setenv("SEC_USER_AGENT", "MarketMind test contact@unit.test")
    return calls

def test_payload(cik="0000320193"):
    # Synthetic statement values are isolated to this test suite.
    def records(value):
        return [{"start": f"{year}-01-01", "end": f"{year}-12-31", "val": value, "fy": 2024, "filed": "2025-02-01", "form": "10-K"} for year in [2023, 2024]]
    return {"cik": cik, "entityName": "Test fixture", "facts": {"us-gaap": {"Revenues": {"units": {"USD": records(1000000)}}, "NetIncomeLoss": {"units": {"USD": records(100000)}}}}}

test_payload.__test__ = False

def test_streamlit_search_selection_navigation_without_connection_steps(stub_automatic_providers):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run(timeout=30)
    assert not app.exception
    app.text_input(key="company_query").input("Apple").run()
    assert not app.exception
    app.selectbox(key="company_result").select("AAPL").run()
    assert app.session_state["selected_company"]["cik"] == "0000320193"
    assert not app.session_state["metrics"].empty
    assert stub_automatic_providers["sec"] == ["0000320193"]
    assert "Data connections" not in app.radio(key="workspace").options
    assert all("Load SEC" not in b.label for b in app.button)
    for page in ("Financials", "DCF valuation", "Macro dashboard", "Research report"):
        app.radio(key="workspace").set_value(page).run()
        assert not app.exception, page
        assert app.session_state["selected_company"]["ticker"] == "AAPL"
    assert len(stub_automatic_providers["fred"]) == len(FRED_SERIES)
    assert len(stub_automatic_providers["sec"]) == 1
    assert not app.text_input(key="company_query").value == ""

def test_streamlit_dcf_calculates_in_python(stub_automatic_providers):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run(timeout=30)
    app.radio(key="workspace").set_value("DCF valuation").run()
    for key, value in (("model_fcf", 100.0), ("model_cash", 20.0), ("model_debt", 30.0), ("model_shares", 10.0)):
        app.number_input(key=key).set_value(value)
    app.run()
    assert not app.exception
    assert app.session_state["dcf_result"].implied_share_price > 0
    assert len(app.get("plotly_chart")) == 2
    before = app.session_state["dcf_result"].implied_share_price
    app.radio(key="workspace").set_value("Research report").run()
    app.radio(key="workspace").set_value("DCF valuation").run()
    assert not app.exception
    assert app.number_input(key="model_fcf").value == 100.0
    assert app.session_state["dcf_result"].implied_share_price == pytest.approx(before)
