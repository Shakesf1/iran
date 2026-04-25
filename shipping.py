
import time
import random
import json
import base64
from datetime import datetime
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

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY") # Use Service Role for backend writes


supabase: Client = create_client(url, key)
#HORMUZ_GATE_LON = 56.3  # The tripwire for the Strait chokepoint

WEST_LIMIT = 56.15  # Deep in the Gulf
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

    # 1. Fetch rows that haven't been classified yet, in batches to avoid timeout
    response = supabase.table("vessel_history") \
        .select("id, longitude, latitude") \
        .is_("location", "null") \
        .limit(500) \
        .execute()
    
    rows = response.data

    if not rows:
        print("No new coordinates to classify.")
        return

    # Extract data for processing
    row_ids = [r['id'] for r in rows]
    lons = [r['longitude'] for r in rows]
    lats = [r['latitude'] for r in rows]

    try:
        # 2. Load land polygons (Ensure the .shp file path is correct in your environment)
        land = gpd.read_file("./ne_10m_land/ne_10m_land.shp")
        
        # Create GeoSeries of points
        points = gpd.GeoSeries(
            [Point(x, y) for x, y in zip(lons, lats)],
            crs="EPSG:4326"
        )

        # Project to metric CRS for accurate buffering
        land_m = land.to_crs(epsg=3857)
        points_m = points.to_crs(epsg=3857)

        # Merge land polygons for faster spatial testing
        land_geom = land_m.union_all()
        # 200m inland tolerance
        land_buffer = land_geom.buffer(200)

        # 3. Classify and build the Supabase update list
        updates = []
        for i, p in enumerate(points_m):
            if land_geom.contains(p):
                label = "bad"
            elif land_buffer.contains(p):
                label = "coastal_noise"
            else:
                label = "water"
            
            # Map the primary key 'id' and the new 'location' label
            updates.append({
                "id": row_ids[i],
                "location": label
            })

        # 4. Perform Bulk Upsert to Supabase
        if updates:
            try:
                # Upsert updates existing records matching the 'id' primary key
                supabase.table("vessel_history").upsert(updates).execute()
                print(f"Successfully classified {len(updates)} records in Supabase.")
            except Exception as e:
                print(f"Supabase Update Error: {e}")

    except Exception as e:
        print(f"Spatial Processing Error: {e}")


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

        time.sleep(random.uniform(4, 6))  # Wait for potential AJAX calls to populate data

        for attempt in range(3):  # Try up to 3 times to find a 'meaty' packet
            packet = page.listen.wait(timeout=10)
            if packet and packet.response.body:
                body_str = str(packet.response.body)
                # Check if the packet is large enough to contain real data
                if len(body_str) > 10000: 
                    print(f"✅ Captured valid data packet ({len(body_str)} bytes)")
                    return packet.response.body
                else:
                    print(f"⚠️ Captured small packet ({len(body_str)} bytes), skipping...")



        if not packet:
            return None
        return packet.response.body
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
    target_id = '466738'
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


def export_stats():
    update_vessel_locations()

    crossings_res = supabase.rpc('get_vessel_crossings', {
            'west_limit': WEST_LIMIT, 
            'east_limit': EAST_LIMIT
        }).execute()
    

    SHIP_TYPE_MAP = {8: 'VLCC', 7: 'Cargo'}
    crossings = [
        {
            "time": r['out_transit_time'], 
            "mmsi": r['out_shipid'], 
            "name": r['out_name'], 
            "dir": r['out_direction'],
            "ship_type": SHIP_TYPE_MAP.get(int(r['out_ship_type'] or 0), str(r['out_ship_type']))
        } for r in crossings_res.data
    ]

    # 2. NEW: Fetch Bab el-Mandeb Crossings
        # No parameters needed as the limits are hardcoded in the SQL function
    bab_res = supabase.rpc('get_bab_el_mandeb_transits').execute()

    bab_crossings = [
        {
            "time": r['transit_time'], 
            "mmsi": r['ship_id'], 
            "name": r['vessel_name'], 
            "dir": r['transit_direction'],
            "ship_type": r['vessel_class']
        } for r in bab_res.data
    ]


    
    # 2. Fetch Dormant Vessels via RPC
    dormant_res = supabase.rpc('get_dormant_vessels').execute()

    dormant = [
        {"time": r['out_time'], "count": r['out_count']} 
        for r in dormant_res.data
    ]
    
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