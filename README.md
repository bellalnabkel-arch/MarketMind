# MarketMind — Python / Streamlit edition

MarketMind runs a real Python/Streamlit server. Company-directory retrieval, fuzzy matching, SEC extraction, Pandas financial analysis, WACC, DCF and reports execute in Python. Streamlit and Plotly provide browser interactions. No Node.js server is required.

## Automatic data retrieval

There is no Data connections page and no Load SEC / Load FRED step for visitors:

- Select a company; the app automatically retrieves its SEC Company Facts and populates every company section.
- Open Macro dashboard; the app automatically retrieves nine national FRED series and state unemployment, real GDP and nonfarm employment for all 50 states and Washington, D.C. Research reports retrieve national context automatically.
- SEC financials are cached for one hour; national and state economic data expire after five minutes. A live-page timer checks freshness every minute on active pages. Reopening the app refreshes expired data; closed or hibernated apps do not run background checks. Searching and navigating reuse cached results.
- Each company is identified by CIK. Switching companies clears the previous company's data before retrieval, so figures are never shown under the wrong issuer.
- Provider errors trigger a 60-second retry cooldown and retain any previously fetched data with its original retrieval/observation dates. Missing facts remain unavailable; the app never generates placeholder financial data.
- Cash and shares in the DCF are prefilled from available latest annual SEC facts. Unlevered FCF, total debt and forecast assumptions still require analyst review; SEC does not publish future DCF assumptions.

FRED works without a visitor API key using FRED's official published CSV downloads. CPI inflation is calculated from exact 12-calendar-month observations without filling missing months. If the owner configures a FRED API key, the JSON API is used first, with official CSV fallback.

## Updating your existing GitHub / Streamlit deployment

1. Extract the updated ZIP, open the `MarketMind_Streamlit` folder and upload its contents to your repository's root, replacing existing files. Include every module, particularly `marketmind/regions.py`, `marketmind/regional_data.py` and `marketmind/macro_dashboard.py`. Keep `app.py` at the root used by Streamlit.
2. Commit the changes on the branch used by Streamlit. Community Cloud will redeploy the updated code; reboot the app from its management menu if it is still showing the previous version.
3. No visitor connection step or mandatory API key is required. SEC requests use the truthful project identity `MarketMind/0.4 (+https://github.com/bellalnabkel-arch/MarketMind)`. As the owner, you can optionally set a monitored SEC contact in Streamlit's app settings → Secrets:

```toml
SEC_USER_AGENT = "Your name your.real.email@domain.com"
```

Use a real monitored contact if overriding the default. This identifies automated requests to SEC; it is not a visitor login or an SEC API key. Keep it out of committed source files. Remove any old example/placeholder SEC_USER_AGENT secret or replace it with a real identity: an invalid explicitly configured override is reported clearly instead of hidden behind a generic outage.

`FRED_API_KEY` is optional. Leave it unset to use FRED's official CSV downloads. For the JSON API, add your own valid key to the same server secret settings. Visitors never enter credentials.

SEC 403 access restrictions, 429 rate limits, missing records, transport failures and invalid settings have distinct diagnostics. The default identity passed live SEC retrieval for all seven validation companies. SEC can still restrict particular hosting IPs; code cannot guarantee availability or bypass provider access controls. Unsupported issuer taxonomies and missing facts remain clearly unavailable.

The existing Sites deployment is a separate application and is not changed by this package. This edition preserves the financial workflows and color palette, with native Streamlit widgets in place of the original standalone HTML layout.

## Run locally

Use Python 3.12. From the extracted project directory:

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell instead:
# .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Optional: copy `secrets.example.toml` to `.streamlit/secrets.toml` and configure your own monitored contact or FRED key, or use `.env`. Neither file is required; both real secret files are ignored by Git. Open the URL printed by Streamlit, normally http://localhost:8501, and search for a company. Retrieval runs automatically.

The top search uses a complete downloaded SEC directory, with partial, ticker, CIK and fuzzy matching. Query text updates after a 300 ms pause. Choose a suggestion with the native select control; keyboard navigation is supported. The selected ticker is reflected in the URL and survives page navigation and reloads. CIK and official name are validated from the cached directory. The application passes that CIK directly to `SECClient.company_facts`.

## Recommended deployment: Streamlit Community Cloud

1. Extract this ZIP and put its contents at the root of a GitHub repository. Keep the repository private unless you intentionally want to publish the source. Do not upload `.venv`, `.env`, caches or real secrets.
2. Sign in at https://share.streamlit.io and connect the GitHub repository using the provider's supported flow.
3. Create an app, select your repository and branch, and set the main file path to `app.py`.
4. Choose Python 3.12 in advanced settings. `SEC_USER_AGENT` and `FRED_API_KEY` are optional owner overrides through hosting secret settings. Do not copy active placeholder values into Secrets.
5. Review app sharing settings before sharing the new URL. Hosting access is managed by Streamlit and does not inherit ChatGPT/Sites sign-in.
6. Deploy, select a company and verify that financials populate automatically. Open Macro dashboard and verify that economic observations appear without a load button or API-key form.
7. After verifying the new deployment, use its new URL. The Sites hostname does not automatically move to another provider, and this migration does not delete the old Site.

Official instructions: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy and https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management.

## Other hosts

`render.yaml` supplies a Python web-service configuration; review the host's plan and access controls before creating the service. Build: `pip install -r requirements.txt`. Start: `python -m streamlit run app.py --server.address=0.0.0.0 --server.port=$PORT`. Health check: `/_stcore/health`. Render's public-facing services do not inherit Sites authentication. No Render service has been provisioned by preparing this file.

