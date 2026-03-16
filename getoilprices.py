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
    """Fetches latest Oman price and its source timestamp from Barchart."""
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0"}
    try:
        session.get("https://www.barchart.com/", headers=headers, impersonate="firefox144")
        xsrf_token = unquote(session.cookies.get("XSRF-TOKEN", ""))
        api_headers = {**headers, "X-XSRF-TOKEN": xsrf_token, "Referer": "https://www.barchart.com/"}
        params = {"fields": "lastPrice,tradeTime", "root": Ticker, "lists": "futures.contractInRoot", "raw": "1"}
        
        response = session.get(BARCHART_API, params=params, headers=api_headers, impersonate="firefox144")
        if response.status_code == 200:
            item = response.json()['data'][0]
            price = float(item['lastPrice'])
            # Barchart usually provides tradeTime in ISO format or timestamp
            source_time = item['tradeTime'] 
            return price, source_time
    except Exception as e:
        print(f"Oman Fetch Error: {e}")
    return None, None

def update_intraday_oil():
    """Saves a high-frequency snapshot of the current energy spread."""
    INTRADAY_FILE = 'intraday_oilprices.json'

    price_m, time_m = get_today_commodity_price("DB")
    price_o, time_o = get_today_commodity_price("OQ")

    if price_m and price_o:
        # Save to the new high-frequency file
        intraday_data = {
            "source_time_murban": time_m,
            "source_time_oman": time_o,
            "price_murban": price_m,
            "price_oman": price_o,
            "spread": round(price_o - price_m, 2),
            "fetched_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S') # Our sync time
        }
        new_df = pd.DataFrame([intraday_data])
        update_persistent_json(new_df, "oil_prices_spread_intraday.json", keys=['source_time_oman', 'source_time_murban'], rolling_days=0)
        

        print(f"Intraday Update Success. Spread: {intraday_data['spread']}")


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

if __name__ == "__main__":
    df_spread = get_combined_data()
    print(df_spread)
    if not df_spread.empty:
            # Update the persistent JSON file
            update_persistent_json(df_spread, "oil_prices_spread.json", keys=['date'], rolling_days=3)

    update_intraday_oil()