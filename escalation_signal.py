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
BDTI_FILE = 'shipping_data.json'  # BDI data file
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
    bdti = read_encrypted_dict(BDTI_FILE) 
    #df_oil = df_oil.ffill(axis=0)


    df_daily['total_attacks'] = df_daily['total_attacks'] + df_daily['Extrapolation'] # Combine actual + extrapolated for the most recent days


    # --- Pre-process Shipping (Eastbound VLCCs only) ---
    m_daily_counts = {}
    if shipping_raw and 'crossings' in shipping_raw:
        for c in shipping_raw['crossings']:
            day_key = c['time'].split(' ')[0]
            if c['ship_type'] == 'VLCC' and c['dir'] == 'EASTBOUND':
                m_daily_counts[day_key] = m_daily_counts.get(day_key, 0) + 1

    # --- Pre-process BDTI Data with Log Returns ---
    df_bdti = pd.DataFrame(bdti)
    df_bdti['date'] = pd.to_datetime(df_bdti['date'])
    df_bdti = df_bdti.sort_values('date')

    # Calculate log returns
    df_bdti['log_return'] = np.log(df_bdti['bdti_price'] / df_bdti['bdti_price'].shift(1))

    # Initialize expanding window variables
    ewma_bdti_mean = None
    ewma_bdti_std = None

    # Start calculations well before March 1st
    all_dates = pd.date_range(start=df_bdti['date'].min(), end=df_bdti['date'].max())
    df_bdti = df_bdti.set_index('date').reindex(all_dates).rename_axis('date').reset_index()

    # Forward-fill missing values for continuity
    df_bdti['log_return'] = df_bdti['log_return'].fillna(0.0)

    # --- Adjust Oil Spread Handling ---
    df_oil['spread_murban_brent'] = df_oil['spread_murban_brent'].ffill(axis=0)
    raw_oil_std = df_oil['spread_murban_brent'].std(skipna=True)

    # --- 7-Day Rolling Baseline Logic ---
    dates = pd.date_range(start="2026-02-28", end=datetime.now().strftime('%Y-%m-%d'))
    history_out = []

    ewma_attacks = None
    ewma_attacks_std = None
    ewma_shipping = None
    ewma_shipping_std = None
    ewma_energy = None
    ewma_energy_std = None

    for idx, d in enumerate(dates):
        d_str = d.strftime('%Y-%m-%d')
        window_start = d - timedelta(days=7)

        # 1. KINETIC (Strikes)
        mask = (df_daily['day'] >= window_start.strftime('%Y-%m-%d')) & (df_daily['day'] < d_str)
        hist_k = df_daily.loc[mask, 'total_attacks'].tolist()

        if idx < 7:
            # Use rolling mean and std for the first 7 days
            padding_needed = 7 - len(hist_k)
            rolling_k_vals = ([0] * padding_needed) + hist_k
            k_mean = np.mean(rolling_k_vals)
            k_std = np.std(rolling_k_vals) or 1.0
        else:
            # Use EWMA after 7 days
            val_k = df_daily[df_daily['day'] == d_str]['total_attacks'].sum()
            ewma_attacks = (ewma_attacks * 0.97 + val_k * (1 - 0.97)) if ewma_attacks is not None else np.mean(hist_k)
            ewma_attacks_std = (ewma_attacks_std * 0.97 + ((val_k - ewma_attacks) ** 2) * (1 - 0.97)) if ewma_attacks_std is not None else np.std(hist_k)
            k_mean = ewma_attacks
            k_std = np.sqrt(ewma_attacks_std)

        val_k = df_daily[df_daily['day'] == d_str]['total_attacks'].sum()
        zk = (val_k - k_mean) / k_std

        # 2. MARITIME (Eastbound VLCCs)
        hist_m = []
        for i in range(1, 8):
            prev_date = (d - timedelta(days=i)).strftime('%Y-%m-%d')
            hist_m.append(m_daily_counts.get(prev_date, 0.0))

        # Assume 0 ships passed between March 1st and March 6th, with mean 10 and std 1.5
        if '2026-03-01' <= d_str <= '2026-03-06':
            val_m = 0.0
        else:
            val_m = m_daily_counts.get(d_str, 0.0)

        # Transform shipping value
        zm = -1 * ((val_m - 5) / 2)

        # 3. ENERGY (Oil Spread)
        mask_s = (df_oil['date'] >= window_start.strftime('%Y-%m-%d')) & (df_oil['date'] < d_str)
        hist_s = df_oil.loc[mask_s, 'spread_murban_brent'].tolist()

        if idx < 7:
            padding_s = 7 - len(hist_s)
            rolling_s_vals = ([0.0] * padding_s) + hist_s
            s_mean = np.mean(rolling_s_vals)
            s_std = raw_oil_std  # Use raw standard deviation without carry-forward
        else:
            day_s = df_oil[df_oil['date'] == d_str]
            val_s = day_s['spread_murban_brent'].values[0] if not day_s.empty else 0.0
            ewma_energy = (ewma_energy * 0.97 + val_s * (1 - 0.97)) if ewma_energy is not None else np.mean(hist_s)
            ewma_energy_std = (ewma_energy_std * 0.97 + ((val_s - ewma_energy) ** 2) * (1 - 0.97)) if ewma_energy_std is not None else raw_oil_std
            s_mean = ewma_energy
            s_std = np.sqrt(ewma_energy_std)

        day_s = df_oil[df_oil['date'] == d_str]
        val_s = day_s['spread_murban_brent'].values[0] if not day_s.empty else 0.0
        zs = (val_s - s_mean) / s_std

        # 4. BDTI (Baltic Dirty Tanker Index with Log Returns)
        mask_bdti = (df_bdti['date'] >= window_start.strftime('%Y-%m-%d')) & (df_bdti['date'] < d_str)
        hist_bdti = df_bdti.loc[mask_bdti, 'log_return'].tolist()

        if idx < 7:
            padding_bdti = 7 - len(hist_bdti)
            rolling_bdti_vals = ([0.0] * padding_bdti) + hist_bdti
            bdti_mean = np.mean(rolling_bdti_vals)
            bdti_std = np.std(rolling_bdti_vals) or 1.0
        else:
            day_bdti = df_bdti[df_bdti['date'] == d_str]
            val_bdti = day_bdti['log_return'].values[0] if not day_bdti.empty else 0.0
            ewma_bdti_mean = (ewma_bdti_mean * 0.97 + val_bdti * (1 - 0.97)) if ewma_bdti_mean is not None else np.mean(hist_bdti)
            ewma_bdti_std = (ewma_bdti_std * 0.97 + ((val_bdti - ewma_bdti_mean) ** 2) * (1 - 0.97)) if ewma_bdti_std is not None else np.std(hist_bdti)
            bdti_mean = ewma_bdti_mean
            bdti_std = np.sqrt(ewma_bdti_std)

        day_bdti = df_bdti[df_bdti['date'] == d_str]
        val_bdti = day_bdti['log_return'].values[0] if not day_bdti.empty else 0.0
        zbdti = (val_bdti - bdti_mean) / bdti_std


        
        # Update composite score to include BDTI
        composite = (0.2 * zk + 0.2 * zm + 0.3 * zs + 0.3 * zbdti)
        composite = max(min(composite, 3), -3)  # Limit composite score between -3 and 3

        history_out.append({
            "date": d_str,
            "composite": round(composite, 2),
            "components": {
                "Attacks": round(zk, 2),
                "Crossings": round(zm, 2),
                "EnergyMarket": round(zs, 2),
                "BDTI": round(zbdti, 2)
            }
        })

    # Save to file
    history_out = sanitize_data(history_out)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(history_out, f, indent=4)
    

    print(f"Escalation History Updated. Composite Z-Score: {history_out[-1]['composite']}")

    df_results = pd.DataFrame(history_out)
    df_results = pd.DataFrame(history_out[1:])
    # Flatten the 'components' column into separate columns
    components_df = df_results['components'].apply(pd.Series)
    df_final = pd.concat([df_results[['date', 'composite']], components_df], axis=1)

    # Rename for clarity if needed
    df_final.columns = ['Date', 'Composite Z', 'Attacks Z', 'Shipping Z', 'Energy Z', 'BDTI Z']

    print("\n" + "="*70)
    print("      REGIONAL ESCALATION MONITOR (0.97 decay expanding window ROLLING Z-SCORE)")
    print("="*70)
    # Using .to_string() to ensure we see all rows without index
    print(df_final.to_string(index=False, formatters={
        'Composite Z': '{:,.2f}'.format,
        'Attacks Z': '{:,.2f}'.format,
        'Shipping Z': '{:,.2f}'.format,
        'Energy Z': '{:,.2f}'.format,
        'BDTI Z': '{:,.2f}'.format
    }))
    print("="*70)



if __name__ == "__main__":
    calculate_history()