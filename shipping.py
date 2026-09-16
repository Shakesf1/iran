
import time
import random
import json
import base64
import httpx
from datetime import datetime, timedelta
from DrissionPage import ChromiumPage, ChromiumOptions
import geopandas as gpd
from shapely.geometry import Point
from supabase import create_client, Client
from dotenv import load_dotenv
import os
import sys 

# def force_print(msg):
#     print(msg)
#     sys.stdout.flush()

# force_print("--- START ENV DEBUG ---")
# for env_var in ["SUPABASE_URL", "SUPABASE_KEY", "GITHUB_ACTIONS", "DISPLAY"]:
#     val = os.environ.get(env_var)
#     force_print(f"{env_var}: {'[PRESENT]' if val else '[MISSING]'}")
#     if env_var == "SUPABASE_URL" and val:
#         force_print(f"URL Start: {val[:10]}...") 
#     if env_var == "SUPABASE_KEY" and val:
#         force_print(f"KEY Start: {val[:10]}...")     
# force_print("--- END ENV DEBUG ---")


load_dotenv()    
# Get the absolute path of the folder containing shipping.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Update your paths to be absolute

JSON_PATH = os.path.join(BASE_DIR, "dashboard_stats.json")
HORMUZ_TRANSITS_PATH = os.path.join(BASE_DIR, "hormuz_transits.json")
CROSSINGS_HISTORY_PATH = os.path.join(BASE_DIR, "crossings_history.json")

# --- CONFIGURATION ---
CHOKEPOINTS = [
    "https://www.marinetraffic.com/en/ais/home/centerx:57.5/centery:24.9/zoom:10", # Hormuz
    "https://www.marinetraffic.com/en/ais/home/centerx:57.5/centery:25.9/zoom:10",
    "https://www.marinetraffic.com/en/ais/home/centerx:56.7/centery:26.6/zoom:10",
    "https://www.marinetraffic.com/en/ais/home/centerx:55.1/centery:26.0/zoom:10",
    "https://www.marinetraffic.com/en/ais/home/centerx:53.0/centery:25.2/zoom:9",
    "https://www.marinetraffic.com/en/ais/home/centerx:51.9/centery:26.9/zoom:9",
    "https://www.marinetraffic.com/en/ais/home/centerx:50.9/centery:28.6/zoom:9",
    "https://www.marinetraffic.com/en/ais/home/centerx:58.6/centery:24.5/zoom:9",
    "https://www.marinetraffic.com/en/ais/home/centerx:45.4/centery:14.4/zoom:7", # Bab al-Mandab
    "https://www.marinetraffic.com/en/ais/home/centerx:29.7/centery:30.3/zoom:7"  # Suez
]

#CHOKEPOINTS = ['https://www.marinetraffic.com/en/ais/home/centerx:56.7/centery:26.6/zoom:10']

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY") # Use Service Role for backend writes


supabase: Client = create_client(url, key)
supabase.postgrest.session.timeout = httpx.Timeout(120.0)
#HORMUZ_GATE_LON = 56.3  # The tripwire for the Strait chokepoint

WEST_LIMIT = 56.33  # Deep in the Gulf
EAST_LIMIT = 56.45  # Well out into the Gulf of Oman


SECRET_KEY = "pay_homage_to_stan_4ever"

def encrypt_data(data_string, key=SECRET_KEY):
# 1. Apply XOR Cipher using the key
    # This cycles through the key and XORs each character of the data
    xor_data = "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(data_string))
    
    # 2. Base64 encode the XOR'd result so it can be saved in JSON
    encoded = base64.b64encode(xor_data.encode('utf-8')).decode('utf-8')
    return encoded



def update_vessel_locations():
    """Classifies vessel positions as water, bad, or coastal_noise using spatial data in Supabase."""
    print("--- Classifying vessel locations via GeoPandas ---")

    # Load land geometry once — expensive, don't repeat per batch
    land = gpd.read_file("./ne_10m_land/ne_10m_land.shp")
    land_geom = land.to_crs(epsg=3857).union_all()
    land_buffer = land_geom.buffer(200)

    BATCH_SIZE = 200
    total_classified = 0

    while True:
        response = supabase.table("vessel_history") \
            .select("id, longitude, latitude") \
            .is_("location", "null") \
            .limit(BATCH_SIZE) \
            .execute()

        rows = response.data
        if not rows:
            break

        row_ids = [r['id'] for r in rows]
        lons = [r['longitude'] for r in rows]
        lats = [r['latitude'] for r in rows]

        try:
            points_m = gpd.GeoSeries(
                [Point(x, y) for x, y in zip(lons, lats)],
                crs="EPSG:4326"
            ).to_crs(epsg=3857)

            updates = []
            for i, p in enumerate(points_m):
                if land_geom.contains(p):
                    label = "bad"
                elif land_buffer.contains(p):
                    label = "coastal_noise"
                else:
                    label = "water"
                updates.append({"id": row_ids[i], "location": label})

            supabase.table("vessel_history").upsert(updates).execute()
            total_classified += len(updates)
            print(f"  Classified {len(updates)} records (total so far: {total_classified})")
            time.sleep(2)  # let Postgres recover between batches

        except Exception as e:
            print(f"Batch processing error: {e}")
            break

    print(f"Done. Classified {total_classified} records total.")


