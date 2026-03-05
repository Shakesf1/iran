from curl_cffi import requests
import pandas as pd
import os
from datetime import datetime

BASE_URL = "https://iranstrike.com/api"

def update_persistent_json(new_df, filename, keys, keep_strategy='last'):
    """Checks for existing data and only appends unique/new records."""
    if os.path.exists(filename):
        try:
            existing_df = pd.read_json(filename)
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            new_df = combined.drop_duplicates(subset=keys, keep=keep_strategy)
        except: pass
    new_df.to_json(filename, orient='records', indent=4)

# 1. Fetch Data
session = requests.Session()
events_res = session.get(f"{BASE_URL}/events", impersonate="firefox144")
summary_res = session.get(f"{BASE_URL}/summary", impersonate="firefox144")

if events_res.status_code == 200 and summary_res.status_code == 200:
    # --- PART A: EVENTS (HOURLY & DAILY) ---
    events_data = events_res.json()['events']
    df_e = pd.DataFrame(events_data)
    df_e['timestamp'] = pd.to_datetime(df_e['timestamp'], format='ISO8601')
    df_irn = df_e[df_e['origin'] == 'IRN'].copy()
    
    if not df_irn.empty:
        df_irn['hour'] = df_irn['timestamp'].dt.floor('h').dt.strftime('%Y-%m-%d %H:%M')
        hourly_new = df_irn.groupby(['hour', 'location']).size().reset_index(name='count')
        update_persistent_json(hourly_new, 'hourly_data.json', ['hour', 'location'])
        
        df_irn['day'] = df_irn['timestamp'].dt.floor('D').dt.strftime('%Y-%m-%d')
        daily_new = df_irn.groupby(['day', 'location']).size().reset_index(name='count')
        update_persistent_json(daily_new, 'daily_data.json', ['day', 'location'])

    # --- PART B: SUMMARY & HISTORY ---
    summary_data = summary_res.json()
    as_of = summary_data.get('asOf')
    day_str = pd.to_datetime(as_of).strftime('%Y-%m-%d')
    
    iran_allies = ['IRN', 'YEM', 'LBN', 'IRQ', 'SYR', 'PSE']
    summary_list = []
    
    for c in summary_data.get('countries', []):
        launched = c.get('launched', {}).get('total', 0)
        intercepted = c.get('intercepted', 0)
        summary_list.append({
            "date": day_str,
            "asOf": as_of,
            "bloc": "Iran-Led Bloc" if c['entityId'] in iran_allies else "US/Israel Bloc",
            "entity": c['name'],
            "launched": launched,
            "intercepted": intercepted,
            "hits": c.get('hits', 0),
            "mil_cas": c.get('casualties', {}).get('military', 0),
            "civ_cas": c.get('casualties', {}).get('civilian', 0)
        })
    
    summary_df = pd.DataFrame(summary_list)
    
    # 1. Full History (every update)
    update_persistent_json(summary_df, 'summary_history.json', ['asOf', 'entity'])
    
    # 2. Daily Snapshot (only latest per day)
    update_persistent_json(summary_df, 'daily_summary_history.json', ['date', 'entity'], keep_strategy='last')

    print(f"Sync complete for {as_of}")