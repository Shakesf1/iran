from supabase import create_client, Client
from dotenv import load_dotenv
from DrissionPage import ChromiumPage, ChromiumOptions
import random
import os
import time
import re
import pandas as pd

load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

BATCH_SIZE = 50

def flush_to_supabase(results):
    """Insert a batch of results into ship_mapping."""
    if results:
        supabase.table("ship_mapping").insert(results).execute()
        print(f"  -> Inserted {len(results)} records into ship_mapping.")

def make_browser():
    co = ChromiumOptions()
    co.set_argument('--no-sandbox')
    co.set_argument('--headless=new')
    co.set_argument('--disable-dev-shm-usage')
    co.set_argument('--disable-gpu')
    profile_path = f'/tmp/chrome_profile_{os.getpid()}'
    co.set_user_data_path(profile_path)
    co.set_paths(local_port=9222)
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ]
    co.set_user_agent(random.choice(ua_list))
    return ChromiumPage(co)

def process_missing_shipids(shipids):
    RawURL = "https://www.marinetraffic.com/en/ais/details/ships/shipid:"
    results = []
    page = make_browser()
    for i, shipid in enumerate(list(shipids)):
        url = RawURL + str(shipid)
        print(f"[{i+1}] Fetching: {url}")
        imo = 'not found'
        try:
            time.sleep(random.uniform(2, 4))
            page.get(url)
            page.wait.ele_displayed('css:.MuiTableRow-root', timeout=20)
            html = page.html
            match = re.search(r'<th[^>]*>IMO</th>\s*<td[^>]*>(\d+)</td>', html)
            if match:
                imo = match.group(1)
                print(f"  shipid: {shipid} -> IMO: {imo}")
            else:
                print(f"  shipid: {shipid} -> IMO not found")
        except Exception as e:
            print(f"  Error fetching/parsing for shipid {shipid}: {e}")
            # Browser may have crashed — recreate it and carry on
            try:
                page.quit()
            except Exception:
                pass
            time.sleep(3)
            page = make_browser()

        results.append({"shipid": str(shipid), "imo": imo})

        # Flush every BATCH_SIZE records
        if len(results) >= BATCH_SIZE:
            flush_to_supabase(results)
            results = []

    # Flush any remaining records
    flush_to_supabase(results)
    try:
        page.quit()
    except Exception:
        pass

def fetch_all_shipids(table_name):
    """Fetch ALL unique shipids from a table, bypassing Supabase's 100-row default limit."""
    all_rows = []
    page_size = 100  # Match the server's actual max-rows limit
    offset = 0
    while True:
        res = supabase.table(table_name).select("shipid").range(offset, offset + page_size - 1).execute()
        if not res.data:
            break
        all_rows.extend(res.data)
        print(f"  [{table_name}] Fetched {len(all_rows)} rows so far...")
        if len(res.data) < page_size:
            break
        offset += page_size
    if not all_rows:
        return pd.DataFrame(columns=["shipid"])
    return pd.DataFrame(all_rows)

def main():
    # 1. Get all unique shipid from vessel_history
    res = supabase.rpc("get_unmapped_shipids").execute()
    missing_shipids = set(r["shipid"] for r in res.data)
    print(missing_shipids)
    # 4. Process missing shipids
    process_missing_shipids(missing_shipids)

if __name__ == "__main__":
    main()