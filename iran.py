from curl_cffi import requests
import pandas as pd
import json
import os
import sys
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


BDTI_JS_URL = "https://en.stockq.org/index/js/BDTI_dev.js"
# Fallback if the dataFiles map can't be read from the JS (the &v= cache-buster is optional)
BDTI_DATA_FALLBACK = "https://www.stockq.org/index/chart-data.php?id=BDTI&type=dev&range=5y"
# chart-data.php returns 403 without a stockq Referer
STOCKQ_HEADERS = {"Referer": "https://en.stockq.org/"}


def sync_bdti_5y(session):
    """Sync 5y BDTI history from stockq. Returns True on success, False on failure.

    Since ~Aug 2026 BDTI_dev.js no longer inlines the data; it has a `dataFiles`
    map of range -> chart-data.php URL, which returns
    window.stockQChartRangeData("dev", "5y", google.visualization.arrayToDataTable([...]))
    with rows like [new Date('Dec 5, 2024'), 944.00, ...] (column 1 = price).
    """
    data_url = BDTI_DATA_FALLBACK
    try:
        res = session.get(BDTI_JS_URL, impersonate="chrome110", headers=STOCKQ_HEADERS, timeout=30)
        if res.status_code == 200:
            m = re.search(r"var\s+dataFiles\s*=\s*(\{.*?\})\s*;", res.text, re.DOTALL)
            if m:
                data_url = json.loads(m.group(1)).get("5y", data_url)
            else:
                print("⚠️ dataFiles map not found in BDTI_dev.js, using fallback URL")
        else:
            print(f"⚠️ BDTI_dev.js returned {res.status_code}, using fallback URL")
    except Exception as e:
        print(f"⚠️ Could not read BDTI_dev.js ({e}), using fallback URL")

    print(f"Fetching BDTI data: {data_url}")
    res = session.get(data_url, impersonate="chrome110", headers=STOCKQ_HEADERS, timeout=30)
    if res.status_code != 200:
        print(f"❌ BDTI data request failed: HTTP {res.status_code}")
        return False

    matches = re.findall(r"\[new Date\('([^']+)'\),\s*([\d\.]+)", res.text)
    new_rows = []
    for date_str, price in matches:
        try:
            dt = datetime.strptime(date_str, '%b %d, %Y')
        except ValueError:
            continue
        new_rows.append({"date": dt.strftime('%Y-%m-%d'), "bdti_price": float(price)})

    if not new_rows:
        print(f"❌ No BDTI rows parsed from {len(res.text)} bytes. Start: {res.text[:200]!r}")
        return False

    update_persistent_json(pd.DataFrame(new_rows), 'shipping_data.json', ['date'])
    print(f"✅ BDTI sync complete ({len(new_rows)} rows). Latest: {new_rows[-1]['bdti_price']} on {new_rows[-1]['date']}")
    return True

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
    print(new_df)
    print(keys)
    if os.path.exists(filename):
        try:
            existing_df = read_encrypted_df(filename)
            if not existing_df.empty:
                date_col = next((c for c in ['day', 'date', 'timestamp'] if c in existing_df.columns), None)
                
                # FIX: Ensure everything is string-based for the comparison to avoid TZ errors
                if date_col and rolling_days > 0:
                    existing_df[date_col] = pd.to_datetime(existing_df[date_col], utc=True)
                    new_df[date_col] = pd.to_datetime(new_df[date_col], utc=True)
                    cutoff = datetime.now(timezone.utc) - pd.Timedelta(days=rolling_days)
                    
                    existing_df = existing_df[existing_df[date_col] < cutoff]

                # Combine and update the dataframe we intend to save
                combined = pd.concat([existing_df, new_df], ignore_index=True)
                new_df = combined.drop_duplicates(subset=keys, keep='last')
            
        except Exception as e:
            print(f"⚠️ Rolling merge error for {filename}: {e}")
            # If merge fails, we stop here to avoid overwriting history with just today's data
            return 

    # Standardization: Convert all Timestamps back to strings to prevent JSON errors
    for col in new_df.columns:
        if pd.api.types.is_datetime64_any_dtype(new_df[col]):
            new_df[col] = new_df[col].dt.strftime('%Y-%m-%d %H:%M:%S' if 'timestamp' in col else '%Y-%m-%d')

    raw_json_str = new_df.to_json(orient='records')
    encrypted_payload = encrypt_data(raw_json_str)
    with open(filename, 'w') as f:
        json.dump({"payload": encrypted_payload}, f)
    print(f"✅ Saved {filename}")

