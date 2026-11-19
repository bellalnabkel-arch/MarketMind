"""Readable national dashboard with a selectable, dated state choropleth."""
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from .config import FRED_SERIES
from .regions import STATES, format_macro_value, series_units
from .regional_data import ensure_regional_data, map_table, state_observations
from .map_interaction import enable_map_clicks

def make_state_map(table, column='unemployment'):
    table=table.copy()
    custom=[]
    for r in table.itertuples():
        custom.append([r.code,r.state,f'{r.unemployment:.1f}%' if pd.notna(r.unemployment) else 'Unavailable',r.unemployment_date,f'{r.gdp_growth:.2f}%' if pd.notna(r.gdp_growth) else 'Unavailable',r.gdp_date,f'{r.jobs_millions:.2f}M' if pd.notna(r.jobs_millions) else 'Unavailable',r.jobs_date])
    hover='<b>%{customdata[1]}</b><br>Unemployment: %{customdata[2]} (%{customdata[3]})<br>Real GDP growth: %{customdata[4]} (%{customdata[5]})<br>Nonfarm jobs: %{customdata[6]} (%{customdata[7]})<extra></extra>'
    base=go.Choropleth(locations=table.code,locationmode='USA-states',z=[0]*len(table),colorscale=[[0,'#E2E8F0'],[1,'#E2E8F0']],showscale=False,customdata=custom,hovertemplate=hover,marker_line_color='white',marker_line_width=1)
    fig=go.Figure(base)
    valid=table[column].notna()
    if valid.any():
        fig.add_trace(go.Choropleth(locations=table.loc[valid,'code'],locationmode='USA-states',z=table.loc[valid,column],colorscale='Blues',customdata=[c for c,v in zip(custom,valid) if v],hovertemplate=hover,marker_line_color='white',marker_line_width=1,colorbar=dict(title={'text':{'unemployment':'Percent','gdp_growth':'Percent, SAAR','jobs_millions':'Million jobs'}[column]},tickfont=dict(color='#142033'))))
    fig.update_layout(geo=dict(scope='usa',bgcolor='rgba(0,0,0,0)',showlakes=True,lakecolor='white'),margin=dict(l=0,r=0,t=10,b=0),height=470,clickmode='event',dragmode='pan',paper_bgcolor='white',font=dict(color='#142033',size=13),hoverlabel=dict(bgcolor='white',font_color='#142033',font_size=13))
    return fig

def _show_series(label, frame, series_id, *, growth=False):
    if frame.empty:
        st.info(label + ': no available observations.')
        return
    last=frame.iloc[-1]
    value=f'{last.value:.2f}%' if growth else format_macro_value(series_id,float(last.value))
    st.metric(label,value)
    attrs=frame.attrs
    st.caption(f"Observation: {last.date.date()} · {series_id} · {'Annualized quarter-over-quarter percent' if growth else series_units(series_id)}")
    st.caption(f"Source: {attrs.get('source','FRED')} · Retrieved {attrs.get('retrieved_at','unavailable')}")
    # SVG keeps daily histories usable on browsers without WebGL acceleration.
    chart=px.line(frame,x='date',y='value',title=label,template='plotly_white',render_mode='svg')
    chart.update_layout(font_color='#142033',xaxis_title='Observation date',yaxis_title='Percent' if growth else series_units(series_id),hovermode='x unified')
    st.plotly_chart(chart,width='stretch')
    st.link_button('Source · '+series_id,'https://fred.stlouisfed.org/series/'+series_id)

def render_macro_dashboard(state):
    st.title('U.S. economic dashboard')
    st.caption('National data and all 50 states plus Washington, D.C. · Checks every minute while open; provider data cache expires after 5 minutes. Updates appear after publication by FRED/BLS/BEA/Fed.')
    with st.spinner('Updating state economic observations…'):
        regional=ensure_regional_data(state)
    if state.get('regional_error'):
        st.warning(state.regional_error)
    code=st.selectbox('Geography', ['US',*sorted(STATES,key=STATES.get)],format_func=lambda c:'United States · national' if c=='US' else STATES[c],key='macro_geography')
    table=map_table(regional.get('frames',{}))
    color=st.selectbox('Color state map by',['Unemployment rate','Real GDP growth','Nonfarm payroll employment'],key='map_measure')
    column={'Unemployment rate':'unemployment','Real GDP growth':'gdp_growth','Nonfarm payroll employment':'jobs_millions'}[color]
    with st.container(key='mm_state_map'):
        st.plotly_chart(make_state_map(table,column),key='us_states_map',width='stretch',config={'displaylogo':False})
    enable_map_clicks()
    st.caption('Hover for dated state values. Click a state to open its detail below, or use Geography. Each state uses its latest available observation; dates may differ. Gray means unavailable.')
    for label,error in state.get('macro_errors',{}).items():
        st.warning(f'{label}: {error}')
    if code=='US':
        st.subheader('United States · national indicators')
        for label,series_id in FRED_SERIES.items():
            frame=state.get('macro',{}).get(label)
            if frame is None or frame.empty:
                st.caption(label+': unavailable')
                continue
            with st.container(border=True):_show_series(label,frame,series_id)
    else:
        st.subheader(STATES[code]+' · state indicators')
        observations=state_observations(regional.get('frames',{}),code)
        for label in ['Unemployment rate','Real GDP growth','Real GDP level','Nonfarm payroll employment']:
            item=observations[label]
            with st.container(border=True):_show_series(label,item['frame'],item['series_id'],growth=label=='Real GDP growth')
        st.info('Statewide CPI inflation is not available consistently for all states in the BLS CPI program. Regional or metropolitan CPI is not substituted as a state estimate.')
        st.subheader('National policy context · applies across states')
        st.caption('The Fed policy rate and U.S. Treasury yields are national measures, not separate state-level rates.')
        for label in ['Fed target range · lower','Fed target range · upper','Effective federal funds rate · daily','10-year Treasury yield','CPI inflation · YoY']:
            frame=state.get('macro',{}).get(label)
            if frame is not None and not frame.empty:
                last=frame.iloc[-1];st.metric(label+' · U.S.',f'{last.value:.2f}%',help=f'Observation: {last.date.date()}')
    with st.expander('State comparison table and observation dates'):
        st.dataframe(table,hide_index=True,width='stretch')
        st.download_button('Download state comparison CSV',table.to_csv(index=False),'MarketMind_state_economy.csv','text/csv')
    st.caption('A five-minute provider check is not an announcement-time push feed. Publication lags, weekends and revisions affect the latest available observation. On reopening the app, expired data refreshes automatically.')
