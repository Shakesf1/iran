import base64
import json
from datetime import datetime

# The data from your dashboard_stats.json
data_json = {"payload": "KxpbOwkbCENdR21EXWleRFJDbwIxRlVIQFFDb1hBXVFXP31YTT0fGwJMZRYsBAQcXS0cO0gtAQ4ER3NWAz4GGgIGOlBHTFBGQ1VVfQEBGQQVBjoEGzoXVltfbg1JVA0bBBJbZVpYWVlLRzIdAwAQFRJMZQVTRlFeUgIQKTcMDBJFX2ZMXyJfD0MKPkAAVF9QQlFLaUVfXkxXUwtEX2VDRFtebxpVRlUoUk1bPQQADkNdRwonM3A6BxMPOlhFNAkdE0NVfQQOGA8EDToQTWVCRVBWbxhHHwsGFRMaOhgbCAVFX2lEWmxfVgkHK0dHTFdCR01bMgEDMgIGFn1OXW9fVgIHKWsGFxZQSlVAIjU="}
SECRET_KEY = "pay_homage_to_stan_4ever"

# 1. Base64 decode and XOR decrypt
scrambled = base64.b64decode(data_json['payload']).decode('utf-8')
decrypted_str = "".join(chr(ord(c) ^ ord(SECRET_KEY[i % len(SECRET_KEY)])) for i, c in enumerate(scrambled))

# 2. Convert the decrypted string into a Python dictionary
shipping_data = json.loads(decrypted_str)



def aggregate_all_data(data):
    if not data:
        return {"error": "No data provided"}

    # Initialize totals
    totals = {
        "launched": 0,
        "intercepted": 0,
        "hits": 0,
        "mil_cas": 0,
        "civ_cas": 0,
        "count": 0
    }
    
    # Track the date range found in the data
    dates = []

    for entry in data:
        # Parse date and add to list for min/max calculation
        entry_date = datetime.fromisoformat(entry['date'].replace('Z', '+00:00'))
        dates.append(entry_date)
        
        # Aggregate totals using .get() for safety
        totals["launched"] += entry.get("launched", 0)
        totals["intercepted"] += entry.get("intercepted", 0)
        totals["hits"] += entry.get("hits", 0)
        totals["mil_cas"] += entry.get("mil_cas", 0)
        totals["civ_cas"] += entry.get("civ_cas", 0)
        totals["count"] += 1
            
    # Add the inferred range to the output
    totals["inferred_start_date"] = min(dates).isoformat()
    totals["inferred_end_date"] = max(dates).isoformat()
    
    # Calculate global interception rate
    if totals["launched"] > 0:
        totals["interception_rate"] = f"{(totals['intercepted'] / totals['launched'] * 100):.2f}%"
    
    return totals

# Usage: 
result = aggregate_all_data(shipping_data)
print(result)