def get_ships_with_stealth(map_url):
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
    try:
        time.sleep(random.uniform(2, 4))
        page = ChromiumPage(co)
        page.listen.start('get_data_json')
        page.get(map_url)
        page.wait.ele_displayed('css:.leaflet-container', timeout=35)

        time.sleep(random.uniform(4, 6))  # Wait for tile packets to arrive

        all_ships = {}  # keyed by SHIP_ID to deduplicate across tiles
        while True:
            packet = page.listen.wait(timeout=10)
            if not packet:
                break  # no more packets arriving
            if not packet.response.body:
                continue
            try:
                body = packet.response.body
                parsed = body if isinstance(body, dict) else json.loads(body)
                rows = parsed.get("data", {}).get("rows", [])
                for ship in rows:
                    all_ships[ship.get("SHIP_ID")] = ship
                if rows:
                    print(f"  Tile packet: {len(rows)} ships (running total: {len(all_ships)})")
            except Exception:
                continue

        if not all_ships:
            print("⚠️ No ship data captured.")
            return None

        print(f"✅ Collected {len(all_ships)} unique ships across all tile packets.")
        return {"data": {"rows": list(all_ships.values())}}
    except Exception as e:
        print(f"Scraping Error: {e}")
        return None
    finally:
        if page:
            page.quit()

def process_and_save(strait_data):

    if isinstance(strait_data, str):
            try:
                strait_data = json.loads(strait_data)
            except Exception as e:
                print(f"Error parsing JSON string: {e}")
                return

    if not strait_data or 'data' not in strait_data:
        return

    rows = strait_data.get("data", {}).get("rows", [])


# --- DEBUG START ---
    # Check if the target ship ID is present in the RAW rows
    target_id = '5835738'
    found_in_raw = any(str(ship.get('SHIP_ID')) == target_id for ship in rows)
    if found_in_raw:
        print(f"🎯 DEBUG: Target ship {target_id} FOUND in raw JSON rows!")
    else:
        # This helps confirm if the scraper is even seeing the ship on the map
        print(f"🔍 DEBUG: Target ship {target_id} NOT found in this packet ({len(rows)} ships total).")
    # --- DEBUG END ---

    vessels_to_insert = []
    for ship in rows:
        try:
            # MarineTraffic API fields are often strings in dict format
            vessel_record = {
                "shipid": str(ship.get('SHIP_ID')),
                "name": ship.get('SHIPNAME', 'Unknown'),
                "longitude": float(ship.get('LON') or 0),
                "latitude": float(ship.get('LAT') or 0),
                "ship_type": int(ship.get('SHIPTYPE') or 0),
                "speed": float(ship.get('SPEED') or 0),
                "width": float(ship.get('WIDTH') or 0),
                "length": float(ship.get('LENGTH') or 0),
                "dwt": int(ship.get('DWT') or 0),
                "gt_shiptype": int(ship.get('GT_SHIPTYPE') or 0),
                "flag": str(ship.get('FLAG') or 'Unknown'),
                "destination": str(ship.get('DESTINATION') or 'Unknown'),
                "course": int(ship.get('COURSE') or 0),
                "heading": int(ship.get('HEADING') or 0)
            }
            
            # Only track Cargo (7) and Tankers (8)
            # if ship_type not in [7, 8]:
            #     continue
            vessels_to_insert.append(vessel_record)

        except Exception as e:
            print(f"Error processing ship {ship.get('SHIPNAME', 'Unknown')}: {e}")
            continue

    if vessels_to_insert:
        try:
            print(f"Pushing {len(vessels_to_insert)} records to Supabase...")
            response = supabase.table("vessel_history").insert(vessels_to_insert).execute()
            print("Successfully updated vessel history in cloud.")
        except Exception as e:
            print(f"Supabase Insert Error: {e}")

    print(f"Processed {len(rows)} ships. ")


