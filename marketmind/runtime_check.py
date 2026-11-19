"""A small real JavaScript-to-Python round trip for deployment diagnostics."""
import streamlit as st
from streamlit.components.v2 import component

_ping = component(
    "marketmind.runtime_check",
    html='<button type="button" id="ping">Test JavaScript → Python connection</button><span id="status" aria-live="polite"></span>',
    css='button { padding: .65rem .9rem; border: 1px solid #2f78e6; border-radius: 7px; background: white; color: #2468c7; cursor: pointer; font: 14px sans-serif; } span { margin-left: 12px; font: 12px sans-serif; color: #667085; }',
    js='''export default function(component) {
      const {data, parentElement, setTriggerValue} = component;
      const button = parentElement.querySelector('#ping');
      const handler = () => { setTriggerValue('ping', {nonce:data.nonce, browser_time:new Date().toISOString()}); parentElement.querySelector('#status').textContent = 'Browser event sent.'; };
      button.addEventListener('click', handler);
      return () => button.removeEventListener('click', handler);
    }''',
)

def runtime_check(nonce):
    return _ping(key="runtime_ping", data={"nonce": nonce}, on_ping_change=lambda: None)
