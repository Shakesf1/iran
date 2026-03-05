from curl_cffi import requests
import pandas as pd
import json
from datetime import datetime, timezone

# API Endpoints
EVENTS_URL = "https://iranstrike.com/api/events"
SUMMARY_URL = "https://iranstrike.com/api/summary"

# 1. Fetch Data
session = requests.Session()
events_res = session.get(EVENTS_URL, impersonate="firefox144")
summary_res = session.get(SUMMARY_URL, impersonate="firefox144")

if events_res.status_code == 200 and summary_res.status_code == 200:
    # --- PART A: PROCESS EVENTS (HOURLY/DAILY CHARTS) ---
    events_data = events_res.json().get('events', [])
    df = pd.DataFrame(events_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601')
    df_irn = df[df['origin'] == 'IRN'].copy()
    
    if not df_irn.empty:
        # Hourly Data
        hourly = df_irn.groupby([df_irn['timestamp'].dt.floor('h'), 'location']).size().unstack(fill_value=0)
        hourly.index = hourly.index.strftime('%Y-%m-%d %H:%M')
        hourly.reset_index().to_json('hourly_data.json', orient='records')

        # Daily Data with Extrapolation
        daily = df_irn.groupby([df_irn['timestamp'].dt.floor('D'), 'location']).size().unstack(fill_value=0).sort_index()
        avg_pace = daily.sum(axis=1).tail(3).mean()
        last_day_dt = daily.index[-1]
        
        now = datetime.now(timezone.utc)
        extra = 0
        if last_day_dt.date() == now.date():
            hours_passed = now.hour + (now.minute / 60)
            extra = avg_pace * ((24 - hours_passed) / 24) if hours_passed < 24 else 0
        
        daily['Extrapolation'] = float(extra)
        daily.index = daily.index.strftime('%Y-%m-%d')
        daily.reset_index().rename(columns={'timestamp': 'day'}).to_json('daily_data.json', orient='records')

    # --- PART B: PROCESS SUMMARY (BLOC TABLES) ---
    raw_summary = summary_res.json()
    inner_data = raw_summary.get('data', raw_summary)
    countries = inner_data.get('countries', [])
    
    # Define Blocs
    iran_allies = ['IRN', 'YEM', 'LBN', 'SYR', 'PSE']
    bloc_totals = {
        "Iran-Led Bloc": {"launched": 0, "intercepted": 0, "hits": 0, "mil_cas": 0, "civ_cas": 0},
        "US/Israel Bloc": {"launched": 0, "intercepted": 0, "hits": 0, "mil_cas": 0, "civ_cas": 0}
    }

    for c in countries:
        bloc = "Iran-Led Bloc" if c.get('entityId') in iran_allies else "US/Israel Bloc"
        
        launched_obj = c.get('launched', {})
        launched = launched_obj.get('total', 0) if isinstance(launched_obj, dict) else 0
        cas = c.get('casualties', {})

        bloc_totals[bloc]["launched"] += launched
        bloc_totals[bloc]["intercepted"] += c.get('intercepted', 0)
        bloc_totals[bloc]["hits"] += c.get('hits', 0)
        bloc_totals[bloc]["mil_cas"] += cas.get('military', 0)
        bloc_totals[bloc]["civ_cas"] += cas.get('civilian', 0)

    # Export a clean, latest snapshot
    with open('summary_latest.json', 'w') as f:
        json.dump({
            "asOf": inner_data.get('asOf'),
            "summary": bloc_totals
        }, f, indent=4)
    
    print(f"Successfully synced: {inner_data.get('asOf')}")

else:
    print(f"Error: Events ({events_res.status_code}) Summary ({summary_res.status_code})")