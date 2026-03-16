from urllib import response

import pandas as pd
from curl_cffi import requests
from urllib.parse import unquote
import io
import os
import json 
import time
import random
from iran import update_persistent_json
from datetime import datetime

# Endpoints
API_URL = "https://oilprice.com/freewidgets/json_get_oilprices"
BARCHART_API = "https://www.barchart.com/proxies/core-api/v1/quotes/get"
BARCHART_CSV_URL = "https://www.barchart.com/proxies/timeseries/historical/queryeod.ashx"

# We use *0 (Nearby) for both to ensure a proper "rolled" comparison
SYMBOL_MURBAN = "DB*1"
SYMBOL_OMAN = "OQ*1"


def get_today_murban():
    """Fetches latest Murban price and its source timestamp from OilPrice.com widget."""
    session = requests.Session()
    payload = {"oilprices": "156"} # 156 is usually the ID for Murban on their widget
    headers = {"Referer": "https://oilprice.com/"}
    
    response = session.post(API_URL, data=payload, headers=headers, impersonate="firefox144")
    if response.status_code == 200:
        data = response.json().get("prices", [])
        if data:
            latest = data[-1] # Get the most recent entry
            # Convert source unix timestamp to readable string
            source_time = datetime.fromtimestamp(int(latest['time'])).strftime('%Y-%m-%d %H:%M:%S')
            return float(latest['price']), source_time
    return None, None

def get_today_commodity_price(Ticker):
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0"}
    try:
        session.get("https://www.barchart.com/", headers=headers, impersonate="firefox144")
        xsrf_token = unquote(session.cookies.get("XSRF-TOKEN", ""))
        api_headers = {**headers, "X-XSRF-TOKEN": xsrf_token, "Referer": "https://www.barchart.com/"}
        
        # We fetch the specific front-month future (root)
        params = {"fields": "symbol,lastPrice,tradeTime", "root": Ticker, "lists": "futures.contractInRoot", "raw": "1"}
        
        response = session.get(BARCHART_API, params=params, headers=api_headers, impersonate="firefox144")
        if response.status_code == 200:
            data = response.json().get('data', [])
            # Find the first real contract (length 5, ignore indices like '00')
            item = next(i for i in data if len(i['symbol']) == 5 and '00' not in i['symbol'])
            
            price = float(str(item['lastPrice']).replace('s', ''))
            source_time = item['tradeTime'] 
            symbol = item['symbol']
            
            return {
                "symbol": symbol,
                "price": price,
                "source_time": source_time,
                "date": datetime.now().strftime('%Y-%m-%d')
            }
    except Exception as e:
        print(f"Error fetching {Ticker}: {e}")
    return None

def update_intraday_oil():
    """Saves individual snapshots for Murban and Oman."""
    # 1. Fetch data for both
    murban = get_today_commodity_price("DB")
    oman = get_today_commodity_price("OQ")
    brent = get_today_commodity_price("QA")
    # 2. Prepare the list for persistent storage
    # We save them as separate entries so they have their own time-series
    updates = []
    if murban:
        murban['name'] = 'Murban'
        updates.append(murban)
    if oman:
        oman['name'] = 'Oman'
        updates.append(oman)
    if brent:
        brent['name'] = 'Brent'
        updates.append(brent)

    print(f"Fetched Intraday Prices: {updates}")
    if updates:
        # Save to the individual status file
        # We use [name, source_time] as keys so we don't save the same tick twice
        for entry in updates:
            entry_df = pd.DataFrame([entry])
            update_persistent_json(
                entry_df, 
                "oil_individual_status.json", 
                keys=['name', 'source_time'], 
                rolling_days=0
            )
        
        # 3. Optional: Logic to align and print the current spread for the logs
        if murban and oman:
            current_spread = round(oman['price'] - murban['price'], 2)
            print(f"✅ Sync Update: Murban ({murban['source_time']}) | Oman ({oman['source_time']}) | Spread: {current_spread} | Brent ({brent['source_time']}) ")


def get_random_user_agent():
    """Returns a random modern user agent to rotate identity."""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
    ]
    return random.choice(user_agents)


def get_barchart_data(symbol):
    """Fetches historical data from Barchart CSV endpoint for a given symbol."""
    session = requests.Session()
    headers = {"User-Agent": get_random_user_agent()}
    
    # Handshake to get session cookies and XSRF token
    random_delay(3, 7)
    session.get("https://www.barchart.com/", headers=headers, impersonate="firefox144")
    xsrf_token = unquote(session.cookies.get("XSRF-TOKEN", ""))
    

    params = {
        "symbol": symbol,
        "data": "dailycontinue",
        "maxrecords": "10000",
        "volume": "contract",
        "order": "asc",
        "dividends": "false",
        "backadjust": "false",
        "daystoexpiration": "3",
        "contractroll": "combined",
        "splits": "true",
        "padded": "false"
    }
    
    api_headers = {
        **headers,
        "x-xsrf-token": xsrf_token,
        "Referer": f"https://www.barchart.com/futures/quotes/{symbol}/interactive-chart"
    }

    random_delay(3, 7)
    response = session.get(BARCHART_CSV_URL, params=params, headers=api_headers, impersonate="firefox144")

    if response.status_code == 200 and response.text:
        # Barchart CSV order: Symbol, Date, Open, High, Low, Close, Volume, OI
        df = pd.read_csv(io.StringIO(response.text), header=None, 
                         names=['symbol', 'date', 'open', 'high', 'low', 'price', 'volume', 'oi'])
        
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df[['date', 'price']]
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        return df
    return pd.DataFrame()

