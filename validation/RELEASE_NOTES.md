# MarketMind 0.4.0 validation and changes

This release updates the existing Python/Streamlit application. It does not
rebuild it in Sites, and preparing this package does not change the hosted
GitHub/Streamlit deployment.

## SEC retrieval

The previous implementation rejected a missing SEC_USER_AGENT before making
an HTTP request, then displayed the same provider-outage message as network
failures. An unset override now uses a declared public project identity.
Invalid explicit overrides produce an actionable configuration message.
HTTP 403, 429, 404, network and parsing failures have distinct diagnostics.
Previously fetched figures retain their dates during outages. Provider access
restrictions on a particular host still require resolution by its operator.
No hosted Streamlit logs were available to establish the cause on that host.

The financial extractor now covers PaymentsToAcquireProductiveAssets as an
additional reported capex tag, including the real NVDA and AMZN responses.
Unavailable bank cash-flow metrics remain unavailable.

## Economic dashboard

Nine national series and 153 regional series cover 50 states and D.C. The map
supports dated hover values and state clicks; the keyboard-accessible
Geography control provides the same scope selection. State detail includes
unemployment, real GDP level, derived annualized quarterly GDP growth, and
nonfarm employment. Regional downloads respect FRED's 12-series graph limit
and parse mixed-frequency ZIP downloads without extracting archive members.

National policy rates, Treasury yields and national CPI are explicitly labeled
as national context. Regional/metro CPI is not represented as statewide CPI.
Statewide CPI is not consistently available for every state.

National and state caches expire after 300 seconds; the open app checks each
minute, and reopening refreshes expired data. These checks reflect published
provider data and revisions, not instantaneous Fed announcement delivery or
background execution while a hosted app is asleep. Daily policy target bounds
and effective fed funds rates replace the monthly effective-rate series.

## Readability and browser compatibility

Stronger body text, labels, captions and sidebar text improve contrast. Caption
opacity is set to 1 after browser inspection found Streamlit applied 0.6.
The sensitivity heatmap uses dark labels on light cells. Daily Plotly histories
use SVG after browser review exposed WebGL-unavailable errors.

## Verification

- 49 automated tests passed, including company search, official-directory CIKs,
  financial/DCF calculations, automatic data loading, isolation, provider-error
  paths, cache refresh, mixed-frequency downloads, regional coverage and colors.
- The separately dated LIVE_AUDIT.json records successful real SEC retrieval
  for AAPL, TSLA, NVDA, MSFT, JPM, AMZN and GOOGL; nine national and 153 regional
  FRED series; and 42 AppTest navigation/scope checks reusing those real responses.
- A real Python Streamlit server started and returned HTTP 200 for its app and
  health endpoints.
- Browser checks confirmed automatic Apple data retrieval, readable captions
  at full opacity, map hover details, and a California click opening state detail.
- Dependency deprecation warnings came from Streamlit's Pandas/NumPy time
  conversion; they did not cause test failures.

## Principal files

New: marketmind/regions.py, marketmind/regional_data.py,
marketmind/macro_dashboard.py, marketmind/map_interaction.py,
tests/test_regions_and_diagnostics.py, scripts/live_audit.py, and validation files.

Modified: app.py, marketmind/config.py, marketmind/sec_client.py,
marketmind/data_service.py, marketmind/financials.py, marketmind/fred_client.py,
marketmind/exceptions.py, marketmind/ui.py, marketmind/__init__.py,
.streamlit/config.toml, existing automatic-data tests, README.md,
secrets.example.toml, .env.example and render.yaml.

To deploy, replace the repository contents with the extracted project contents
and commit to the Streamlit deployment branch. Keep app.py at the configured
main-file path. Do not upload the ZIP itself, real secrets, or a virtual environment.
Remove any old placeholder SEC_USER_AGENT secret or replace it with a real
monitored contact; a missing override now works automatically.