def rpc_with_retry(fn, retries=3, delay=10):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if attempt < retries - 1:
                print(f"RPC error (attempt {attempt+1}/{retries}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise


def export_stats():
    update_vessel_locations()
    print("Waiting for DB to settle after writes...")
    time.sleep(30)

    def normalize_time(t):
        return t[:16].replace('T', ' ')

    since_date = (datetime.now() - timedelta(days=8)).isoformat()

    SHIP_TYPE_MAP = {8: 'VLCC', 7: 'Cargo'}
    try:
        crossings_res = rpc_with_retry(lambda: supabase.rpc('get_vessel_crossings', {
                'west_limit': WEST_LIMIT,
                'east_limit': EAST_LIMIT,
                'since_date': since_date
            }).execute())
        fresh_crossings = [
            {
                "out_transit_time": normalize_time(r['out_transit_time']),
                "out_shipid": r['out_shipid'],
                "out_name": r['out_name'],
                "out_direction": r['out_direction'],
                "out_ship_type": r['out_ship_type'],
                "out_dwt": r['out_dwt'],
                "out_length": r['out_length'],
                "out_width": r['out_width'],
                "out_gt_shiptype": r['out_gt_shiptype'],
                "out_vessel_class": r['out_vessel_class']
            } for r in crossings_res.data
        ]
        if fresh_crossings:
            supabase.table("vessel_crossings").upsert(fresh_crossings, on_conflict="out_transit_time,out_shipid").execute()
        all_res = supabase.table("vessel_crossings").select("*").order("out_transit_time").execute()
        crossings = [
            {"time": r["out_transit_time"], "mmsi": r["out_shipid"], "name": r["out_name"],
             "dir": r["out_direction"], "ship_type": r["out_ship_type"], "vessel_class": r["out_vessel_class"],
             "dwt": r["out_dwt"], "length": r["out_length"], "width": r["out_width"]}
            for r in all_res.data
        ]
        print(f"Crossings: {len(fresh_crossings)} fresh, {len(crossings)} total in DB.")
    except Exception as e:
        print(f"get_vessel_crossings failed: {e}")
        crossings = []

    try:
        bab_res = rpc_with_retry(lambda: supabase.rpc('get_bab_el_mandeb_transits_new', {'since_date': since_date}).execute())
        fresh_bab = [
            {
                "vessel_name": r['vessel_name'],
                "dwt": str(r['dwt']),
                "ship_id": str(r['ship_id']),
                "vessel_class": r['vessel_class'],
                "transit_time": normalize_time(r['transit_time']),
                "transit_direction": r['transit_direction']
            } for r in bab_res.data
        ]
        if fresh_bab:
            supabase.table("bab_crossings").upsert(fresh_bab, on_conflict="transit_time,ship_id").execute()
        all_bab_res = supabase.table("bab_crossings").select("*").order("transit_time").execute()
        bab_crossings = [
            {"time": r["transit_time"], "mmsi": r["ship_id"], "name": r["vessel_name"],
             "dir": r["transit_direction"], "ship_type": r["vessel_class"], "dwt": r["dwt"]}
            for r in all_bab_res.data
        ]
        print(f"Bab crossings: {len(fresh_bab)} fresh, {len(bab_crossings)} total in DB.")
    except Exception as e:
        print(f"get_bab_el_mandeb_transits_new failed: {e}")
        bab_crossings = []

    try:
        dormant_res = rpc_with_retry(lambda: supabase.rpc('get_dormant_vessels').execute())
        dormant = [
            {"time": r['out_time'], "count": r['out_count']}
            for r in dormant_res.data
        ]
        print(f"Fetched {len(dormant)} dormant vessel records from RPC.")
    except Exception as e:
        print(f"get_dormant_vessels failed, using cached data: {e}")
        dormant = load_cached_stats().get("dormant", [])
    
    # 3. Get Latest AIS timestamp
    latest_res = supabase.table("vessel_history") \
        .select("created_at") \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()
    
    if latest_res.data:
        # Standardize format from '2024-05-01T12:00:00' to '2024-05-01 12:00'
        latest_ais = latest_res.data[0]['created_at'][:16].replace('T', ' ')
    else:
        latest_ais = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 4. Encrypt and Save
    raw_data = {
        "dormant": dormant, 
        "crossings": crossings,
        "bab_crossings": bab_crossings,
        "calculated_at": datetime.now().isoformat(),
        "latest_ais": latest_ais
    }
    
    json_string = json.dumps(raw_data)
    encrypted_payload = encrypt_data(json_string)

    with open(JSON_PATH, 'w') as f:
        json.dump({"payload": encrypted_payload}, f)
    
    print(f"Successfully exported stats to {JSON_PATH}")

    # --- Fetch vessel sanctions view for Hormuz transit detail ---
    try:
        sanctions_res = supabase.rpc('get_vessel_sanctions_view', {}).execute()
        hormuz_transits = sanctions_res.data or []
        print(f"Fetched {len(hormuz_transits)} records from get_vessel_sanctions_view")

        hormuz_json = json.dumps(hormuz_transits)
        hormuz_encrypted = encrypt_data(hormuz_json)
        with open(HORMUZ_TRANSITS_PATH, 'w') as f:
            json.dump({"payload": hormuz_encrypted}, f)
        print(f"Successfully exported hormuz transits to {HORMUZ_TRANSITS_PATH}")
    except Exception as e:
        print(f"Error fetching vessel sanctions view: {e}")



if __name__ == "__main__":
    print(f"--- Monitoring Strait of Hormuz: {datetime.now()} ---")
    for url in CHOKEPOINTS:
        time.sleep(random.uniform(2, 4))
        print(f"Scraping URL: {url}")
        data = get_ships_with_stealth(url)

        if data:
            process_and_save(data)

    export_stats()

