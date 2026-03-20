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
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()    
 # Supabase
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY") # Use Service Role for backend writes


supabase: Client = create_client(url, key)
# Endpoints
API_URL = "https://oilprice.com/freewidgets/json_get_oilprices"
BARCHART_API = "https://www.barchart.com/proxies/core-api/v1/quotes/get"
BARCHART_CSV_URL = "https://www.barchart.com/proxies/timeseries/historical/queryeod.ashx"
BARCHART_API_HIST = "https://www.barchart.com/proxies/core-api/v1/historical/get"

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
                keys=['name', 'source_time', 'date', 'price'], 
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
        "data": "dailyNearest",
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

def get_multiple_historical_data(symbols_list=["DB", "QA", "OQ"], commodity_name=["Murban", "Brent", "Oman"]):
    """Fetches and merges historical data for multiple symbols into one DataFrame."""
    session = requests.Session()
    headers = {"User-Agent": get_random_user_agent()}
    
    # Initial Handshake
    session.get("https://www.barchart.com/", headers=headers, impersonate="firefox144")
    xsrf_token = unquote(session.cookies.get("XSRF-TOKEN", ""))
    
    combined_df = None

    for symbol, name in zip(symbols_list, commodity_name):
        print(f"Fetching history for: {name} (Ticker: {symbol})...")

        
        # Note: Using *1 or similar nearby suffix is often required for historical continuation
        ticker = f"{symbol}*1" 
        
        params = {
        "symbol": ticker,
        "data": "dailyNearest",     # This tells the API to switch contracts automatically
        "maxrecords": "30", # Increase if we need more history. Now we keep it short to 30 days. 
        "volume": "contract",
        "order": "asc",
        "backadjust": "false",      # Set to "false" to get unadjusted front-month prices
        "daystoexpiration": "3",    # Critical: Tells it when to "roll" to the next month
        "contractroll": "combined", # Ensures it stitches different months into one CSV
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
            temp_df['commodity']= name
            # Clean data
            temp_df['date'] = pd.to_datetime(temp_df['date'])

            max_date = temp_df['date'].max()
            two_days_ago = (max_date - timedelta(days=2)).strftime('%Y-%m-%d')
            print(f"Cleaning {name} records from {two_days_ago} onwards...")

            supabase.table("oilprices") \
                    .delete() \
                    .eq("commodity", name) \
                    .gte("date", two_days_ago) \
                    .execute()
            

            records_df = temp_df[['ticker', 'date', 'price', 'commodity']].copy()
            records_df['date'] = records_df['date'].dt.strftime('%Y-%m-%d')

            # 5. Convert to dict and upload
            records = records_df.to_dict(orient='records')
            supabase.table("oilprices").upsert(
                records, 
                on_conflict="ticker,date", # Matches your unique constraint columns
                ignore_duplicates=True      # Skips the row if it already exists
            ).execute()


            

            temp_df['date'] = temp_df['date'].dt.date
            temp_df = temp_df[['date', 'price']].rename(columns={'price': symbol.lower()})
            temp_df = temp_df.sort_values('date').drop_duplicates(subset=['date'], keep='last')
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

def get_multiple_historical_intraday_data(symbols_list=["DB", "QA", "OQ"], commodity_name=["Murban", "Brent", "Oman"]):
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0"}
    
    # Handshake
    session.get("https://www.barchart.com/", headers=headers, impersonate="firefox144")
    xsrf_token = unquote(session.cookies.get("XSRF-TOKEN", ""))

    all_data = []

    # The NEW URL you discovered
    ASHX_URL = "https://www.barchart.com/proxies/timeseries/historical/queryminutes.ashx"

    for symbol, name in zip(symbols_list, commodity_name):
        # Using the front month (or root symbol with nearby suffix)
        try:
            res = supabase.table("oilprices") \
                .select("ticker") \
                .eq("commodity", name) \
                .order("date", desc=True) \
                .limit(1) \
                .execute()
            
            if res.data and len(res.data) > 0:
                ticker = res.data[0]['ticker']
                print(f"🔍 Found latest ticker for {name} in DB: {ticker}")
            else:
                
                print(f"⚠️ No ticker in DB for {name}. Skipping {name}.")
                continue
        except Exception as e:
            
            print(f"❌ Supabase lookup failed: {e}. Skipping {name}.")
            continue

        params = {
            "symbol": ticker,
            "interval": "5",          # 5-minute bars
            "maxrecords": "500",      # Last 500 minutes
            "volume": "contract",
            "order": "asc",
            "daystoexpiration": "1",
            "contractroll": "combined"
        }
        
        api_headers = {
            **headers,
            "x-xsrf-token": xsrf_token,
            "Referer": f"https://www.barchart.com/futures/quotes/{ticker}/overview"
        }

        response = session.get(ASHX_URL, params=params, headers=api_headers, impersonate="firefox144")

        if response.status_code == 200 and response.text:
            # The .ashx endpoint returns text/plain CSV data
            # Format is usually: Symbol, Timestamp, Open, High, Low, Close, Volume
            from io import StringIO
            
            # Use read_csv but handle the fact it has no header
            try:

                df = pd.read_csv(
                        StringIO(response.text), 
                        header=None, 
                        names=['raw_time', 'day_num', 'open', 'high', 'low', 'price', 'volume']
                    )
                    
                # 2. Fix the Index shift
                # If the date string is stuck in the index, move it to 'date_string'
                if not isinstance(df.index, pd.RangeIndex):
                    df = df.reset_index()
                    df.rename(columns={df.columns[0]: 'date_string'}, inplace=True)
                else:
                    df['date_string'] = df['raw_time']

                # 3. CONVERT THE CORRECT COLUMN
                # We use the 'date_string' column which has "2026-02-03 20:55"
                df['formatted_date'] = pd.to_datetime(df['date_string']).dt.strftime('%Y-%m-%d %H:%M:%S')
                
                # 4. Final selection with the correct 'name' variable from your loop
                records_df = pd.DataFrame()
                records_df['ticker'] = [ticker] * len(df)
                records_df['datetime'] = df['formatted_date']
                records_df['price'] = df['price']
                records_df['commodity'] = name # This 'name' comes from your for-loop zip
                

                # 5. Convert to dict and upload
                records = records_df.to_dict(orient='records')
                #print(records)

                supabase.table("oilprices_intraday").upsert(
                    records, 
                    on_conflict="ticker,datetime", # Matches your unique constraint columns
                    ignore_duplicates=True      # Skips the row if it already exists
                ).execute()


                print(records_df)
     
                #print(f"✅ Retrieved {len(records)} CSV rows for {name}")
                
            except Exception as e:
                print(f"⚠️ Parsing error for {name}: {e}. Response was: {response.text[:50]}")

    return pd.DataFrame(all_data)

def export_spreads_to_json(filename="oil_prices_spread.json"):
    try:
        # 1. Call the RPC function we created in Step 1
        response = supabase.rpc("get_oil_spreads").execute()
        
        # 2. Extract the data
        data = response.data # This is already a list of dictionaries
        print(pd.DataFrame(data).head())
        if not data:
            print("⚠️ No synchronized data found for Murban and Brent.")
            return

        new_df = pd.DataFrame(data)
        keys_to_track = ['datetime']
        if os.path.exists(filename):
            os.remove(filename)

        update_persistent_json(
                    new_df=new_df, 
                    filename=filename, 
                    keys=keys_to_track, 
                    rolling_days=0
                )
            
        print(f"✅ Successfully saved {len(data)} rows to {filename}")

    except Exception as e:
        print(f"❌ Error: {e}")



if __name__ == "__main__":
    get_multiple_historical_data() # Get end of day prices 
    export_spreads_to_json(filename='oil_prices_spread_intraday.json') # Save to json from supabase
    #print(HistoricalData)
    get_multiple_historical_intraday_data() # Get itnraday prices 
    export_spreads_to_json(filename='oil_prices_spread.json') # Save to json