def get_combined_data():
    # 1. Fetch Murban (DB) from Barchart
    print(f"Fetching {SYMBOL_MURBAN} historical data...")
    df_murban = get_barchart_data(SYMBOL_MURBAN)
    
    # 2. Fetch Oman (OQ) from Barchart
    print(f"Fetching {SYMBOL_OMAN} historical data...")
    df_oman = get_barchart_data(SYMBOL_OMAN)

    if df_murban.empty or df_oman.empty:
        print("Error: Could not retrieve data for one or both symbols.")
        return pd.DataFrame()

    # 3. Merge and Calculate Spread
    # We use an inner join to ensure we only compare dates where both have prices
    combined = pd.merge(
        df_oman, 
        df_murban, 
        on='date', 
        how='inner', 
        suffixes=('_oman', '_murban')
    )

    combined['spread'] = combined['price_oman'] - combined['price_murban']
    combined = combined.sort_values('date').reset_index(drop=True)
    
    print("\n--- Oman (OQ) vs Murban (DB) Spread ---")
    print("HEAD:")
    print(combined.head(10))
    print("\nTAIL:")
    print(combined.tail(10))
    
    return combined

def random_delay(min_sec=2, max_sec=10):
    """Introduces a random sleep to mimic human interaction."""
    delay = random.uniform(min_sec, max_sec)
    print(f"Humanizing: Waiting {delay:.2f}s before request...")
    time.sleep(delay)



# --- Keeping existing functions per instructions (Not called) ---
def fetch_series(blend_id, session):
    payload = {"blend_id": str(blend_id), "period": "7", "op_csrf_token": "3ce541ba049eebe598d57b473954756b"}
    headers = {"X-Requested-With": "XMLHttpRequest", "Referer": "https://oilprice.com/oil-price-charts/"}
    response = session.post(API_URL, data=payload, headers=headers, impersonate="firefox144")
    if response.status_code == 200:
        df = pd.DataFrame(response.json().get("prices", []))
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        return df
    return pd.DataFrame()

def get_today_oman():
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0"}
    try:
        session.get("https://www.barchart.com/", headers=headers, impersonate="firefox144")
        xsrf_token = unquote(session.cookies.get("XSRF-TOKEN", ""))
        api_headers = {**headers, "X-XSRF-TOKEN": xsrf_token, "Referer": "https://www.barchart.com/"}
        params = {"fields": "lastPrice,tradeTime", "root": "OQ", "lists": "futures.contractInRoot", "raw": "1"}
        response = session.get(BARCHART_API, params=params, headers=api_headers, impersonate="firefox144")
        if response.status_code == 200:
            item = response.json()['data'][0]
            price = float(item['lastPrice'].replace('s', ''))
            return {'price': price}
    except: pass
    return None

def get_multiple_historical_data(symbols_list=["DB", "QA", "OQ"]):
    """Fetches and merges historical data for multiple symbols into one DataFrame."""
    session = requests.Session()
    headers = {"User-Agent": get_random_user_agent()}
    
    # Initial Handshake
    session.get("https://www.barchart.com/", headers=headers, impersonate="firefox144")
    xsrf_token = unquote(session.cookies.get("XSRF-TOKEN", ""))
    
    combined_df = None

    for symbol in symbols_list:
        print(f"Fetching history for: {symbol}...")
        
        # Note: Using *1 or similar nearby suffix is often required for historical continuation
        ticker = f"{symbol}*1" 
        
        params = {
            "symbol": ticker,
            "data": "dailycontinue",
            "maxrecords": "50", # Adjust as needed for history length
            "volume": "contract",
            "order": "asc",
            "contractroll": "combined"
        }
        
        api_headers = {
            **headers,
            "x-xsrf-token": xsrf_token,
            "Referer": f"https://www.barchart.com/futures/quotes/{ticker}/interactive-chart"
        }

        random_delay(1, 3) # Be gentle with repeated calls
        response = session.get(BARCHART_CSV_URL, params=params, headers=api_headers, impersonate="firefox144")

        if response.status_code == 200 and response.text:
            # Parse CSV: Symbol, Date, Open, High, Low, Close, Volume, OI
            temp_df = pd.read_csv(io.StringIO(response.text), header=None, 
                                 names=['ticker', 'date', 'open', 'high', 'low', 'price', 'volume', 'oi'])
            
            # Clean data
            temp_df['date'] = pd.to_datetime(temp_df['date']).dt.date
            temp_df = temp_df[['date', 'price']].rename(columns={'price': symbol.lower()})
            temp_df[symbol.lower()] = pd.to_numeric(temp_df[symbol.lower()], errors='coerce')

            # Merge into the main DataFrame
            if combined_df is None:
                combined_df = temp_df
            else:
                combined_df = pd.merge(combined_df, temp_df, on='date', how='outer')

    if combined_df is not None:
        # Sort by date and calculate spreads
        combined_df = combined_df.sort_values('date').dropna(subset=['date'])
        
        # Calculations (NaNs are handled automatically by Pandas)
        if 'db' in combined_df and 'qa' in combined_df:
            combined_df['spread_murban_brent'] = combined_df['db'] - combined_df['qa']
        if 'db' in combined_df and 'oq' in combined_df:
            combined_df['spread_oman_murban'] =  combined_df['oq'] -  combined_df['db']
        combined_df = combined_df.rename(columns={
            'db': 'Murban',
            'qa': 'Brent',
            'oq': 'Oman'
        })    
        return combined_df
    


    return pd.DataFrame()



if __name__ == "__main__":
    HistoricalData = get_multiple_historical_data()
    if not HistoricalData.empty:
        # Update the persistent JSON file
        update_persistent_json(HistoricalData, "oil_prices_spread.json", keys=['date'], rolling_days=3)
    print(HistoricalData)
    update_intraday_oil()