For Docker-compatible hosts:

```bash
docker build -t marketmind .
docker run --rm -p 8501:8501 --env-file .env marketmind
```

Review authentication before exposing this port outside your own computer. Host-specific deployments and account setup are separate from local verification.

## Validation

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests include the seven requested official company CIKs, fuzzy/case/partial matching, automatic SEC/FRED loading, CIK isolation, cache TTL and cross-session cache reuse, retry cooldown, partial outages, no-key CSV/ZIP retrieval, CPI calendar alignment, financial period alignment, DCF/WACC math, key redaction, classified SEC failures, state selection, missing state values and text contrast. Automated test numbers are synthetic test inputs, never production data.

For a separately dated live-provider audit, run `python scripts/live_audit.py`. It fetches actual SEC data for AAPL, TSLA, NVDA, MSFT, JPM, AMZN and GOOGL, nine national series and 153 state series, then replays those real responses through all five application sections and seven geography selections. The result is recorded in `validation/LIVE_AUDIT.json`; it documents one run, not a guarantee of subsequent provider access. `python scripts/verify_server.py` checks a real Streamlit server's startup and HTTP health endpoints. Browser interaction checks separately verified live search/automatic Apple financial retrieval, map hover and a California map click opening state detail.

## National and state economic coverage

The national view includes CPI inflation, real GDP growth, unemployment, daily effective federal funds rate, the Fed target range, 10-year Treasury yield, nonfarm employment and real GDP level. The interactive map supports hover values, observation dates, click selection and a keyboard-accessible Geography dropdown. State detail includes unemployment, quarterly real GDP growth and level, and nonfarm employment. State GDP growth is calculated from consecutive quarterly real GDP levels at an annualized rate; a missing intervening quarter is never bridged.

Fed targets use daily series `DFEDTARL` and `DFEDTARU`, and the effective rate uses `DFF`. The five-minute cache refresh displays updates after FRED publishes them; it is not an instant FOMC announcement feed. Daily, monthly and quarterly observation dates can differ and revisions appear after the next successful refresh. FRED multi-series downloads are limited to 12 series per request; the regional service batches 153 series into 13 requests and retains explicit partial-failure diagnostics.

Statewide CPI is not consistently published for every state. MarketMind does not relabel regional/metro CPI as statewide inflation. Fed rates and U.S. Treasury yields appear as national context in state views. Missing observations remain unavailable. See the official BLS coverage guidance: https://www.bls.gov/cpi/questions-and-answers.htm and series sources linked beside each chart.

The interface uses dark text on light surfaces, brighter sidebar text, stronger captions and labels, focus outlines and a light sensitivity heatmap with dark cell labels. Caption opacity is explicitly 1 so Streamlit cannot fade the chosen text colors. Automated checks cover the configured text/background contrast pairs; keyboard search and geography controls remain native Streamlit widgets. Daily history charts use SVG so browsers without WebGL can render them. The small `map_interaction.py` component bridges Plotly geographic clicks into Streamlit callbacks; the Geography dropdown remains usable if JavaScript map interactions or Plotly's geographic assets are unavailable.

## Structure

- `app.py`: Streamlit server entry point, search, selected-company state and dashboard sections.
- `marketmind/company_search.py`: official SEC directory, disk cache, 24-hour refresh, fuzzy index.
- `data/sec-directory-cache.json`: complete official SEC snapshot and source/download date, reused from MarketMind's verified directory download.
- `marketmind/sec_client.py`: SEC request identity, timeouts, pacing and CIK retrieval.
- `marketmind/data_service.py`: automatic retrieval, one-hour SEC and five-minute macro caches, retry cooldowns and stale-data retention.
- `marketmind/financials.py`, `analytics.py`: annual US-GAAP USD facts, metrics and per-fact filing provenance.
- `marketmind/dcf.py`, `wacc.py`: validated five-year unlevered DCF and CAPM/WACC.
- `marketmind/fred_client.py`: FRED JSON API and official CSV retrieval, source dates and CPI YoY transformation.
- `marketmind/regions.py`, `regional_data.py`: state series definitions, batched retrieval, dated regional values and annualized GDP growth.
- `marketmind/macro_dashboard.py`: national/state dashboard, selectable Plotly map and comparison download.
- `marketmind/map_interaction.py`: scoped JavaScript/Streamlit callback for Plotly state clicks.
- `marketmind/report.py`, `ui.py`: sourced report and shared Plotly/formatting helpers.

## Data and modeling limits

Only standard US-GAAP monetary facts in USD are extracted; unsupported IFRS/custom tags remain missing. Actual reporting end dates determine periods; latest-filed comparatives may include restatements. ROE/ROA require adjacent annual balances and positive average denominators. EBITDA is a proxy using reported cash-flow D&A; CFO less capex is historical FCF and is not automatically used as unlevered FCF. The DCF requires an analyst-supplied unlevered-FCF base, cash, total debt and shares. A market price and market recommendation are not supplied. Multiple share classes and financial institutions require analyst review.

The official directory refreshes after 24 hours when the application is used; a declared project identity is supplied automatically and cached metadata supports outages. Some hosting filesystems are ephemeral. Public SEC financials are cached for one hour and national/state economic observations for five minutes. Owner credentials stay on the server; personal modeling inputs remain in the server session. Missing SEC/FRED data is never replaced with fabricated values.
