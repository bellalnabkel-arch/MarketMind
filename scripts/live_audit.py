"""Read-only audit against live SEC/FRED, then exercise every app section.

Actual provider responses are reused for UI testing to avoid redundant network
requests. No synthetic company financial figures are used in this audit.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from streamlit.testing.v1 import AppTest
from marketmind.sec_client import SECClient
from marketmind.fred_client import FREDClient
from marketmind.financials import build_annual_financials
from marketmind.analytics import calculate_metrics
from marketmind.regional_data import regional_snapshot,map_table
from marketmind.regions import REGIONAL_SERIES
from marketmind.config import FRED_SERIES
from marketmind import data_service,regional_data

cases=[('Apple','AAPL','0000320193'),('Tesla','TSLA','0001318605'),('NVIDIA','NVDA','0001045810'),('Microsfot','MSFT','0000789019'),('JPMorgan Chase','JPM','0000019617'),('Amazon','AMZN','0001018724'),('GOOGL','GOOGL','0001652044')]
report={'run_at_utc':datetime.now(timezone.utc).isoformat(),'companies':[],'ui_checks':0,'failures':[]}
snapshots={}
for query,ticker,cik in cases:
    try:
        payload=SECClient('').company_facts(cik)
        now=datetime.now(timezone.utc).isoformat()
        snapshots[cik]={'payload':payload,'retrieved_at':now}
        metrics=calculate_metrics(build_annual_financials(payload))
        assert not metrics.empty
        row=metrics.iloc[-1]
        report['companies'].append({'ticker':ticker,'cik':cik,'period_end':row.period_end,'annual_periods':len(metrics),'source':f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'})
        print(f'SEC PASS {ticker}: {len(metrics)} annual periods through {row.period_end}',flush=True)
    except Exception as exc:
        report['failures'].append(f'{ticker}: {type(exc).__name__}: {exc}')

national=FREDClient('').batch_csv_observations(list(FRED_SERIES.values()))
assert set(FRED_SERIES.values()) <= set(national),'National series missing'
report['national_series']={s:{'observation':str(f.iloc[-1].date.date()),'retrieved_at':f.attrs.get('retrieved_at')} for s,f in national.items()}
print(f'FRED PASS {len(national)} national series',flush=True)
regional=regional_snapshot()
assert set(regional['frames'])==REGIONAL_SERIES,'Regional series missing'
table=map_table(regional['frames'])
assert len(table)==51 and table.unemployment.notna().all() and table.gdp_growth.notna().all()
report['regional_series']=len(regional['frames']);report['map_geographies']=len(table)
print(f'STATES PASS {len(regional["frames"])} series / {len(table)} geographies',flush=True)

def cached_sec(cik,*args,**kwargs):return snapshots[cik]
def cached_fred(series,*args,**kwargs):return national[series]
with patch.object(data_service,'sec_snapshot',cached_sec),patch.object(data_service,'fred_snapshot',cached_fred),patch.object(regional_data,'regional_snapshot',lambda:regional):
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    assert not app.exception
    for query,ticker,cik in cases:
        if cik not in snapshots:continue
        app.text_input(key='company_query').input(query).run()
        assert app.selectbox(key='company_result')
        app.selectbox(key='company_result').select(ticker).run()
        assert not app.exception
        assert app.session_state['financial_source']['cik']==cik
        for page in ['Overview','Financials','DCF valuation','Macro dashboard','Research report']:
            app.radio(key='workspace').set_value(page).run()
            assert not app.exception,(ticker,page,[str(e.message) for e in app.exception])
            report['ui_checks']+=1
        print(f'UI PASS {ticker}: all five sections',flush=True)
    app.radio(key='workspace').set_value('Macro dashboard').run()
    for code in ['CA','NY','TX','AK','HI','DC','US']:
        app.selectbox(key='macro_geography').select(code).run()
        assert not app.exception,code
        report['ui_checks']+=1
    assert len(app.get('plotly_chart'))>0

target=ROOT/'validation'/'LIVE_AUDIT.json'
target.parent.mkdir(exist_ok=True)
target.write_text(json.dumps(report,indent=2))
print(f'AUDIT COMPLETE: {report["ui_checks"]} UI checks; {len(report["failures"])} provider failures. {target}',flush=True)
if report['failures']:sys.exit(1)