def process_casualties_csv():
    iran_led = ['Iran', 'Lebanon', 'Iraq', 'Yemen', 'Syria']
    if not os.path.exists('Casualties.csv'): return

    df = pd.read_csv('Casualties.csv')

    # 1. Force Clean Numbers
    cols = ['Civ. Deaths', 'Mil. Deaths', 'Total Deaths', 'Injuries']
    for col in cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    # 2. Force Clean Date Strings (Do not let them become Timestamps)
    df['Date'] = pd.to_datetime(df['Date'], format='%m-%d-%y')
    
    # 3. Aggregate
    df['bloc'] = df['Country'].apply(lambda x: 'Iran-Led Bloc' if x in iran_led else 'US-Israel Bloc')
    daily_bloc = df.groupby(['Date', 'bloc']).sum(numeric_only=True).reset_index()
    daily_bloc.columns = ['date', 'bloc', 'civ_cas', 'mil_cas', 'total_cas', 'injuries']

    # 4. DIRECT SAVE (Skip the update_persistent_json function)
    # This prevents duplicates and date corruption
    raw_json_str = daily_bloc.to_json(orient='records', date_format='iso')
    encrypted_payload = encrypt_data(raw_json_str)
    
    with open('casualties_history.json', 'w') as f:
        json.dump({"payload": encrypted_payload}, f)
        
    print("✅ Casualties History Overwritten Cleanly")

