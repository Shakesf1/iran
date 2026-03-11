import sqlite3
import time
import random
import json
import base64
from datetime import datetime
from DrissionPage import ChromiumPage, ChromiumOptions
import geopandas as gpd
from shapely.geometry import Point

import os

# Get the absolute path of the folder containing shipping.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Update your paths to be absolute
DB_PATH = os.path.join(BASE_DIR, "shipping_data.db")
JSON_PATH = os.path.join(BASE_DIR, "dashboard_stats.json")

# --- CONFIGURATION ---
MAP_URL = "https://www.marinetraffic.com/en/ais/home/centerx:56.3/centery:26.4/zoom:9"
DB_NAME = DB_PATH
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

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Updated Vessel History Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS vessel_history (
                            mmsi TEXT, 
                            name TEXT, 
                            last_lon REAL, 
                            last_lat REAL, 
                            ship_type INT,
                            location TEXT DEFAULT NULL,
                            update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )''')
        
    # Ensure the location column exists for older databases
    try:
        cursor.execute('ALTER TABLE vessel_history ADD COLUMN location TEXT DEFAULT NULL')
    except sqlite3.OperationalError:
        pass # Column already exists
    
    # Updated Transit Log Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS transit_logs (
                        mmsi TEXT, 
                        name TEXT, 
                        direction TEXT, 
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
    # Add this inside your init_db() function
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mmsi_time ON vessel_history (mmsi, update_time)")

    conn.commit()
    return conn

def update_vessel_locations():
    """Classifies vessel positions as water, bad, or coastal_noise using spatial data."""
    print("--- Classifying vessel locations via GeoPandas ---")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Fetch rows that haven't been classified yet
    cursor.execute("SELECT rowid, last_lon, last_lat FROM vessel_history WHERE location IS NULL")
    rows = cursor.fetchall()

    if not rows:
        print("No new coordinates to classify.")
        conn.close()
        return

    row_ids = [r[0] for r in rows]
    lons = [r[1] for r in rows]
    lats = [r[2] for r in rows]

    try:
        # Load land polygons (Ensure this path is correct)
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

        # Classify
        updates = []
        for i, p in enumerate(points_m):
            if land_geom.contains(p):
                label = "bad"
            elif land_buffer.contains(p):
                label = "coastal_noise"
            else:
                label = "water"
            updates.append((label, row_ids[i]))

        # Bulk update the database
        cursor.executemany("UPDATE vessel_history SET location = ? WHERE rowid = ?", updates)
        conn.commit()
        print(f"Successfully classified {len(updates)} records.")

    except Exception as e:
        print(f"Spatial Processing Error: {e}")
    finally:
        conn.close()

def get_ships_with_stealth():
    co = ChromiumOptions()
    co.set_argument('--no-sandbox')
    co.set_argument('--headless=new')
    co.set_argument('--disable-dev-shm-usage') # Uses /tmp instead of memory (Slower but stable)
    co.set_argument('--disable-gpu')

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
        page.get(MAP_URL)
        page.wait.ele_displayed('css:.leaflet-container', timeout=20)
        packet = page.listen.wait(timeout=30)

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
    if not strait_data or 'data' not in strait_data:
        return

    conn = init_db()
    cursor = conn.cursor()
    rows = strait_data.get("data", {}).get("rows", [])
    transits_this_run = 0

    for ship in rows:
        try:
            # MarineTraffic API fields are often strings in dict format
            mmsi = str(ship.get('SHIP_ID'))
            name = ship.get('SHIPNAME', 'Unknown')
            curr_lon = float(ship.get('LON', 0))
            curr_lat = float(ship.get('LAT', 0))
            ship_type = int(ship.get('SHIPTYPE', 0))

            # Only track Cargo (7) and Tankers (8)
            if ship_type not in [7, 8]:
                continue

            # Check previous known longitude for this ship
            cursor.execute("SELECT last_lon FROM vessel_history WHERE mmsi=? ORDER BY update_time DESC LIMIT 1", (mmsi,))
            row = cursor.fetchone()

            if row:
                prev_lon = row[0]
                # Logic: Crossing the 56.3 longitude line
                # Westbound: From East to West
                if prev_lon > EAST_LIMIT and curr_lon < WEST_LIMIT:
                    cursor.execute("INSERT INTO transit_logs VALUES (?, ?, ?, ?)",
                                   (mmsi, name, 'WESTBOUND', datetime.now()))
                    transits_this_run += 1
                # Eastbound: From West to East
                elif prev_lon < WEST_LIMIT and curr_lon >= EAST_LIMIT:
                    cursor.execute("INSERT INTO transit_logs VALUES (?, ?, ?, ?)",
                                   (mmsi, name, 'EASTBOUND', datetime.now()))
                    transits_this_run += 1

            # Update history with latest position
            print('Updating vessel history:', mmsi, name, curr_lon, curr_lat, ship_type)
            cursor.execute('''INSERT INTO vessel_history 
                  (mmsi, name, last_lon, last_lat, ship_type, update_time)
                  VALUES (?, ?, ?, ?, ?, ?)''', 
               (mmsi, name, curr_lon, curr_lat, ship_type, datetime.now()))

        except Exception as e:
            print(f"Error processing ship {ship.get('SHIPNAME', 'Unknown')}: {e}")
            continue

    conn.commit()
    conn.close()
    print(f"Processed {len(rows)} ships. New transits detected: {transits_this_run}")


def export_stats():
    update_vessel_locations()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. DYNAMIC CROSSINGS: Calculate from vessel_history per hour
    # This finds ships that moved from one side of the buffer to the other
    # between any two updates for that ship.
    # Pass the variables as a tuple to the execute function
    cursor.execute(f'''
    WITH DefinitivePositions AS (
        SELECT 
            update_time,
            mmsi,
            name,
            ship_type,
            CASE 
                WHEN last_lon < ? THEN 'WESTBOUND' 
                WHEN last_lon > ? THEN 'EASTBOUND' 
            END as direction
        FROM vessel_history
        WHERE (last_lon < ? OR last_lon > ?) 
        AND location != 'bad'
        AND location IS NOT NULL
    ),
    Transitions AS (
        SELECT 
            *,
            LAG(direction) OVER (PARTITION BY mmsi ORDER BY update_time) as prev_direction
        FROM DefinitivePositions
    )
    SELECT 
        strftime('%Y-%m-%d %H:%M', update_time) as transit_time,
        mmsi,
        name,
        direction,
        CASE WHEN ship_type = 8 THEN 'VLCC' ELSE 'Cargo' END as ship_type
    FROM Transitions
    WHERE direction != prev_direction 
    AND prev_direction IS NOT NULL
    ORDER BY update_time ASC;
    ''', (WEST_LIMIT, EAST_LIMIT, WEST_LIMIT, EAST_LIMIT)) 
    
    crossings = [
        {
            "time": r[0], 
            "mmsi": r[1], 
            "name": r[2], 
            "dir": r[3],
            "ship_type": r[4]
        } for r in cursor.fetchall()
    ]
    
    # 2. DORMANT SHIPS: Same as before, checking for no movement over 2 hours
    cursor.execute('''
        WITH LastTwoPositions AS (
            SELECT 
                mmsi,
                last_lat,
                last_lon,
                update_time,
                strftime('%Y-%m-%d %H:%M', update_time) as scrape_minute,
                strftime('%Y-%m-%d %H:00', update_time) as scrape_hour,
                LAG(last_lat) OVER (PARTITION BY mmsi ORDER BY update_time) as prev_lat,
                LAG(last_lon) OVER (PARTITION BY mmsi ORDER BY update_time) as prev_lon,
                LAG(update_time) OVER (PARTITION BY mmsi ORDER BY update_time) as prev_time
            FROM vessel_history
            WHERE update_time >= datetime('now', '-48 hours')
        ),
        DormancyCheck AS (
            SELECT 
                scrape_hour,
                scrape_minute,
                mmsi,
                -- Using a slightly stricter threshold: 0.003 degrees (~300m) 
                -- to ensure they are REALLY not moving.
                CASE WHEN ABS(last_lat - prev_lat) < 0.003 AND ABS(last_lon - prev_lon) < 0.003 
                    THEN 1 ELSE 0 END as is_dormant
            FROM LastTwoPositions
            WHERE prev_lat IS NOT NULL 
            AND prev_time >= datetime(update_time, '-4 hours')
        ),
        MinuteTotals AS (
            SELECT 
                scrape_hour,
                scrape_minute,
                SUM(is_dormant) as dormant_in_batch
            FROM DormancyCheck
            GROUP BY scrape_minute
        )
        SELECT 
            scrape_hour,
            -- Using ROUND(AVG()) instead of MAX() to kill the 'saw-tooth' spikes
            CAST(AVG(dormant_in_batch) AS INT) as unique_dormant_vessels
        FROM MinuteTotals
        GROUP BY scrape_hour
        ORDER BY scrape_hour ASC;
    ''')
    
    dormant = [{"time": r[0], "count": r[1]} for r in cursor.fetchall()]
    
    cursor.execute("SELECT MAX(update_time) FROM vessel_history")
    res = cursor.fetchone()
    # Fallback to current time if DB is empty, otherwise use the actual event time
    latest_ais = res[0] if res and res[0] else datetime.now().strftime("%Y-%m-%d %H:%M")

    raw_data = {
            "dormant": dormant, 
            "crossings": crossings,
            "calculated_at": datetime.now().isoformat(),
            "latest_ais": latest_ais
        }
    json_string = json.dumps(raw_data)

    encrypted_payload = encrypt_data(json_string)

    with open(JSON_PATH, 'w') as f:
            json.dump({
                "payload": encrypted_payload
            }, f)   

    conn.close()


if __name__ == "__main__":
    print(f"--- Monitoring Strait of Hormuz: {datetime.now()} ---")
    data = get_ships_with_stealth()
    if data:
        process_and_save(data)

    export_stats()