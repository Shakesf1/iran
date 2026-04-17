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

def process_missing_shipids(shipids):
    RawURL = "https://www.marinetraffic.com/en/ais/details/ships/shipid:"
    results = []
    for i, shipid in enumerate(list(shipids)):  # Remove [:2] to process all
        url = RawURL + str(shipid)
        print(f"Fetching: {url}")
        co = ChromiumOptions()
        co.set_argument('--no-sandbox')
        co.set_argument('--headless=new')
        co.set_argument('--disable-dev-shm-usage') # Uses /tmp instead of memory (Slower but stable)
        co.set_argument('--disable-gpu')
        profile_path = f'/tmp/chrome_profile_{os.getpid()}'
        co.set_user_data_path(profile_path)
        co.set_paths(local_port=9222)

        ua_list = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ]
        co.set_user_agent(random.choice(ua_list))
        page = None
        imo = 'not found'
        try:
            time.sleep(random.uniform(2, 4))
            page = ChromiumPage(co)
            page.get(url)
            page.wait.ele_displayed('css:.MuiTableRow-root', timeout=20)
            html = page.html
            match = re.search(r'<th[^>]*>IMO</th>\s*<td[^>]*>(\d+)</td>', html)
            if match:
                imo = match.group(1)
                print(f"shipid: {shipid} -> IMO: {imo}")
            else:
                print(f"shipid: {shipid} -> IMO not found")
        except Exception as e:
            print(f"Error fetching/parsing for shipid {shipid}: {e}")
        finally:
            if page:
                page.quit()
        results.append({"shipid": str(shipid), "imo": imo})
    # Convert to DataFrame for inspection
    df = pd.DataFrame(results)
    print(df)
    # Insert all to Supabase in one go
    if not df.empty:
        supabase.table("ship_mapping").insert(df.to_dict(orient="records")).execute()
        print(f"Inserted {len(df)} records into ship_mapping.")

def main():
    # 1. Get all unique shipid from vessel_history
    vh_res = supabase.table("vessel_history").select("shipid").execute()
    all_shipids = set(r["shipid"] for r in vh_res.data if r.get("shipid"))

    # 2. Get all shipid from ship_mapping
    sm_res = supabase.table("ship_mapping").select("shipid").execute()
    mapped_shipids = set(r["shipid"] for r in sm_res.data if r.get("shipid"))

    # 3. Find missing shipids
    missing_shipids = all_shipids - mapped_shipids

    # 4. Process missing shipids
    process_missing_shipids(missing_shipids)

if __name__ == "__main__":
    main()