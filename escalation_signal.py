import json
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
import base64 

# --- CONFIGURATION ---
# Path to your existing data files
DAILY_FILE = 'daily_data.json'
HOURLY_FILE = 'hourly_data.json'
SHIPPING_FILE = 'dashboard_stats.json' # AIS Crossings
OIL_FILE = 'oil_prices_spread.json'    # Historical spread log
OUTPUT_FILE = 'escalation_history.json'
SECRET_KEY = "pay_homage_to_stan_4ever"
def read_encrypted_dict(filename):
    with open(filename, 'r') as f:
        encrypted_blob = json.load(f)
        # 1. Base64 Decode
        scrambled = base64.b64decode(encrypted_blob['payload']).decode('utf-8')
        # 2. XOR Decrypt
        decrypted_str = "".join(chr(ord(c) ^ ord(SECRET_KEY[i % len(SECRET_KEY)])) for i, c in enumerate(scrambled))
        # 3. Return as a standard Dictionary
        return json.loads(decrypted_str)
    

def read_encrypted_df(filename):
    
    with open(filename, 'r') as f:
        encrypted_blob = json.load(f)
        scrambled = base64.b64decode(encrypted_blob['payload']).decode('utf-8')
        decrypted_str = "".join(chr(ord(c) ^ ord(SECRET_KEY[i % len(SECRET_KEY)])) for i, c in enumerate(scrambled))
        from io import StringIO
        return pd.read_json(StringIO(decrypted_str))

def sanitize_data(obj):
    """Recursively convert numpy types to standard python types for clean JSON."""
    if isinstance(obj, dict):
        return {k: sanitize_data(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_data(i) for i in obj]
    elif isinstance(obj, (np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, (np.int64, np.int32)):
        return int(obj)
    return obj

def calculate_history():
    # Load Tables
    df_daily = read_encrypted_df(DAILY_FILE)
    df_hourly = read_encrypted_df(HOURLY_FILE)
    df_oil = read_encrypted_df(OIL_FILE)
    shipping_raw = read_encrypted_dict(SHIPPING_FILE) 

    # --- Pre-process Shipping (Eastbound VLCCs only) ---
    m_daily_counts = {}
    if shipping_raw and 'crossings' in shipping_raw:
        for c in shipping_raw['crossings']:
            day_key = c['time'].split(' ')[0]
            if c['ship_type'] == 'VLCC' and c['dir'] == 'EASTBOUND':
                m_daily_counts[day_key] = m_daily_counts.get(day_key, 0) + 1

    # --- 7-Day Rolling Baseline Logic ---
    dates = pd.date_range(start="2026-02-28", end=datetime.now().strftime('%Y-%m-%d'))
    history_out = []

    for d in dates:
        d_str = d.strftime('%Y-%m-%d')
        window_start = d - timedelta(days=7)
        
        # 1. KINETIC (Strikes)
        # Get actual data for the last 7 days
        mask = (df_daily['day'] >= window_start.strftime('%Y-%m-%d')) & (df_daily['day'] < d_str)
        hist_k = df_daily.loc[mask, 'total_attacks'].tolist()
        
        # PAD: If the window goes before Feb 28, fill with 0 (No strikes before war)
        padding_needed = 7 - len(hist_k)
        rolling_k_vals = ([0] * padding_needed) + hist_k
        
        k_mean = np.mean(rolling_k_vals)
        k_std = np.std(rolling_k_vals) or 1.0 # Avoid div by zero
        
        val_k = df_daily[df_daily['day'] == d_str]['total_attacks'].sum()
        zk = (val_k - k_mean) / k_std

        # 2. MARITIME (Eastbound VLCCs)
        # PAD: Before Feb 28, assume 10 ships passed daily
        hist_m = []
        for i in range(1, 8):
            prev_date = (d - timedelta(days=i)).strftime('%Y-%m-%d')
            hist_m.append(m_daily_counts.get(prev_date, 10.0)) # 10 is the "Peace" baseline
            
        m_mean = np.mean(hist_m)
        m_std = np.std(hist_m) or 1.5 
        
        val_m = m_daily_counts.get(d_str, 10.0)
        # ZM = (Mean - Actual) / Std -> Drop in ships = Rise in Score
        zm = (m_mean - val_m) / m_std

        # 3. ENERGY (Oil Spread)
        # PAD: Assume a spread of 0.0 (Market Parity) before the crisis
        mask_s = (df_oil['date'] >= window_start.strftime('%Y-%m-%d')) & (df_oil['date'] < d_str)
        hist_s = df_oil.loc[mask_s, 'spread'].tolist()
        padding_s = 7 - len(hist_s)
        rolling_s_vals = ([0.0] * padding_s) + hist_s
        
        s_mean = np.mean(rolling_s_vals)
        s_std = np.std(rolling_s_vals) or 0.1
        
        day_s = df_oil[df_oil['date'] == d_str]
        if not day_s.empty:
            val_s = day_s['spread'].values[0]
            zs = (val_s - s_mean) / s_std
        else:
            # Carry over last known Z on weekends
            zs = history_out[-1]['components']['EnergyMarket'] if history_out else 0

        # COMPOSITE (Equally weighted)
        composite = (zk + zm + zs) / 3

        history_out.append({
            "date": d_str,
            "composite": round(composite, 2),
            "components": {
                "Attacks": round(zk, 2),
                "Crossings": round(zm, 2),
                "EnergyMarket": round(zs, 2)
            }
        })

    # Save to file
    history_out = sanitize_data(history_out)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(history_out, f, indent=4)
    
    print(history_out)
    print(f"Escalation History Updated. Composite Z-Score: {history_out[-1]['composite']}")

    df_results = pd.DataFrame(history_out)
    df_results = pd.DataFrame(history_out[1:])
    # Flatten the 'components' column into separate columns
    components_df = df_results['components'].apply(pd.Series)
    df_final = pd.concat([df_results[['date', 'composite']], components_df], axis=1)

    # Rename for clarity if needed
    df_final.columns = ['Date', 'Composite Z', 'Attacks Z', 'Shipping Z', 'Energy Z']

    print("\n" + "="*70)
    print("      REGIONAL ESCALATION MONITOR (7-DAY ROLLING Z-SCORE)")
    print("="*70)
    # Using .to_string() to ensure we see all rows without index
    print(df_final.to_string(index=False, formatters={
        'Composite Z': '{:,.2f}'.format,
        'Attacks Z': '{:,.2f}'.format,
        'Shipping Z': '{:,.2f}'.format,
        'Energy Z': '{:,.2f}'.format
    }))
    print("="*70)

if __name__ == "__main__":
    calculate_history()