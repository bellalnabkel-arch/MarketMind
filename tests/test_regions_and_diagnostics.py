import io
from zipfile import ZipFile
import pandas as pd
import pytest
import requests
from streamlit.testing.v1 import AppTest
from marketmind import data_service as service, regional_data
from marketmind.config import DEFAULT_SEC_USER_AGENT, FRED_SERIES
from marketmind.exceptions import DataSourceError
from marketmind.sec_client import SECClient, resolve_identity
from marketmind.fred_client import read_official_csv_download, FREDClient
from marketmind.regions import STATES, REGIONAL_SERIES, quarterly_growth, format_macro_value
from marketmind.regional_data import map_table, state_observations
from marketmind.macro_dashboard import make_state_map
from test_marketmind import ROOT, test_payload, stub_automatic_providers

def test_missing_sec_secret_has_declared_application_identity():
    assert resolve_identity('') == DEFAULT_SEC_USER_AGENT
    client = SECClient('')
    assert client.session.headers['User-Agent'] == DEFAULT_SEC_USER_AGENT
    assert 'github.com/bellalnabkel-arch/MarketMind' in client.user_agent

@pytest.mark.parametrize('value',['Your name your.email@domain.com','Your Name YOUR_REAL_EMAIL','bad\r\nInjected: true'])
def test_placeholder_or_injected_identity_is_actionable(value):
    with pytest.raises(DataSourceError) as e: resolve_identity(value)
    assert e.value.code == 'configuration'

@pytest.mark.parametrize('status,code',[(403,'access_restricted'),(429,'rate_limited'),(404,'not_found'),(503,'network')])
def test_sec_http_failures_are_distinguished(monkeypatch,status,code):
    response = requests.Response();response.status_code=status
    def fail(*args,**kwargs):raise requests.HTTPError(response=response)
    client=SECClient('');monkeypatch.setattr(client.session,'get',fail)
    with pytest.raises(DataSourceError) as e: client.company_facts('0000320193')
    assert e.value.code == code

def test_configuration_error_is_not_misreported_as_outage():
    state={}
    assert service.ensure_financial_data(state,{'cik':'0000320193'},'placeholder') == 'configuration'
    assert state['sec_error_code']=='configuration'
    assert 'SEC_USER_AGENT' in state['sec_error']

def test_fred_mixed_frequency_zip_is_read_without_extraction():
    buffer=io.BytesIO()
    with ZipFile(buffer,'w') as z:
        z.writestr('README.txt','Official download')
        z.writestr('monthly.csv','observation_date,CAUR\n2024-01-01,4.0\n')
        z.writestr('quarterly.csv','observation_date,CARQGSP\n2024-01-01,100\n')
    frames=read_official_csv_download(buffer.getvalue())
    assert len(frames)==2
    assert set(frames[0].columns)|set(frames[1].columns)=={'observation_date','CAUR','CARQGSP'}

def test_regional_requests_respect_fred_twelve_line_limit(monkeypatch):
    calls=[]
    def batch(self,ids,start_date='2015-01-01'):
        calls.append(ids)
        frame=pd.DataFrame({'date':pd.to_datetime(['2024-01-01']), 'value':[1.]})
        return {s:frame for s in ids}
    monkeypatch.setattr(FREDClient,'batch_csv_observations',batch)
    regional_data.regional_snapshot.clear()
    try:
        snapshot=regional_data.regional_snapshot()
        assert set(snapshot['frames'])==REGIONAL_SERIES
        assert max(map(len,calls))<=12
        assert len(calls)==13
        assert not snapshot['errors']
    finally:regional_data.regional_snapshot.clear()

def test_five_minute_macro_ttl_catches_new_releases(monkeypatch):
    from datetime import datetime,timezone
    clock=1700000000.;calls=[]
    def snapshot(series_id,*args,**kwargs):
        calls.append(series_id)
        f=pd.DataFrame({'date':pd.to_datetime(['2024-01-01']),'value':[1.]})
        f.attrs['retrieved_at']=datetime.fromtimestamp(clock,timezone.utc).isoformat()
        return f
    monkeypatch.setattr(service,'fred_snapshot',snapshot)
    state={}
    service.ensure_macro_data(state,now=clock)
    service.ensure_macro_data(state,now=clock+299)
    assert len(calls)==len(FRED_SERIES)
    service.ensure_macro_data(state,now=clock+301)
    assert len(calls)==2*len(FRED_SERIES)
    assert 'DFEDTARL' in calls and 'DFEDTARU' in calls and 'DFF' in calls
    assert 'FEDFUNDS' not in calls

def test_state_growth_annualizes_only_adjacent_quarters():
    f=pd.DataFrame({'date':pd.to_datetime(['2024-01-01','2024-04-01','2024-10-01']),'value':[100.,101.,105.]})
    result=quarterly_growth(f)
    assert len(result)==1
    assert result.iloc[0].value==pytest.approx((1.01**4-1)*100)
    assert quarterly_growth(pd.DataFrame(columns=['date','value'])).empty

def test_map_has_fifty_states_and_dc_with_unavailable_values_preserved():
    table=map_table({})
    assert len(table)==51 and table.unemployment.isna().all()
    fig=make_state_map(table)
    assert len(fig.data[0].locations)==51
    assert 'Unavailable' in fig.data[0].customdata[0]
    assert 'CA' in STATES and 'DC' in STATES
    assert 'CPI' not in set(REGIONAL_SERIES)

def test_macro_units_do_not_label_gdp_or_jobs_as_percent():
    assert format_macro_value('GDPC1',25000)=='$25,000.0B'
    assert format_macro_value('CARQGSP',3000000)=='$3,000.0B'
    assert format_macro_value('CANA',18000)=='18.00M jobs'

def test_state_selector_changes_scope_and_national_context_is_explicit(stub_automatic_providers):
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    app.radio(key='workspace').set_value('Macro dashboard').run()
    assert not app.exception
    app.selectbox(key='macro_geography').select('CA').run()
    assert not app.exception
    assert any('California' in e.value for e in app.subheader)
    assert any('not available consistently' in e.value for e in app.info)
    app.selectbox(key='macro_geography').select('NY').run()
    assert not app.exception
    assert any('New York' in e.value for e in app.subheader)
    app.selectbox(key='macro_geography').select('US').run()
    assert not app.exception

def test_readability_palette_meets_normal_text_contrast():
    def luminance(hex):
        channels=[int(hex[i:i+2],16)/255 for i in (1,3,5)]
        linear=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in channels]
        return sum(c*w for c,w in zip(linear,[.2126,.7152,.0722]))
    for text,bg in [('#142033','#F6F8FB'),('#475569','#F6F8FB'),('#1D4ED8','#FFFFFF'),('#FFFFFF','#1D4ED8'),('#CBD5E1','#0B1220'),('#0F172A','#93C5FD')]:
        a,b=sorted([luminance(text),luminance(bg)])
        assert (b+.05)/(a+.05)>=4.5,(text,bg)
