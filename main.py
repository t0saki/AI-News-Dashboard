import os
import time
import signal
import sys
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional
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

# Watchdog state. _cycle_started_at is a monotonic timestamp while a cycle is
# running and None while we sleep between cycles (sleeping is not a stall).
_watchdog_lock = threading.Lock()
_cycle_started_at: Optional[float] = None

def arm_watchdog():
    global _cycle_started_at
    with _watchdog_lock:
        _cycle_started_at = time.monotonic()

def disarm_watchdog():
    global _cycle_started_at
    with _watchdog_lock:
        _cycle_started_at = None

def watchdog_loop():
    """
    Kills the process if a cycle hangs. Any single blocking call (a stuck socket
    read, an LLM request that never returns) would otherwise leave the container
    Up-but-brain-dead, with data silently frozen. os._exit skips cleanup on
    purpose: the point is to die now and let the restart policy recover.
    """
    while True:
        time.sleep(config.WATCHDOG_CHECK_INTERVAL_SECONDS)
        with _watchdog_lock:
            started = _cycle_started_at
        if started is None:
            continue
        elapsed = time.monotonic() - started
        if elapsed > config.CYCLE_TIMEOUT_SECONDS:
            print(f"WATCHDOG: cycle stuck for {elapsed:.0f}s "
                  f"(limit {config.CYCLE_TIMEOUT_SECONDS:.0f}s); exiting for restart.",
                  flush=True)
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(1)

def start_watchdog():
    if not config.WATCHDOG_ENABLED:
        print("Watchdog: disabled")
        return
    threading.Thread(target=watchdog_loop, name="cycle-watchdog", daemon=True).start()
    print(f"Watchdog: enabled (cycle timeout {config.CYCLE_TIMEOUT_SECONDS:.0f}s)")

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

def generate_simplified_top5(items: list):
    """Generate simplified top 5 JSON."""
    top5 = []
    # Take up to configured number of items
    for item, _ in items[:config.TOP_N_ITEMS]:
        top5.append({
            "title": item.get('l2_title_zh') or item.get('title'),
            "meta": format_time_ago(item.get('published_at'))
        })
    
    # Save to dashboard_top5.json (same dir as dashboard.json)
    output_path = config.DASHBOARD_OUTPUT_PATH.replace('dashboard.json', 'top5.json')
    if output_path == config.DASHBOARD_OUTPUT_PATH: # Fallback if filename diff
        output_path = "data/top5.json"
        
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(top5, f, ensure_ascii=False, indent=2)
        print(f"Top 5 saved to {output_path}")
    except Exception as e:
        print(f"Error saving top5.json: {e}")

def is_quiet_hours() -> bool:
    if not config.QUIET_HOURS_ENABLED:
        return False
    tz = timezone(timedelta(hours=config.QUIET_HOURS_TZ_OFFSET))
    hour = datetime.now(tz).hour
    start = config.QUIET_HOURS_START
    end = config.QUIET_HOURS_END
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end

def get_effective_interval() -> int:
    interval = config.FETCH_INTERVAL_SECONDS
    if is_quiet_hours():
        interval *= config.QUIET_HOURS_MULTIPLIER
    return interval

def calculate_sleep_seconds(interval: int) -> float:
    """Calculate seconds until next aligned interval."""
    now = time.time()
    next_run = (int(now) // interval + 1) * interval
    return next_run - now

def main():
    signal.signal(signal.SIGINT, signal_handler)
    
    print("AI AOD News Dashboard Started.")
    print(f"Update Interval: {config.FETCH_INTERVAL_SECONDS} seconds")
    if config.QUIET_HOURS_ENABLED:
        print(f"Quiet Hours: {config.QUIET_HOURS_START}:00-{config.QUIET_HOURS_END}:00 (UTC+{config.QUIET_HOURS_TZ_OFFSET}), {config.QUIET_HOURS_MULTIPLIER}x slower")

    start_watchdog()

    while True:
        try:
            arm_watchdog()
            print(f"--- Cycle Start: {datetime.fromtimestamp(time.time()).strftime('%H:%M:%S')} ---")
            
            # 1. Fetch
            items_added = source_manager.fetch_all()
            print(f"Fetched {items_added} new items.")
            
            # 2. L1 Filter
            # Drain pending items batch by batch. process_pending() always makes
            # progress (it drains every batch it processes), so this normally ends
            # when count == 0. MAX_L1_LOOPS is a hard safety cap so a pathological
            # batch can never spin the loop and hammer the LLM indefinitely.
            print("L1: Starting batch processing...")
            for _ in range(config.MAX_L1_LOOPS):
                count = l1_filter.process_pending(batch_size=config.L1_BATCH_SIZE)
                if count == 0:
                    break
            else:
                print(f"L1: Hit MAX_L1_LOOPS ({config.MAX_L1_LOOPS}); items may remain pending until next cycle.")

            # 3. L2 Scorer
            # Process ALL items that passed L1 (same safety cap as L1).
            print("L2: Starting batch processing...")
            for _ in range(config.MAX_L2_LOOPS):
                count = l2_scorer.process_l1_passed()
                if count == 0:
                    break
            else:
                print(f"L2: Hit MAX_L2_LOOPS ({config.MAX_L2_LOOPS}); items may remain pending until next cycle.")
            
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
                generate_simplified_top5(ranked)

            # Schedule Sleep
            effective = get_effective_interval()
            quiet = is_quiet_hours()
            sleep_sec = calculate_sleep_seconds(effective)
            quiet_tag = " [Quiet Hours]" if quiet else ""
            print(f"Sleeping for {sleep_sec:.1f} seconds (interval={effective}s{quiet_tag}, next at {datetime.fromtimestamp(time.time() + sleep_sec).strftime('%H:%M:%S')})...")
            disarm_watchdog()
            time.sleep(sleep_sec)

        except Exception as e:
            disarm_watchdog()
            print(f"Main Loop Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
