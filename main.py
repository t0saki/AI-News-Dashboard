import time
import signal
import sys
from datetime import datetime
from config import config
from sources.manager import source_manager
from processors.l1_filter import l1_filter
from processors.l2_scorer import l2_scorer
from database import db
from ranking import calculate_gravity_score
import json

def signal_handler(sig, frame):
    print("\nExiting...")
    sys.exit(0)

def format_time_ago(timestamp: float) -> str:
    """Format timestamp to simplified time ago (e.g. 1H, 2D, 30M)."""
    if not timestamp:
        return ""
    
    diff = time.time() - timestamp
    
    if diff < 3600:
        return f"{int(diff // 60)}M"
    elif diff < 86400:
        return f"{int(diff // 3600)}H"
    else:
        return f"{int(diff // 86400)}D"

def generate_simplified_top5(items: list, topn = 5):
    """Generate simplified top 5 JSON."""
    top5 = []
    # Take up to 5 items
    for item, _ in items[:topn]:
        top5.append({
            "title": item.get('l2_title_zh') or item.get('title'),
            "meta": format_time_ago(item.get('published_at'))
        })
    
    # Save to dashboard_top5.json (same dir as dashboard.json)
    output_path = config.DASHBOARD_OUTPUT_PATH.replace('dashboard.json', f'top{topn}.json')
    if output_path == config.DASHBOARD_OUTPUT_PATH: # Fallback if filename diff
        output_path = f"data/top{topn}.json"
        
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(top5, f, ensure_ascii=False, indent=2)
        print(f"Top {topn} saved to {output_path}")
    except Exception as e:
        print(f"Error saving {output_path}: {e}")

def calculate_sleep_seconds(interval: int) -> float:
    """Calculate seconds until next aligned interval."""
    now = time.time()
    next_run = (int(now) // interval + 1) * interval
    return next_run - now

def main():
    signal.signal(signal.SIGINT, signal_handler)
    
    print("AI AOD News Dashboard Started.")
    print(f"Update Interval: {config.FETCH_INTERVAL_SECONDS} seconds")

    while True:
        try:
            print(f"--- Cycle Start: {datetime.fromtimestamp(time.time()).strftime('%H:%M:%S')} ---")
            
            # 1. Fetch
            items_added = source_manager.fetch_all()
            print(f"Fetched {items_added} new items.")
            
            # 2. L1 Filter
            # Process ALL pending items
            print("L1: Starting batch processing...")
            while True:
                count = l1_filter.process_pending(batch_size=config.L1_BATCH_SIZE)
                if count == 0:
                    break
            
            # 3. L2 Scorer
            # Process ALL items that passed L1
            print("L2: Starting batch processing...")
            while True:
                count = l2_scorer.process_l1_passed()
                if count == 0:
                    break
            
            # 4. Display/Ranking (Preview)
            # Fetch all processed items from last window
            processed = db.get_recent_processed_news(hours=config.RANKING_WINDOW_HOURS)
            if processed:
                header = f"\n=== Top News (Last {config.RANKING_WINDOW_HOURS}h, Gravity={config.GRAVITY}) ==="
                print(header)
                # Calculate display scores
                ranked = []
                for item in processed:
                    g_score = calculate_gravity_score(item['l2_score'], item['published_at'], config.GRAVITY)
                    ranked.append((item, g_score))
                
                # Sort by Gravity Score
                ranked.sort(key=lambda x: x[1], reverse=True)
                
                # Prepare JSON Output
                json_output = {
                    "generated_at": time.time(),
                    "generated_at_str": datetime.now().isoformat(),
                    "config": {
                        "gravity": config.GRAVITY,
                        "window_hours": config.RANKING_WINDOW_HOURS
                    },
                    "items": []
                }

                # Display Loop
                count = 0
                for item, g_score in ranked:
                    # JSON item
                    json_item = dict(item)
                    json_item['gravity_score'] = g_score
                    json_output['items'].append(json_item)

                    # Console Output (Top 10)
                    if count < 10:
                        print(f"[{g_score:.1f}] {item['l2_title_zh']} (Original: {item['l2_score']})")
                        print(f"   {item['l2_summary']}")
                        print(f"   URL: {item['url']}")
                        print("")
                    count += 1
                
                # Save JSON
                with open(config.DASHBOARD_OUTPUT_PATH, 'w', encoding='utf-8') as f:
                    json.dump(json_output, f, ensure_ascii=False, indent=2)
                print(f"Dashboard saved to {config.DASHBOARD_OUTPUT_PATH}")

                # Generate Simplified Top 5
                generate_simplified_top5(ranked, 10)

            # Schedule Sleep
            sleep_sec = calculate_sleep_seconds(config.FETCH_INTERVAL_SECONDS)
            print(f"Sleeping for {sleep_sec:.1f} seconds (Next run at {datetime.fromtimestamp(time.time() + sleep_sec).strftime('%H:%M:%S')})...")
            time.sleep(sleep_sec)
            
        except Exception as e:
            print(f"Main Loop Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
