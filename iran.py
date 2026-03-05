from curl_cffi import requests
import pandas as pd
import os
from datetime import datetime

BASE_URL = "https://iranstrike.com/api"

def update_persistent_json(new_df, filename, keys, keep_strategy='last'):
    if os.path.exists(filename):
        try:
            existing_df = pd.read_json(filename)
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            new_df = combined.drop_duplicates(subset=keys, keep=keep_strategy)
        except Exception: pass
    new_df.to_json(filename, orient='records', indent=4)

# 1. Fetch Data
session = requests.Session()
events_res = session.get(f"{BASE_URL}/events", impersonate="firefox144")
summary_res = session.get(f"{BASE_URL}/summary", impersonate="firefox144")

if summary_res.status_code == 200:
    raw_json = summary_res.json()
    
    # Handle the nested 'data' key if it exists
    inner_data = raw_json.get('data', raw_json)
    
    # Check for timestamps in order of preference
    as_of = inner_data.get('asOf') or inner_data.get('researchedAt')
    
    if as_of is None:
        as_of = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        print("Warning: No timestamp found in API, using system time.")

    day_str = pd.to_datetime(as_of).strftime('%Y-%m-%d')
    countries = inner_data.get('countries', [])
    
    # Define Blocs
    iran_allies = ['IRN', 'YEM', 'LBN', 'IRQ', 'SYR', 'PSE']
    summary_list = []
    
    for c in countries:
        eid = c.get('entityId')
        bloc = "Iran-Led Bloc" if eid in iran_allies else "US/Israel Bloc"
        
        # Get total launched (handling nested launched object)
        launched_info = c.get('launched', {})
        launched = launched_info.get('total', 0) if isinstance(launched_info, dict) else 0
        
        summary_list.append({
            "date": day_str,
            "asOf": as_of,
            "bloc": bloc,
            "entity": c.get('name'),
            "launched": launched,
            "intercepted": c.get('intercepted', 0),
            "hits": c.get('hits', 0),
            "mil_cas": c.get('casualties', {}).get('military', 0),
            "civ_cas": c.get('casualties', {}).get('civilian', 0)
        })
    
    if summary_list:
        summary_df = pd.DataFrame(summary_list)
        # Save to history
        update_persistent_json(summary_df, 'summary_history.json', ['asOf', 'entity'])
        update_persistent_json(summary_df, 'daily_summary_history.json', ['date', 'entity'], keep_strategy='last')
        print(f"Successfully synced data for {day_str}")