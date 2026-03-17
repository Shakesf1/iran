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
    # Load Tables (Keep your existing encrypted loading logic)
    df_daily = read_encrypted_df(DAILY_FILE)
    df_oil = read_encrypted_df(OIL_FILE)
    shipping_raw = read_encrypted_dict(SHIPPING_FILE) 
    bdti = read_encrypted_dict(BDTI_FILE) 
    
    # Process inputs
    df_daily['total_attacks'] = df_daily['total_attacks'] + df_daily['Extrapolation']
    df_bdti = pd.DataFrame(bdti).sort_values('date')
    df_bdti['date'] = pd.to_datetime(df_bdti['date'])

    # --- Pre-process Shipping ---
    m_daily_counts = {}
    if shipping_raw and 'crossings' in shipping_raw:
        for c in shipping_raw['crossings']:
            day_key = c['time'].split(' ')[0]
            if c['ship_type'] == 'VLCC' and c['dir'] == 'EASTBOUND':
                m_daily_counts[day_key] = m_daily_counts.get(day_key, 0) + 1

    dates = pd.date_range(start="2026-02-28", end=datetime.now().strftime('%Y-%m-%d'))
    history_out = []

    # Initialize EWMA states
    states = {
        'attacks': {'mean': None, 'var': None},
        'energy': {'mean': None, 'var': None},
        'bdti': {'mean': None, 'var': None}
    }

    for idx, d in enumerate(dates):
        d_str = d.strftime('%Y-%m-%d')
        
        # --- 1. KINETIC (Attacks) ---
        # --- 1. KINETIC (Attacks) - Updated with 7-Day Warmup ---
        val_k = df_daily[df_daily['day'] == d_str]['total_attacks'].sum()
        
        # Get all attack data recorded up to this loop date
        attacks_so_far = df_daily[df_daily['day'] <= d_str]['total_attacks'].tolist()
        num_days_in = len(attacks_so_far)

        if num_days_in <= 7:
            # PHASE 1: Rolling 7-day window using "Ghost" zeros for pre-war days
            ghost_zeros = [0.0] * (7 - num_days_in)
            effective_window = ghost_zeros + attacks_so_far
            
            k_mean = np.mean(effective_window)
            k_std = np.std(effective_window)
            
            # Prevent division by zero
            if k_std == 0: k_std = 1.0
            
            zk = (val_k - k_mean) / k_std

            # SEED THE STATE: On exactly Day 7, prepare the mean/var for Day 8's EWMA
            if num_days_in == 7:
                states['attacks']['mean'] = k_mean
                states['attacks']['var'] = k_std**2
        else:
            # PHASE 2: Expanding Window (0.97 decay)
            # This only runs starting Day 8, so mean is guaranteed to not be None
            k_mean = states['attacks']['mean']
            k_std = np.sqrt(states['attacks']['var'])
            
            zk = (val_k - k_mean) / k_std
            
            # Update the EWMA state for the next day in the loop
            states['attacks']['mean'] = k_mean * 0.97 + val_k * 0.03
            states['attacks']['var'] = states['attacks']['var'] * 0.97 + ((val_k - k_mean)**2) * 0.03

        # --- 2. MARITIME (Shipping) ---
        # Keep your hardcoded baseline for shipping to represent "Normalcy"
        val_m = 0.0 if '2026-03-01' <= d_str <= '2026-03-06' else m_daily_counts.get(d_str, 0.0)
        zm = -1 * ((val_m - 5) / 2)

        # --- 3. ENERGY (Oil Spread) ---
        # Only look at oil data available up to today
        current_oil = df_oil[df_oil['date'] <= d_str]['spread_murban_brent'].ffill()
        val_s = current_oil.iloc[-1] if not current_oil.empty else 0.0
        
        if states['energy']['mean'] is None:
            states['energy']['mean'], states['energy']['var'] = val_s, (df_oil['spread_murban_brent'].std() or 1.0)
            
        zs = (val_s - states['energy']['mean']) / np.sqrt(states['energy']['var'])
        states['energy']['mean'] = states['energy']['mean'] * 0.97 + val_s * 0.03
        states['energy']['var'] = states['energy']['var'] * 0.97 + ((val_s - states['energy']['mean'])**2) * 0.03

        # --- 4. BDTI (Log Returns) ---
        # Calculate log return only using today and yesterday
        price_today = df_bdti[df_bdti['date'] <= d]['bdti_price'].iloc[-1]
        price_yesterday = df_bdti[df_bdti['date'] < d]['bdti_price'].iloc[-1] if any(df_bdti['date'] < d) else price_today
        val_bdti = np.log(price_today / price_yesterday) if price_yesterday != 0 else 0.0

        if states['bdti']['mean'] is None:
            states['bdti']['mean'], states['bdti']['var'] = val_bdti, 0.01 # Small seed variance for returns
            
        zbdti = (val_bdti - states['bdti']['mean']) / np.sqrt(states['bdti']['var'] + 1e-6)
        states['bdti']['mean'] = states['bdti']['mean'] * 0.97 + val_bdti * 0.03
        states['bdti']['var'] = states['bdti']['var'] * 0.97 + ((val_bdti - states['bdti']['mean'])**2) * 0.03

        # --- COMPOSITE ---
        composite = (0.2 * zk + 0.2 * zm + 0.3 * zs + 0.3 * zbdti)
        composite = max(min(composite, 3), -3)

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