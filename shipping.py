import sqlite3
import time
import random
import json
import base64
from datetime import datetime
from DrissionPage import ChromiumPage, ChromiumOptions

# --- CONFIGURATION ---
MAP_URL = "https://www.marinetraffic.com/en/ais/home/centerx:56.3/centery:26.4/zoom:9"
DB_NAME = "shipping_data.db"
#HORMUZ_GATE_LON = 56.3  # The tripwire for the Strait chokepoint

WEST_LIMIT = 56.1  # Deep in the Gulf
EAST_LIMIT = 56.5  # Well out into the Gulf of Oman


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
                        update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- YOUR system time
                    )''')
    
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
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. DYNAMIC CROSSINGS: Calculate from vessel_history per hour
    # This finds ships that moved from one side of the buffer to the other
    # between any two updates for that ship.
    cursor.execute(f'''
SELECT 
    strftime('%Y-%m-%d %H:%M', h1.update_time) as transit_time,
    h1.mmsi, 
    h1.name,
    CASE 
        WHEN h1.last_lon < 56.2 THEN 'WESTBOUND'
        WHEN h1.last_lon > 56.4 THEN 'EASTBOUND'
    END as direction,
    CASE WHEN h1.ship_type = 8 THEN 'VLCC' ELSE 'Cargo' END as ship_type
FROM vessel_history h1
WHERE (h1.last_lon < 56.2 OR h1.last_lon > 56.4)

-- 1. Directional Validation: Must have been on the OPPOSITE side previously
AND EXISTS (
    SELECT 1 FROM vessel_history h2
    WHERE h2.mmsi = h1.mmsi
    AND h2.update_time < h1.update_time
    AND (
        (h1.last_lon < 56.2 AND h2.last_lon > 56.4) OR 
        (h1.last_lon > 56.4 AND h2.last_lon < 56.2)
    )
)

-- 2. GLOBAL LOCKOUT: Ignore ANY transit for this MMSI if one occurred in the last 12h
-- This prevents ARTMAN from toggling between West/East rapidly
AND NOT EXISTS (
    SELECT 1 FROM vessel_history h_recent
    WHERE h_recent.mmsi = h1.mmsi
    AND h_recent.update_time < h1.update_time
    AND h_recent.update_time > datetime(h1.update_time, '-12 hours')
    -- Check if it was already recorded on EITHER side within the lockout window
    AND (h_recent.last_lon < 56.2 OR h_recent.last_lon > 56.4)
    -- Crucial: Check that the recent ping had the OPPOSITE side history too
    -- (This ensures we only lockout AFTER a successful transit was detected)
    AND EXISTS (
        SELECT 1 FROM vessel_history h_hist
        WHERE h_hist.mmsi = h_recent.mmsi
        AND h_hist.update_time < h_recent.update_time
        AND (
            (h_recent.last_lon < 56.2 AND h_hist.last_lon > 56.4) OR 
            (h_recent.last_lon > 56.4 AND h_hist.last_lon < 56.2)
        )
    )
)

ORDER BY h1.update_time ASC;
    ''')
    
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
    
    raw_data = {
            "dormant": dormant, 
            "crossings": crossings,
            "calculated_at": datetime.now().isoformat()
        }
    json_string = json.dumps(raw_data)

    encrypted_payload = encrypt_data(json_string)

    with open('dashboard_stats.json', 'w') as f:
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