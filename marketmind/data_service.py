"""Automatic public-data loading, TTL caching, stale-data retention and retry control.

Credentials stay server-side. Only public provider results enter shared caches;
selections, model inputs, errors and attempt state remain session-specific.
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone

import streamlit as st

from .analytics import calculate_metrics
from .config import FRED_SERIES
from .exceptions import MarketMindError
from .financials import build_annual_financials
from .fred_client import FREDClient
from .sec_client import SECClient, resolve_identity

TTL_SECONDS = 3600
MACRO_TTL_SECONDS = 300
RETRY_SECONDS = 60
logger = logging.getLogger(__name__)

def _identity_token(value):
    return hashlib.sha256(value.encode()).hexdigest()

def _fresh(timestamp, now, ttl=TTL_SECONDS):
    try:
        return -300 <= now - datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp() < ttl
    except (AttributeError, TypeError, ValueError):
        return False

@st.cache_data(ttl=TTL_SECONDS, max_entries=32, show_spinner=False)
def sec_snapshot(cik, identity_token, _user_agent):
    # The token separates configurations without exposing the contact in a cache key.
    del identity_token
    payload = SECClient(_user_agent).company_facts(cik)
    return {"payload": payload, "retrieved_at": datetime.now(timezone.utc).isoformat()}

@st.cache_data(ttl=MACRO_TTL_SECONDS, max_entries=40, show_spinner=False)
def fred_snapshot(series_id, source_mode, _api_key):
    del source_mode
    if not _api_key:
        frames = national_snapshot()
        if series_id not in frames:
            from .exceptions import DataSourceError
            raise DataSourceError('No observations returned for this national series.')
        return frames[series_id]
    return FREDClient(_api_key).series_observations(series_id)

@st.cache_data(ttl=MACRO_TTL_SECONDS, max_entries=1, show_spinner=False)
def national_snapshot():
    return FREDClient('').batch_csv_observations(list(FRED_SERIES.values()))

def _retry_allowed(attempts, key, now):
    return now - attempts.get(key, -float("inf")) >= RETRY_SECONDS

def _record_attempt(attempts, key, now):
    attempts[key] = now
    while len(attempts) > 64:
        del attempts[next(iter(attempts))]

def ensure_financial_data(state, company, user_agent, *, now=None):
    """Called before rendering any company section; no visitor load action needed."""
    if not company:
        return "idle"
    now = time.time() if now is None else now
    cik = company["cik"]
    try:
        user_agent = resolve_identity(user_agent)
    except MarketMindError as exc:
        state["sec_error_code"] = "configuration"
        state["sec_error"] = str(exc)
        return "configuration"
    source = state.get("financial_source") or {}
    if source.get("cik") == cik and _fresh(source.get("retrieved_at"), now):
        return "ready"
    attempts = state.setdefault("sec_attempts", {})
    key = (cik, _identity_token(user_agent))
    if not _retry_allowed(attempts, key, now):
        return "unavailable" if state.get("sec_error") else "ready"
    _record_attempt(attempts, key, now)
    try:
        snapshot = sec_snapshot(cik, key[1], _user_agent=user_agent)
        payload = snapshot["payload"]
        if not isinstance(payload, dict) or str(payload.get("cik", "")).zfill(10) != cik:
            raise ValueError("SEC Company Facts CIK did not match the selection.")
        metrics = calculate_metrics(build_annual_financials(payload))
        if metrics.empty:
            state["sec_error"] = "No supported annual US-GAAP financial facts in USD are available for this company."
            return "unsupported"
    except (MarketMindError, ValueError, TypeError, KeyError) as exc:
        # Log only the exception class, never contacts, keys or request URLs.
        logger.warning("Automatic SEC retrieval failed for CIK %s (%s). Check SEC_USER_AGENT in hosting secrets and provider availability.", cik, type(exc).__name__)
        code = getattr(exc, "code", "parsing")
        messages = {
            "access_restricted": "SEC is refusing requests from this hosting server (HTTP 403). Automatic retries cannot guarantee access; the app owner needs to resolve the SEC access restriction. Previously retrieved figures remain dated below.",
            "rate_limited": "SEC has rate-limited this server (HTTP 429). MarketMind will retry after the cooldown.",
            "not_found": "SEC has no Company Facts response for this company's CIK (HTTP 404).",
            "network": "The SEC connection failed or timed out. MarketMind will retry automatically; previously retrieved data remains dated below.",
            "parsing": "The SEC response could not be matched to supported financial statements. Existing figures remain dated below.",
        }
        state["sec_error_code"] = code
        state["sec_error"] = messages.get(code, "SEC financial data is unavailable. MarketMind will retry automatically.")
        return "unavailable"
    state["facts"] = payload
    state["metrics"] = metrics
    state["financial_source"] = {"retrieved_at": snapshot["retrieved_at"], "imported": False, "cik": cik}
    state["sec_error"] = None
    state["sec_error_code"] = None
    return "ready"

def ensure_macro_data(state, api_key="", *, now=None):
    """Load/refresh series independently so one provider error cannot blank the page."""
    now = time.time() if now is None else now
    macro = state.setdefault("macro", {})
    sources = state.setdefault("macro_sources", {})
    errors = state.setdefault("macro_errors", {})
    attempts = state.setdefault("macro_attempts", {})
    for label, series_id in FRED_SERIES.items():
        if label in macro and not macro[label].empty and _fresh(sources.get(label, {}).get("retrieved_at"), now, MACRO_TTL_SECONDS):
            continue
        key = (series_id, _identity_token(api_key))
        if not _retry_allowed(attempts, key, now):
            continue
        _record_attempt(attempts, key, now)
        try:
            frame = fred_snapshot(series_id, "api" if api_key else "csv", _api_key=api_key)
            if frame.empty:
                raise ValueError("No valid observations.")
        except (MarketMindError, ValueError, KeyError, TypeError):
            errors[label] = "Temporarily unavailable; automatic retrieval will retry shortly."
            continue
        macro[label] = frame
        sources[label] = dict(frame.attrs)
        errors.pop(label, None)
    return not errors
