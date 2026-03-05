from curl_cffi import requests
import pandas as pd
import json
import os
from datetime import datetime, timezone

# API Endpoints
EVENTS_URL = "https://iranstrike.com/api/events"
SUMMARY_URL = "https://iranstrike.com/api/summary"


def update_persistent_json(new_df, filename, keys):
    if os.path.exists(filename):
        try:
            existing_df = pd.read_json(filename)
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            # Remove duplicates so you don't double-count the same hour/day
            new_df = combined.drop_duplicates(subset=keys, keep='last')
        except Exception: pass
    new_df.to_json(filename, orient='records', indent=4, date_format='iso')

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
            # --- HOURLY DATA ---
            # 1. Group and unstack
            hourly = df_irn.groupby([df_irn['timestamp'].dt.floor('h'), 'location']).size().unstack(fill_value=0)
            
            # 2. Reset index first so 'timestamp' becomes a column
            hourly_df = hourly.reset_index() 
            
            # 3. CONVERT TIMESTAMP TO STRING (This fixes the blank graph)
            hourly_df['timestamp'] = hourly_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
            
            # 4. Use 'timestamp' as the unique key for persistence
            update_persistent_json(hourly_df, 'hourly_data.json', ['timestamp'])

            # --- DAILY DATA ---

            # 1. Group actual strikes by day
            daily = df_irn.groupby([df_irn['timestamp'].dt.floor('D'), 'location']).size().unstack(fill_value=0).sort_index()
            daily.index = daily.index.strftime('%Y-%m-%d')
            
            # 2. Update persistent record of ACTUAL strikes (no extrapolation here)
            daily_df = daily.reset_index().rename(columns={'timestamp': 'day'})
            update_persistent_json(daily_df, 'daily_data.json', ['day'])

            # 3. Handle Extrapolation (Only for the LIVE view)
            # Reload the now-updated file to apply extrapolation to the current day only
            current_daily = pd.read_json('daily_data.json')
            
            avg_pace = daily.sum(axis=1).tail(3).mean()
            now = datetime.now(timezone.utc)
            today_str = now.strftime('%Y-%m-%d')

            # Calculate extra strikes for the remaining hours of today
            hours_passed = now.hour + (now.minute / 60)
            extra = avg_pace * ((24 - hours_passed) / 24) if hours_passed < 24 else 0

            # Apply extrapolation column: 0 for history, 'extra' value for today
            current_daily['Extrapolation'] = 0.0
            current_daily.loc[current_daily['day'] == today_str, 'Extrapolation'] = float(extra)

            # 4. Overwrite daily_data.json with the temporary extrapolation included
            # This will be cleaned/reset the next time the script runs (Step 2)
            current_daily.to_json('daily_data.json', orient='records', indent=4, date_format='iso')


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
    current_date = pd.to_datetime(inner_data.get('asOf')).strftime('%Y-%m-%d')
    
    # Flatten the bloc_totals for a dataframe format
    history_rows = []
    for bloc_name, stats in bloc_totals.items():
        row = {"date": current_date, "bloc": bloc_name}
        row.update(stats)
        history_rows.append(row)
    
    # 2. Update the Historical File (summary_history.json)
    # This appends new days and overwrites the current day if it already exists
    history_df = pd.DataFrame(history_rows)
    update_persistent_json(history_df, 'summary_history.json', ['date', 'bloc'])

    # 3. Export the "Latest" snapshot as before (summary_latest.json)
    with open('summary_latest.json', 'w') as f:
        json.dump({
            "asOf": inner_data.get('asOf'),
            "summary": bloc_totals
        }, f, indent=4)
    
    print(f"Successfully synced summary and history for: {inner_data.get('asOf')}")
    
    print(f"Successfully synced: {inner_data.get('asOf')}")

else:
    print(f"Error: Events ({events_res.status_code}) Summary ({summary_res.status_code})")