import argparse
import io
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv
from browser_util import make_browser
from pg_client import get_client

load_dotenv()
supabase = get_client()

# Endpoints
API_URL = "https://oilprice.com/freewidgets/json_get_oilprices"
BARCHART_API = "https://www.barchart.com/proxies/core-api/v1/quotes/get"
BARCHART_CSV_URL = "https://www.barchart.com/proxies/timeseries/historical/queryeod.ashx"
ASHX_URL = "https://www.barchart.com/proxies/timeseries/historical/queryminutes.ashx"

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

_BLOCK_MARKERS = (
    'just a moment', 'attention required', 'cf-browser-verification',
    'cf_chl_', 'challenge-platform', 'enable javascript and cookies',
    'checking your browser', 'cloudflare ray id',
)

def _make_browser():
    return make_browser('oil_scraper', random.choice(UA_LIST))

def random_delay(min_sec=3, max_sec=7):
    time.sleep(random.uniform(min_sec, max_sec))

def _diagnose_failure(page, label):
    html = page.html or ''
    lower = html.lower()
    hit = next((m for m in _BLOCK_MARKERS if m in lower), None)
    if hit:
        print(f'    {label}: BLOCKED — Cloudflare challenge detected (matched "{hit}")', file=sys.stderr)
    else:
        snippet = re.sub(r'\s+', ' ', html).strip()[:200]
        print(f'    {label}: no block detected, but no usable data either — page snippet: {snippet!r}', file=sys.stderr)

def fetch_barchart_history_via_browser(page, ticker, name):
    """Fetches historical CSV data from Barchart by intercepting the queryeod.ashx network packet."""
    chart_url = f"https://www.barchart.com/futures/quotes/{ticker}/interactive-chart"
    
    try:
        # Start listening for the endpoint like msci_scraper.py does
        page.listen.start("queryeod.ashx")
        
        print(f"    Navigating to chart page for {name}...")
        page.get(chart_url)
        random_delay(4, 8)

        # Wait for the network packet containing the CSV payload
        packet = page.listen.wait(timeout=25)
        text_content = None

        if packet and packet.response and packet.response.body:
            body = packet.response.body
            text_content = body.decode('utf-8') if isinstance(body, bytes) else str(body)
        else:
            text_content = page.html

        page.listen.stop()

        if not text_content or any(marker in text_content.lower() for marker in _BLOCK_MARKERS):
            _diagnose_failure(page, f"fetch-{name}")
            return []

        # Clean up any HTML wrapping if present
        if "<pre" in text_content:
            match = re.search(r'<pre[^>]*>(.*?)</pre>', text_content, re.DOTALL)
            if match:
                text_content = match.group(1)

        text_content = text_content.strip()
        if "Symbol," in text_content or "," in text_content:
            df = pd.read_csv(io.StringIO(text_content), header=None, 
                             names=['ticker', 'date', 'open', 'high', 'low', 'price', 'volume', 'oi'])
            df['commodity'] = name
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            return df[['ticker', 'date', 'price', 'commodity']].to_dict(orient='records')
            
    except Exception as e:
        print(f"    Error fetching history for {name}: {e}", file=sys.stderr)
        try:
            page.listen.stop()
        except:
            pass
    return []

def main():
    print(f'[{datetime.now(timezone.utc).isoformat()}] Starting oil price scraper with headless browser...')
    
    page = _make_browser()
    symbols = [("DB", "Murban"), ("QA", "Brent"), ("OQ", "Oman")]
    pushed = 0

    try:
        print("  Warming session on barchart.com ...")
        page.get('https://www.barchart.com')
        random_delay(4, 8)

        for symbol, name in symbols:
            ticker = f"{symbol}*1"
            print(f"Fetching history for: {name} (Ticker: {ticker})...")
            
            records = fetch_barchart_history_via_browser(page, ticker, name)

            if records:
                max_date = max(r['date'] for r in records)
                two_days_ago = (datetime.strptime(max_date, '%Y-%m-%d') - timedelta(days=2)).strftime('%Y-%m-%d')
                
                supabase.from_("oilprices") \
                        .delete() \
                        .eq("commodity", name) \
                        .gte("date", two_days_ago) \
                        .execute()

                supabase.from_("oilprices").upsert(
                    records, 
                    on_conflict="ticker,date", 
                    ignore_duplicates=True
                ).execute()

                print(f"    pushed {len(records)} record(s) for {name}")
                pushed += 1
            else:
                print(f"    FAILED — no data retrieved for {name}")

            random_delay(5, 10)
    finally:
        page.quit()

    if pushed == 0:
        print('ERROR: no oil data could be fetched at all', file=sys.stderr)
        sys.exit(1)

    print(f'[{datetime.now(timezone.utc).isoformat()}] Done')

if __name__ == "__main__":
    main()