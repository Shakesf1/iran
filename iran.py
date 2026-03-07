from curl_cffi import requests
import pandas as pd
import json
import os
from datetime import datetime, timezone
from io import StringIO

pd.set_option('display.max_columns', None)

# Optional: Also ensure each line doesn't wrap to the next
pd.set_option('display.width', None)


# API Endpoints
EVENTS_URL = "https://iranstrike.com/api/events"
SUMMARY_URL = "https://iranstrike.com/api/summary"
iran_allies = ['IRN', 'YEM', 'LBN', 'SYR', 'PSE', 'IRQ']
import re
import base64

SECRET_KEY = "pay_homage_to_stan_4ever"

def encrypt_data(data_string, key=SECRET_KEY):
# 1. Apply XOR Cipher using the key
    # This cycles through the key and XORs each character of the data
    xor_data = "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(data_string))
    
    # 2. Base64 encode the XOR'd result so it can be saved in JSON
    encoded = base64.b64encode(xor_data.encode('utf-8')).decode('utf-8')
    return encoded


def sync_bdti_5y(session):
    js_url = "https://en.stockq.org/index/js/BDTI_dev.js"
    res = session.get(js_url, impersonate="chrome110")
    
    if res.status_code == 200:
        content = res.text
        print(f"✅ Downloaded {len(content)} bytes")
        # This regex looks for: var data5Y = ... arrayToDataTable([ (CAPTURE EVERYTHING) ]);
        # It handles the nested parenthesis and the trailing semicolon correctly.
        data_match = re.search(r"var\s+data5Y\s*=\s*google\.visualization\.arrayToDataTable\(\s*\[(.*?)\]\s*\)\s*;", content, re.DOTALL)
        
        if data_match:
            print("✅ Successfully extracted the data5Y block from the JS file.")
            raw_data = data_match.group(1)
            print(raw_data[-10:]) # Print the last 500 characters to verify we got the right block
            # Now extract the date and price pairs
            # Pattern: [new Date('Oct 18, 2021'), 727.00,
            pattern = r"\[new Date\('([^']+)'\),\s*([\d\.]+),"
            matches = re.findall(pattern, raw_data)
            
            new_rows = []
            for date_str, price in matches:
                try:
                    # Convert 'Oct 18, 2021' -> '2021-10-18'
                    dt = datetime.strptime(date_str, '%b %d, %Y')
                    new_rows.append({
                        "date": dt.strftime('%Y-%m-%d'),
                        "bdti_price": float(price)
                    })
                except: continue
            
            if new_rows:
                df_new = pd.DataFrame(new_rows)
                # This uses your existing function from iran.py
                update_persistent_json(df_new, 'shipping_data.json', ['date'])
                print(f"Sync complete. BDTI Latest: {new_rows[-1]['bdti_price']} on {new_rows[-1]['date']}")
        else:
            print("Regex failed to find the data5Y block. Check if the variable name changed in the JS file.")

def read_encrypted_df(filename):
    SECRET_KEY = "pay_homage_to_stan_4ever"
    with open(filename, 'r') as f:
        encrypted_blob = json.load(f)
        scrambled = base64.b64decode(encrypted_blob['payload']).decode('utf-8')
        decrypted_str = "".join(chr(ord(c) ^ ord(SECRET_KEY[i % len(SECRET_KEY)])) for i, c in enumerate(scrambled))
        from io import StringIO
        return pd.read_json(StringIO(decrypted_str))

    
