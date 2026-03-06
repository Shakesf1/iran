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
    conn.commit()
    return conn

def get_ships_with_stealth():
    co = ChromiumOptions()
    co.set_argument('--no-sandbox')
    co.set_argument('--headless=new')
    
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ]
    co.set_user_agent(random.choice(ua_list))
    page = ChromiumPage(co)

    try:
        time.sleep(random.uniform(2, 4))
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
            strftime('%Y-%m-%d %H:00', h1.update_time) as hr,
            SUM(CASE WHEN h2.last_lon <= {WEST_LIMIT} AND h1.last_lon >= {EAST_LIMIT} THEN 1 ELSE 0 END) as east,
            SUM(CASE WHEN h2.last_lon >= {EAST_LIMIT} AND h1.last_lon <= {WEST_LIMIT} THEN 1 ELSE 0 END) as west
        FROM vessel_history h1
        JOIN vessel_history h2 ON h1.mmsi = h2.mmsi
        WHERE h1.update_time > h2.update_time
          AND h1.update_time >= datetime('now', '-24 hours')
          -- Ensure h2 is the record immediately preceding h1 to avoid double counting
          AND h2.update_time = (
              SELECT MAX(update_time) 
              FROM vessel_history 
              WHERE mmsi = h1.mmsi AND update_time < h1.update_time
          )
        GROUP BY hr 
        ORDER BY hr ASC
    ''')
    
    crossings = [{"time": r[0], "East": r[1], "West": r[2]} for r in cursor.fetchall()]
    
    # 2. DORMANT SHIPS: Same as before, checking for no movement over 2 hours
    cursor.execute('''
        SELECT COUNT(DISTINCT h1.mmsi) 
        FROM vessel_history h1
        JOIN vessel_history h2 ON h1.mmsi = h2.mmsi
        WHERE h1.last_lon = h2.last_lon 
          AND h1.last_lat = h2.last_lat
          AND h1.update_time >= datetime('now', '-45 minutes')
          AND h2.update_time <= datetime('now', '-2 hours')
          AND h2.update_time >= datetime('now', '-3 hours')
    ''')
    
    dormant = cursor.fetchone()[0]
    
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