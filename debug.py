import json
from collections import defaultdict

# 1. Load the data
with open('poly_series.json', 'r') as f:
    data = json.load(f)

# 2. Settings for the specific event you are seeing spikes on
TARGET_EVENT_ID = "236884" # Conflict Ends
TARGET_TIME = "2026-04-03T10:13"

# 3. Filter and Round
grouped_data = defaultdict(list)

for entry in data:
    if entry['event_id'] == TARGET_EVENT_ID:
        # Round the timestamp to the minute (YYYY-MM-DDTHH:MM)
        minute_key = entry['created_at'][:16] 
        grouped_data[minute_key].append(entry)

# 4. Check the specific "Spike" minute
print(f"--- Debugging {TARGET_TIME} ---")
spike_entries = grouped_data.get(TARGET_TIME, [])

if not spike_entries:
    print("No data found for this exact minute.")
else:
    print(f"Found {len(spike_entries)} markets for this timestamp:")
    print(f"{'Market ID':<12} | {'Probability':<12} | {'Original Timestamp'}")
    print("-" * 60)
    for s in spike_entries:
        print(f"{s['market_id']:<12} | {s['probability']:<12} | {s['created_at']}")

# 5. Check for missing markets compared to other minutes
counts = {time: len(entries) for time, entries in grouped_data.items()}
max_markets = max(counts.values())

print(f"\nExpected markets per minute: {max_markets}")
if len(spike_entries) < max_markets:
    print(f"ALERT: Minute {TARGET_TIME} is MISSING {max_markets - len(spike_entries)} market(s).")
    print("This gap is what causes the 'Spike' in Plotly.")