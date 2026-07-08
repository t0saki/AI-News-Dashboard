import os
import time
from config import config
from database import db
from ai_service import ai_service
from ranking import calculate_gravity_score
from response_utils import parse_json_response, sanitize_text

class L2Scorer:
    def __init__(self):
        self.profile_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'prompts', 'user_profile.md')
        self.rules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'prompts', 'l2_rules.md')
        self.model = config.AI_MODEL_L2

    def _load_prompt(self) -> str:
        with open(self.profile_path, 'r', encoding='utf-8') as f1:
            profile = f1.read()
        with open(self.rules_path, 'r', encoding='utf-8') as f2:
            rules = f2.read()
        return f"{profile}\n\n{rules}"

    def process_l1_passed(self):
        # Items that passed L1 but pending L2
        new_items = db.get_high_score_pending_l2(limit=config.L2_BATCH_SIZE)
        if not new_items:
            return 0

        # Prepare Top 20 context for deduplication (computed once, reused across
        # any binary-split recursion below).
        recent_processed = db.get_recent_processed_news(hours=config.RANKING_WINDOW_HOURS)
        ranked_context = []
        for rp in recent_processed:
            g_score = calculate_gravity_score(rp['l2_score'], rp['published_at'], config.GRAVITY)
            ranked_context.append((rp, g_score))

        ranked_context.sort(key=lambda x: x[1], reverse=True)
        top_20_old_items = [x[0] for x in ranked_context[:20]]

        # _score() ALWAYS drains every new item it is handed (scored, merged, or
        # dropped), so the caller's drain loop terminates instead of re-sending a
        # stuck batch forever.
        self._score(new_items, top_20_old_items)
        return len(new_items)

    def _ask(self, new_items: list, top_20_old_items: list):
        """Build the L2 prompt, call the model (with one strict-JSON reprompt on
        failure), and return (data, clean_json, response_text)."""
        all_batch_items = top_20_old_items + new_items

        news_list_str = ""
        for item in all_batch_items:
            is_new = "NEW" if item in new_items else f"OLD, Score: {item.get('l2_score', 0)}"

            pub_time = item.get('published_at', time.time())
            diff_seconds = int(time.time() - pub_time)
            hours = diff_seconds // 3600
            minutes = (diff_seconds % 3600) // 60
            time_str = f"{hours} hours {minutes} minutes ago" if hours > 0 else f"{minutes} minutes ago"

            summary_snippet = (item.get('summary') or '')[:500]
            if len(item.get('summary') or '') > 500:
                summary_snippet += "..."

            news_list_str += f"- [ID: {item['id']}] [{is_new}] \"{item['title']}\" ({item['source_name']}) - {item['url']} - Published: {time_str}\n"

            if summary_snippet:
                summary_snippet = " ".join(summary_snippet.split())
                news_list_str += f"  Snippet: {summary_snippet}\n"

            if item.get('l2_summary'):
                news_list_str += f"  Existing Summary: {item['l2_summary']}\n"

        system_prompt = self._load_prompt()
        user_prompt = f"News Items to Process:\n{news_list_str}\n\nPlease generate the output JSON feed."

        base_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        response_text = ai_service.chat_completion(
            messages=base_messages,
            model=self.model,
            response_format={"type": "json_object"}
        )

        data, clean_json = (None, None)
        if response_text:
            data, clean_json = parse_json_response(response_text)
            if not isinstance(data, dict):
                print("L2: Retry with strict JSON reprompt...")
                fallback_messages = base_messages + [
                    {"role": "assistant", "content": response_text},
                    {"role": "user", "content": "Your previous reply was not valid JSON for the parser. Reply again with only a strict JSON object matching this exact top-level shape: {\"feed\": [...]}. Keep each feed item flat. Use fields id, merged_ids, category, title, score, summary, url. No markdown fences, no commentary, no extra text."}
                ]
                response_text = ai_service.chat_completion(
                    messages=fallback_messages,
                    model=self.model,
                    response_format={"type": "json_object"}
                )
                if response_text:
                    data, clean_json = parse_json_response(response_text)

        return data, clean_json, response_text

    def _score(self, new_items: list, top_20_old_items: list):
        if not new_items:
            return

        print(f"L2: Processing {len(new_items)} new items...")
        data, clean_json, response_text = self._ask(new_items, top_20_old_items)

        feed_items = data.get('feed', []) if isinstance(data, dict) else None
        if not isinstance(feed_items, list):
            # Model returned nothing usable (empty / refusal / garbage). Isolate
            # the offending item(s) via binary split so one item can't poison the
            # batch or spin the loop.
            self._handle_unparseable(new_items, top_20_old_items, clean_json or response_text)
            return

        processed_primary_ids = set()
        processed_merged_ids = set()

        try:
            for feed_item in feed_items:
                if not isinstance(feed_item, dict):
                    continue

                primary_id = feed_item.get('id')
                if not primary_id:
                    continue

                try:
                    primary_id = int(primary_id)
                except (TypeError, ValueError):
                    continue

                optimized_title = sanitize_text(feed_item.get('title')) or sanitize_text(feed_item.get('title_optimized'))
                summary = sanitize_text(feed_item.get('summary')) or sanitize_text(feed_item.get('technical_summary'))
                category = sanitize_text(feed_item.get('category'))

                raw_score = feed_item.get('score', 0)
                try:
                    score = int(raw_score)
                except (TypeError, ValueError):
                    score = 0

                merged_ids = feed_item.get('merged_ids', [])
                if isinstance(merged_ids, int):
                    merged_ids = [merged_ids]
                elif not isinstance(merged_ids, list):
                    merged_ids = []

                db.update_l2_result(primary_id, score, summary or '', optimized_title or '', category or '')
                processed_primary_ids.add(primary_id)
                print(f"  - L2 Primary {primary_id}: {optimized_title}")

                for mid in merged_ids:
                    try:
                        mid = int(mid)
                    except (TypeError, ValueError):
                        continue
                    if mid != primary_id:
                        db.update_l2_result(mid, 0, "Deduplicated/Merged", "", "")
                        processed_merged_ids.add(mid)
                        print(f"  - L2 Merged {mid} -> {primary_id}")
        except Exception as e:
            print(f"L2 Error: {e}")

        # Any NEW item the model didn't explicitly cover is dropped, which also
        # drains it from the pending-L2 queue.
        for item in new_items:
            iid = item['id']
            if iid not in processed_primary_ids and iid not in processed_merged_ids:
                print(f"  - L2 Dropped NEW {iid}: {item['title']}")
                db.update_l2_result(iid, 0, "Dropped by AI", "", "")

    def _handle_unparseable(self, new_items: list, top_20_old_items: list, response_text):
        preview = (str(response_text) if response_text else "").strip().replace("\n", " ")[:120]
        if len(new_items) > 1:
            mid = len(new_items) // 2
            print(f"L2: Unparseable/refused response for {len(new_items)} items (resp={preview!r}); binary-splitting to isolate.")
            self._score(new_items[:mid], top_20_old_items)
            self._score(new_items[mid:], top_20_old_items)
        else:
            it = new_items[0]
            print(f"L2: Isolated unparseable/refused item id={it['id']} ({it.get('source_name')}): {it.get('title')!r}; marking dropped.")
            db.update_l2_result(it['id'], 0, "Dropped by AI (L2 unparseable/refused)", "", "")

l2_scorer = L2Scorer()
