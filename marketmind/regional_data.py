"""Batched regional retrieval, date-aware snapshots and cache policy."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import time
import pandas as pd
import streamlit as st
from .fred_client import FREDClient
from .regions import STATES, state_series, quarterly_growth
from .data_service import _fresh, MACRO_TTL_SECONDS, RETRY_SECONDS

@st.cache_data(ttl=MACRO_TTL_SECONDS, max_entries=2, show_spinner=False)
def regional_snapshot():
    ids = [state_series(code)[metric] for code in STATES for metric in ('Unemployment rate', 'Real GDP level', 'Nonfarm payroll employment')]
    # FRED silently truncates larger graph requests to 12 lines.
    groups = [ids[i:i+12] for i in range(0,len(ids),12)]
    frames, errors = {}, []
    # Only raw HTTP/CSV work runs in threads; Streamlit UI stays on the main thread.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(FREDClient('').batch_csv_observations, ids) for ids in groups]
        for future in as_completed(futures):
            try: frames.update(future.result())
            except Exception: errors.append('A regional dataset is temporarily unavailable.')
    missing = set(ids) - set(frames)
    if missing:
        errors.append(f'{len(missing)} regional series are currently unavailable; their map fields remain blank.')
    return {'frames':frames, 'errors':errors, 'retrieved_at':datetime.now(timezone.utc).isoformat()}

def ensure_regional_data(state, *, now=None):
    now = time.time() if now is None else now
    current = state.get('regional_data') or {}
    if current.get('frames') and _fresh(current.get('retrieved_at'), now, MACRO_TTL_SECONDS): return current
    if now - state.get('regional_attempt', -float('inf')) < RETRY_SECONDS: return current
    state['regional_attempt'] = now
    try:
        result = regional_snapshot()
        if result['frames']:
            # Partial refreshes retain dated observations for any missing series.
            result['frames'] = {**current.get('frames', {}), **result['frames']}
            state['regional_data'] = result
        state['regional_error'] = '; '.join(result.get('errors', []))
    except Exception:
        state['regional_error'] = 'Regional economic data is temporarily unavailable; dated data is retained when available.'
    return state.get('regional_data') or {}

def latest(frame):
    if frame is None or frame.empty: return None, None
    clean = frame.dropna(subset=['value']).sort_values('date')
    if clean.empty: return None, None
    row = clean.iloc[-1]
    return float(row.value), str(row.date.date())

def state_observations(frames, code):
    items = {}
    for label, series_id in state_series(code).items():
        frame = frames.get(series_id, pd.DataFrame(columns=['date','value']))
        items[label] = {'series_id':series_id, 'frame':frame, 'value':latest(frame)[0], 'date':latest(frame)[1]}
        if label == 'Real GDP level':
            growth = quarterly_growth(frame)
            items['Real GDP growth'] = {'series_id':series_id, 'frame':growth, 'value':latest(growth)[0], 'date':latest(growth)[1]}
    return items

def map_table(frames):
    rows=[]
    for code, name in STATES.items():
        values=state_observations(frames, code)
        u=values['Unemployment rate'];g=values['Real GDP growth'];jobs=values['Nonfarm payroll employment']
        rows.append({'code':code,'state':name,'unemployment':u['value'],'unemployment_date':u['date'] or 'Unavailable','gdp_growth':g['value'],'gdp_date':g['date'] or 'Unavailable','jobs_millions':jobs['value']/1000 if jobs['value'] is not None else None,'jobs_date':jobs['date'] or 'Unavailable'})
    return pd.DataFrame(rows)