if __name__ == "__main__":

    # 1. Fetch Data
    session = requests.Session()
    events_res = session.get(EVENTS_URL, impersonate="firefox144")
    summary_res = session.get(SUMMARY_URL, impersonate="firefox144")

    # BDTI sync is independent of iranstrike; run it regardless
    print("Syncing BDTI 5-year historical data...")
    try:
        bdti_ok = sync_bdti_5y(session)
    except Exception as e:
        print(f"❌ BDTI sync crashed: {e}")
        bdti_ok = False

    if events_res.status_code == 200 and summary_res.status_code == 200:

        # --- PART A: PROCESS EVENTS (HOURLY/DAILY CHARTS) ---
        # 1. Load data
        events_data = events_res.json().get('events', [])
        df = pd.DataFrame(events_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', utc=True)

        # 2. Refined Origin Logic
        # Instead of just location, check for indicators of Iranian-linked activity
        likely_targets = [
        'ISR', 'USA', 'JOR', 'SAU',  # Original core
        'CYP', 'TUR', 'ARE', 'KWT',  # Cyprus, Turkey, UAE, Kuwait
        'BHR', 'OMN', 'QAT', 'EGY',  # Bahrain, Oman, Qatar, Egypt
        'SDN', 'ERI', 'DJI'          # Red Sea/Horn of Africa (relevant for shipping strikes)
        ]
        df['origin'] = df['origin'].fillna('UNK')

        # We assume IRN origin if:
        # - It's explicitly in the ally list
        # - OR it hits a likely target and the origin is unknown
        
        df_irn = df[
            (
                (df['origin'].isin(iran_allies)) |
                ((df['origin'] == 'UNK') & (df['location'].isin(likely_targets)))
            ) & 
            (df['type'] == 'strike') # ['strike', 'report', 'intercept', 'defense', 'movement'] ==> Only strike is relevant
        ].copy()


        # 3. INCIDENT CLUSTERING (The Fix for Overcounting)
        # Round timestamps to 10-minute windows.
        # If 20 drones hit the same city in 10 minutes, they become 1 'incident'.
        df_irn['cluster_time'] = df_irn['timestamp'].dt.round('10min')

        # Deduplicate: Keep only one record per location per 10-minute window
        df_incidents = df_irn.drop_duplicates(subset=['cluster_time', 'location']).copy()

        # 4. Final Grouping
    # 4. Final Grouping (Fixed 'H' to 'h' to resolve FutureWarning)
        df_incidents['hour'] = df_incidents['timestamp'].dt.floor('h')
        df_incidents['day'] = df_incidents['timestamp'].dt.floor('D')
            
        # CRITICAL: Switch from df_irn to df_incidents for all calculations
        if not df_incidents.empty:
                # 1. Group incidents by hour and location
                # Use 'h' instead of 'H' to avoid the FutureWarning
                df_incidents['timestamp'] = df_incidents['timestamp'].dt.floor('h') 
                df_incidents = df_incidents[pd.to_datetime(df_incidents['timestamp'], utc=True) >= pd.Timestamp('2026-02-28', tz='UTC')]
                hourly = df_incidents.groupby(['timestamp', 'location']).size().unstack(fill_value=0)
                hourly_df = hourly.reset_index()
                
                # 2. Format for JSON
                hourly_df['timestamp'] = hourly_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                hourly_df['total_attacks'] = hourly.sum(axis=1).values
                            
                # 3. Persistence now finds 'timestamp' and succeeds
                
                update_persistent_json(hourly_df, 'hourly_data.json', ['timestamp'])

                # --- DAILY DATA ---
                # Grouping clustered incidents by day and location
                daily = df_incidents.groupby(['day', 'location']).size().unstack(fill_value=0)
                daily_df = daily.reset_index()
                daily_df['day'] = daily_df['day'].dt.strftime('%Y-%m-%d')

                # Initialize Extrapolation to 0 for all days first
                daily_df['Extrapolation'] = 0 

                # Extrapolation Calculation
                now = datetime.now(timezone.utc)
                current_hour = now.hour
                today_str = now.strftime('%Y-%m-%d')

                three_days_ago = (now - pd.Timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
                recent_full_days = df_incidents[
                    (df_incidents['timestamp'] >= three_days_ago) & 
                    (df_incidents['day'] < pd.Timestamp(today_str, tz='UTC'))
                ].copy()

                if not recent_full_days.empty:
                    recent_full_days['hr'] = recent_full_days['timestamp'].dt.hour
                    avg_remaining = recent_full_days[recent_full_days['hr'] > current_hour].groupby('day').size().mean()
                    
                    # Only apply to today's row
                    if today_str in daily_df['day'].values:
                        daily_df.loc[daily_df['day'] == today_str, 'Extrapolation'] = round(avg_remaining if not pd.isna(avg_remaining) else 0)

                daily_df['total_attacks'] = daily.sum(axis=1).values
                daily_df = daily_df[daily_df['day'] >= '2026-02-28']
                update_persistent_json(daily_df, 'daily_data.json', ['day'])

                # --- EXTRAPOLATION & SIGNALS ---
                # Use df_incidents to calculate tempo and escalation
                tempo = df_incidents.groupby('hour').size().rename('attacks').reset_index()
                tempo = tempo.sort_values('hour')
                
                tempo['rolling_6h'] = tempo['attacks'].rolling(6, min_periods=1).mean()
                tempo['rolling_24h'] = tempo['attacks'].rolling(24, min_periods=1).mean()
                
                # Use clustered data for geographic spread
                spread = df_incidents.groupby('hour')['location'].nunique().rename('countries_hit').reset_index()
                signals = tempo.merge(spread, on='hour')
                
                signals['tempo_change'] = (signals['rolling_6h'] / signals['rolling_24h']).fillna(1.0)
                signals['escalation_score'] = (
                    (signals['tempo_change'] * 0.7) + 
                    (signals['countries_hit'] * 0.3)
                ).round(2)
                
                signals['bar_color'] = signals.apply(
                    lambda x: '#ef4444' if x['rolling_6h'] > x['rolling_24h'] else '#94a3b8', 
                    axis=1
                )

                signals['timestamp'] = signals['hour'].dt.strftime('%Y-%m-%d %H:%M')
                update_persistent_json(signals, 'escalation_signals.json', ['timestamp'])

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
        update_persistent_json(history_df, 'summary_history.json', ['date', 'bloc'], rolling_days=0)

        # 3. Export the "Latest" snapshot as before (summary_latest.json)
        summary_str = json.dumps({"asOf": inner_data.get('asOf'), "summary": bloc_totals})
        with open('summary_latest.json', 'w') as f:
            json.dump({"payload": encrypt_data(summary_str)}, f)
        


        print(f"Successfully synced summary and history for: {inner_data.get('asOf')}")

        process_casualties_csv()
        print('✅ Casualties data processed and saved.')
        

    else:
        print(f"Error: Events ({events_res.status_code}) Summary ({summary_res.status_code})")

    if not bdti_ok:
        # Non-zero exit so run_job.sh sends a failure alert
        sys.exit(1)
