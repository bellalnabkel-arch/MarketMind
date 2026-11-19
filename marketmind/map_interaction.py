"""Bridge Plotly's geographic click event to Streamlit's selected geography.

Streamlit exposes selection events, but choropleth clicks do not reliably emit a
selection event. This small V2 component listens to plotly_click on our own
keyed chart container. It adds no dependencies and sends only a state code.
The native Geography selectbox remains the accessible fallback.
"""
import streamlit as st
from .regions import STATES

MAP_CLICK_JS = """
export default function({setTriggerValue}) {
    let chart = null;
    const clicked = event => {
        const point = event?.points?.[0];
        const code = point?.location || point?.customdata?.[0];
        if (typeof code === 'string' && /^[A-Z]{2}$/.test(code)) {
            setTriggerValue('state_click', code);
        }
    };
    const connect = () => {
        const next = document.querySelector('.st-key-mm_state_map .js-plotly-plot');
        if (next === chart || typeof next?.on !== 'function') return;
        if (chart) chart.removeListener('plotly_click', clicked);
        chart = next;
        chart.on('plotly_click', clicked);
    };
    const observer = new MutationObserver(connect);
    observer.observe(document.querySelector('[data-testid="stMain"]') || document.body,
                     {childList:true, subtree:true});
    connect();
    return () => {
        observer.disconnect();
        if (chart) chart.removeListener('plotly_click', clicked);
    };
}
"""

_click_bridge = st.components.v2.component('marketmind_state_map_click', js=MAP_CLICK_JS)


def _selected():
    event = st.session_state.get('macro_map_click') or {}
    code = event.get('state_click')
    if code in STATES:
        st.session_state.macro_geography = code


def enable_map_clicks():
    """Register a callback before the next rerun creates the geography widget."""
    _click_bridge(key='macro_map_click', on_state_click_change=_selected)