def update_persistent_json(new_df, filename, keys, rolling_days=5):
    SECRET_KEY = "pay_homage_to_stan_4ever"
    
    if os.path.exists(filename):
        try:
            # 1. Load existing data
            existing_df = read_encrypted_df(filename)
            if existing_df.empty:
                combined = new_df
            else:
                # 2. Identify the date column
                date_col = next((c for c in ['day', 'date', 'timestamp'] if c in existing_df.columns), None)
                
                if date_col and rolling_days > 0:
                    # Use format='mixed' to handle both YYYY-MM-DD and YYYY-MM-DD HH:MM
                    existing_df[date_col] = pd.to_datetime(existing_df[date_col], format='mixed')
                    new_df[date_col] = pd.to_datetime(new_df[date_col], format='mixed')
                    
                    # WIPE the rolling window from history to allow fresh overwrite
                    cutoff = datetime.now() - pd.Timedelta(days=rolling_days)
                    existing_df = existing_df[existing_df[date_col] < cutoff]

                # 3. Combine
                combined = pd.concat([existing_df, new_df], ignore_index=True)
            
            # 4. Deduplicate based on provided keys
            new_df = combined.drop_duplicates(subset=keys, keep='last')
            
        except Exception as e:
            print(f"Rolling merge error for {filename}: {e}")
            import traceback
            traceback.print_exc()

    # Save logic (Standardize dates to strings before JSON export)
    # This prevents JSON serializing issues with Timestamp objects
    raw_json_str = new_df.to_json(orient='records', date_format='iso')
    encrypted_payload = encrypt_data(raw_json_str)
    with open(filename, 'w') as f:
        json.dump({"payload": encrypted_payload}, f)

# 1. Fetch Data
session = requests.Session()
events_res = session.get(EVENTS_URL, impersonate="firefox144")
summary_res = session.get(SUMMARY_URL, impersonate="firefox144")

if events_res.status_code == 200 and summary_res.status_code == 200:
    #Sync shipping data
    print("Syncing BDTI 5-year historical data...")
    sync_bdti_5y(session)

    # --- PART A: PROCESS EVENTS (HOURLY/DAILY CHARTS) ---
    events_data = events_res.json().get('events', [])
    df = pd.DataFrame(events_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601')

    mask = (df['origin'].isna()) & (~df['location'].isin(iran_allies))
    df.loc[mask, 'origin'] = 'IRN'
    mask_inside_iran = (df['location'] == 'IRN') & (df['origin'].isna())
    df.loc[mask_inside_iran, 'origin'] = 'ISR'
    df = df[df['type'].isin(['launch', 'strike'])]




    df_irn = df[df['origin'] == 'IRN'].copy()
    
    df_irn['time_diff'] = df_irn.groupby('location')['timestamp'].diff().dt.total_seconds()
        
    # Mark it as a new volley if the gap is > 5 minutes or if it's the first event
    df_irn['is_new_volley'] = (df_irn['time_diff'] > 300) | (df_irn['time_diff'].isna())
    
    # Assign a unique ID to each group (volley)
    df_irn['volley_id'] = df_irn.groupby('location')['is_new_volley'].cumsum()

    # 4. Collapse the data: Group by Location and Volley ID, keep the first timestamp
    df_irn = df_irn.groupby(['location', 'volley_id']).agg({
        'timestamp': 'first',
        'origin': 'first'
    }).reset_index()
 

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
            current_daily = read_encrypted_df('daily_data.json')
            
            avg_pace = daily.sum(axis=1).tail(3).mean()
            now = datetime.now(timezone.utc)
            today_str = now.strftime('%Y-%m-%d')

            # Calculate extra strikes for the remaining hours of today
            hours_passed = now.hour + (now.minute / 60)
            extra = avg_pace * ((24 - hours_passed) / 24) if hours_passed < 24 else 0

            # Apply extrapolation column: 0 for history, 'extra' value for today
            current_daily['Extrapolation'] = 0.0
            current_daily['day'] = current_daily['day'].astype(str)
            mask = current_daily['day'] == today_str
            current_daily.loc[mask, 'Extrapolation'] = float(extra)
            update_persistent_json(current_daily, 'daily_data.json', ['day'])



    # --- PART B: PROCESS SUMMARY (BLOC TABLES) ---
    raw_summary = summary_res.json()
    inner_data = raw_summary.get('data', raw_summary)
    countries = inner_data.get('countries', [])
    
    # Define Blocs
    
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
    summary_str = json.dumps({"asOf": inner_data.get('asOf'), "summary": bloc_totals})
    with open('summary_latest.json', 'w') as f:
        json.dump({"payload": encrypt_data(summary_str)}, f)
    
    print(f"Successfully synced summary and history for: {inner_data.get('asOf')}")
    
    print(f"Successfully synced: {inner_data.get('asOf')}")

else:
    print(f"Error: Events ({events_res.status_code}) Summary ({summary_res.status_code})")