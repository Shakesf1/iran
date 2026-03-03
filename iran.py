from curl_cffi import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np

url = "https://iranstrike.com/api/events"

# 1. Fetch data
response = requests.get(url, impersonate="firefox144")

if response.status_code == 200:
    data = response.json()['events']
    df = pd.DataFrame(data)
    
    # 2. Convert and Create Time Buckets
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601')
    df['hour'] = df['timestamp'].dt.floor('h')
    df['day'] = df['timestamp'].dt.floor('D')
    
    # 3. Filter for Origin = IRN
    df_irn = df[df['origin'] == 'IRN'].copy()
    
    if not df_irn.empty:
        # --- HOURLY JSON ---
        hourly = df_irn.groupby(['hour', 'location']).size().unstack(fill_value=0)
        hourly.index = hourly.index.strftime('%Y-%m-%d %H:%M')
        hourly_json = hourly.reset_index().to_json(orient='records')
        with open('hourly_data.json', 'w') as f:
            f.write(hourly_json)

        # --- DAILY JSON WITH EXTRAPOLATION ---
        daily = df_irn.groupby(['day', 'location']).size().unstack(fill_value=0).sort_index()
        
        # 3-Day Avg Logic
        last_3_days = daily.sum(axis=1).tail(3)
        avg_pace = last_3_days.mean()
        last_day_dt = daily.index[-1]
        
        # Calculate Extrapolation
        now = datetime.now(last_day_dt.tzinfo)
        extra = 0
        if last_day_dt.date() == now.date():
            hours_passed = now.hour + (now.minute / 60)
            extra = avg_pace * ((24 - hours_passed) / 24) if hours_passed < 24 else 0
        
        daily['Extrapolation'] = 0.0
        daily.loc[last_day_dt, 'Extrapolation'] = extra
        
        # Export Daily
        daily.index = daily.index.strftime('%Y-%m-%d')
        daily_json = daily.reset_index().to_json(orient='records')
        with open('daily_data.json', 'w') as f:
            f.write(daily_json)
else:
    print(f"Error: {response.status_code}")