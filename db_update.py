import sqlite3

conn = sqlite3.connect('shipping_data.db')
cursor = conn.cursor()

try:
    # 1. Add the update_time column to vessel_history if it doesn't exist
    cursor.execute("ALTER TABLE vessel_history ADD COLUMN update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    print("Success: Added update_time column.")
except sqlite3.OperationalError:
    print("Column already exists or table needs manual fix.")

# 2. Make sure transit_logs also has a timestamp
try:
    cursor.execute("ALTER TABLE transit_logs ADD COLUMN timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    print("Success: Added timestamp to transit_logs.")
except sqlite3.OperationalError:
    print("Column already exists.")

conn.commit()
conn.close()