import sqlite3
import time
import random
import json
from datetime import datetime
from DrissionPage import ChromiumPage, ChromiumOptions

# --- CONFIGURATION ---
MAP_URL = "https://www.marinetraffic.com/en/ais/home/centerx:56.3/centery:26.4/zoom:9"
DB_NAME = "shipping_data.db"
HORMUZ_GATE_LON = 56.3  # The tripwire for the Strait chokepoint

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Updated Vessel History Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS vessel_history (
                        mmsi TEXT PRIMARY KEY, 
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
            cursor.execute("SELECT last_lon FROM vessel_history WHERE mmsi=?", (mmsi,))
            row = cursor.fetchone()

            if row:
                prev_lon = row[0]
                # Logic: Crossing the 56.3 longitude line
                # Westbound: From East to West
                if prev_lon > HORMUZ_GATE_LON and curr_lon <= HORMUZ_GATE_LON:
                    cursor.execute("INSERT INTO transit_logs VALUES (?, ?, ?, ?)",
                                   (mmsi, name, 'WESTBOUND', datetime.now()))
                    transits_this_run += 1
                # Eastbound: From West to East
                elif prev_lon < HORMUZ_GATE_LON and curr_lon >= HORMUZ_GATE_LON:
                    cursor.execute("INSERT INTO transit_logs VALUES (?, ?, ?, ?)",
                                   (mmsi, name, 'EASTBOUND', datetime.now()))
                    transits_this_run += 1

            # Update history with latest position
            cursor.execute('''INSERT OR REPLACE INTO vessel_history 
                              VALUES (?, ?, ?, ?, ?, ?)''', 
                           (mmsi, name, curr_lon, curr_lat, ship_type, datetime.now()))

        except Exception as e:
            print(f"Error processing ship {ship.get('SHIPNAME', 'Unknown')}: {e}")
            continue

    conn.commit()
    conn.close()
    print(f"Processed {len(rows)} ships. New transits detected: {transits_this_run}")

if __name__ == "__main__":
    print(f"--- Monitoring Strait of Hormuz: {datetime.now()} ---")
    data = get_ships_with_stealth()
    if data:
        process_and_save(data)