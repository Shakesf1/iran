import requests
import json
import os
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# --- SUPABASE CONFIG ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

GAMMA_URL = "https://gamma-api.polymarket.com/events/slug"

SLUGS = [
    "iran-leader-end-of-2026",
    "iran-x-israelus-conflict-ends-by",
    "bab-el-mandeb-strait-effectively-closed-by",
    "kharg-island-no-longer-under-iranian-control-by-march-31",
    "trump-announces-end-of-military-operations-against-iran-by",
    "strait-of-hormuz-traffic-returns-to-normal-by-april-30",
    "us-x-iran-ceasefire-by"
]

def get_market_price(market):
    try:
        raw_prices = market.get('outcomePrices', '["0", "0"]')
        prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
        return float(prices[0]) * 100
    except:
        return None

def run_monitor():
    print(f"--- Iran Intelligence Snapshot | {datetime.now().strftime('%Y-%m-%d %H:%M')} ---\n")
    
    for slug in SLUGS:
        resp = requests.get(f"{GAMMA_URL}/{slug}")
        if resp.status_code != 200: continue
        data = resp.json()
        
        event_id = data.get('id')
        title = data.get('title', slug)
        markets = data.get('markets', [])

        # --- A. SAVE EVENT METADATA ---
        supabase.table("poly_events").upsert({
            "id": event_id,
            "slug": slug,
            "title": title,
            "updated_at": datetime.now().isoformat()
        }).execute()

        # --- B. PROCESS MARKETS & DISPLAY ---
        snapshots_to_save = []
        
        if "leader" in slug.lower():
            print(f"{title} (Top 10 Candidates)")
            sorted_markets = sorted(markets, key=lambda x: get_market_price(x) or 0, reverse=True)
            target_list = sorted_markets[:10]
        else:
            print(f"{title}")
            target_list = [m for m in markets if not m.get('closed')]
            target_list.sort(key=lambda x: float(x.get('groupItemThreshold', 0)))

        for m in target_list:
            prob = get_market_price(m)
            if prob is not None:
                label = m.get('groupItemTitle') or m.get('question')
                print(f"  - {label:<22} : {prob:>5.1f}%")
                
                # Add to Supabase Batch
                snapshots_to_save.append({
                    "event_id": event_id,
                    "market_id": m.get('id'),
                    "label": label,
                    "probability": prob
                })

        # --- C. SAVE SNAPSHOTS ---
        if snapshots_to_save:
            supabase.table("poly_market_snapshots").insert(snapshots_to_save).execute()
        
        print("") # Formatting spacer

def export_data():
    print("--- Exporting Optimized Data ---")
    
    # 1. Get Metadata (using standard table select)
    meta_res = supabase.table("poly_events").select("id, title, slug").execute()
    market_res = supabase.table("poly_market_snapshots").select("market_id, label, event_id").execute()
    unique_markets = {m['market_id']: m for m in market_res.data}.values()
    
    # 2. Get Series (calling the RPC function we just created)
    # This executes our complex UNION logic on the server
    series_res = supabase.rpc("get_optimized_polymarket_series").execute()

    # 3. Save JSONs
    with open("poly_metadata.json", "w") as f:
        json.dump({"events": meta_res.data, "markets": list(unique_markets)}, f, indent=2)
    
    with open("poly_series.json", "w") as f:
        json.dump(series_res.data, f, indent=2)

    # 4. Push to Git
    if not os.environ.get("GITHUB_ACTIONS"):
        git_push()

def git_push():
    import os
    try:
        # Move to the script's directory
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        
       
        # 2. Stage and commit your new JSON files
        os.system('git add poly_metadata.json poly_series.json')
        # We use a check to see if there's actually anything to commit
        os.system('git commit -m "data: update snapshots [skip ci]"')
        os.system('git stash')
        # 3. Integrated Pull: Rebase to put your new commit on top of the remote ones
        # --autostash handles any lingering unstaged changes automatically
        print("Pulling latest changes from remote...")
        os.system('git pull --rebase origin main')
        
        # 4. Push
        print("Pushing to GitHub...")
        result = os.system('git push origin main')
        
        if result == 0:
            print("Successfully pushed to GitHub.")
        else:
            print("Push failed. You might have a merge conflict in the JSONs.")
            
        # 5. Bring back any work-in-progress you had
        os.system('git stash pop')
        
    except Exception as e:
        print(f"Git error: {e}")

if __name__ == "__main__":
    run_monitor()
    export_data()