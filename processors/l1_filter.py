import os
import time
from config import config
from database import db
from ai_service import ai_service
from response_utils import best_title_match, parse_json_response, sanitize_text

class L1Filter:
    def __init__(self):
        self.profile_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'prompts', 'user_profile.md')
        self.rules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'prompts', 'l1_rules.md')
        self.model = config.AI_MODEL_L1

    def _load_prompt(self) -> str:
        with open(self.profile_path, 'r', encoding='utf-8') as f1:
            profile = f1.read()
        with open(self.rules_path, 'r', encoding='utf-8') as f2:
            rules = f2.read()
        return f"{profile}\n\n{rules}"

    def process_pending(self, batch_size: int = config.L1_BATCH_SIZE) -> int:
        items = db.get_pending_news(limit=batch_size)
        if not items:
            return 0

        # _classify() ALWAYS drains every item it is handed: it either scores
        # them, or — when the model returns an unparseable/refused response
        # (e.g. a content-filter refusal on sensitive news) — isolates the
        # offending item via binary split and marks it filtered. That guarantees
        # the pending queue strictly shrinks each call, so the caller's drain
        # loop terminates instead of re-sending the same stuck batch forever.
        self._classify(items)
        return len(items)

    def _ask(self, items: list):
        """Build the L1 prompt for `items`, call the model (with one strict-JSON
        reprompt on failure), and return (data, clean_json, id_map, response_text).
        `data` is None if the model gave nothing usable."""
        news_list_str = ""
        id_map = {}  # Map temporary ID to DB item

        for idx, item in enumerate(items):
            temp_id = idx + 1
            id_map[temp_id] = item

            # Calculate readable time
            pub_time = item.get('published_at', time.time())
            diff_seconds = int(time.time() - pub_time)
            hours = diff_seconds // 3600
            minutes = (diff_seconds % 3600) // 60
            time_str = f"{hours} hours {minutes} minutes ago" if hours > 0 else f"{minutes} minutes ago"

            # Trim summary to save tokens (e.g., max 500 chars)
            summary_snippet = (item.get('summary') or '')[:500]
            if len(item.get('summary') or '') > 500:
                summary_snippet += "..."

            news_list_str += f"- [ID: {temp_id}] \"{item['title']}\" ({item['source_name']}) - Published: {time_str}\n"
            if summary_snippet:
                summary_snippet = " ".join(summary_snippet.split())
                news_list_str += f"  Snippet: {summary_snippet}\n"

        system_prompt = self._load_prompt()
        user_prompt = f"Here is the list of news items to filter:\n\n{news_list_str}\n\nPlease output the JSON object as specified."

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
                print("L1: Retry with strict JSON reprompt...")
                fallback_messages = base_messages + [
                    {"role": "assistant", "content": response_text},
                    {"role": "user", "content": "Your previous reply was not valid JSON for the parser. Reply again with only a strict JSON object using this exact top-level shape: {\"items\": [...]}. No markdown fences, no commentary, no extra text, and preserve the input id for every selected item."}
                ]
                response_text = ai_service.chat_completion(
                    messages=fallback_messages,
                    model=self.model,
                    response_format={"type": "json_object"}
                )
                if response_text:
                    data, clean_json = parse_json_response(response_text)

        return data, clean_json, id_map, response_text

    def _classify(self, items: list):
        if not items:
            return

        print(f"L1: Processing {len(items)} items...")
        data, clean_json, id_map, response_text = self._ask(items)

        processed_ids = set()

        def update_item(item_data, category=None):
            if not isinstance(item_data, dict):
                return

            title = sanitize_text(item_data.get('title'))
            context = sanitize_text(item_data.get('context'))
            category = sanitize_text(item_data.get('category')) or sanitize_text(category)
            raw_score = item_data.get('score', 0)
            raw_temp_id = item_data.get('id')

            try:
                score = int(raw_score)
            except (TypeError, ValueError):
                score = 0

            matched_item = None
            match_score = 0.0
            temp_id = None
            try:
                temp_id = int(raw_temp_id)
            except (TypeError, ValueError):
                temp_id = None

            if temp_id is not None:
                matched_item = id_map.get(temp_id)
                if matched_item and title:
                    fuzzy_item, match_score = best_title_match(title, [matched_item], threshold=0.0)
                    if not fuzzy_item:
                        match_score = 0.0
                elif matched_item:
                    match_score = 1.0

            if not matched_item and title:
                matched_item, match_score = best_title_match(title, items)
                if matched_item:
                    print(f"  - Fallback title match for temp id {raw_temp_id!r}: {title!r}")

            if not matched_item:
                print(f"  - Skip unmatched L1 item: id={raw_temp_id!r}, title={title!r}")
                return

            matched_id = matched_item['id']
            processed_ids.add(matched_id)
            status = 'l1_done' if score >= 70 else 'filtered'
            reason = f"Category: {category or 'N/A'}. Context: {context or 'N/A'}"
            db.update_l1_result(matched_id, score, reason, status)
            print(f"  - Update {matched_id}: temp_id={temp_id} score={score} ({status}) [match={match_score:.2f}] category={category!r}")

        parsed_any = False
        try:
            if isinstance(data, dict):
                item_list = data.get('items', [])
                if isinstance(item_list, list):
                    parsed_any = True
                    for item_data in item_list:
                        update_item(item_data)

                if not parsed_any:
                    for category in ["AI_Algorithms", "Aerospace_HardTech", "Major_Industry_Moves"]:
                        category_items = data.get(category, [])
                        if isinstance(category_items, list):
                            parsed_any = True
                            for item_data in category_items:
                                update_item(item_data, category)
        except Exception as e:
            print(f"L1: Processing Error: {e}")
            # Fall through: unprocessed items are drained below so we never spin.
            parsed_any = parsed_any or bool(processed_ids)

        if not parsed_any:
            # The model returned nothing usable for this batch (empty / refusal /
            # garbage). Isolate the offending item(s) via binary split so a single
            # content-refused item can't poison the whole batch or spin the loop.
            self._handle_unparseable(items, clean_json or response_text)
            return

        # Anything the model didn't explicitly keep is implicitly filtered, which
        # also drains it from the pending queue.
        for item in items:
            if item['id'] not in processed_ids:
                db.update_l1_result(item['id'], 0, "Implicitly filtered by AI (Low Score)", "filtered")

    def _handle_unparseable(self, items: list, response_text):
        preview = (str(response_text) if response_text else "").strip().replace("\n", " ")[:120]
        if len(items) > 1:
            mid = len(items) // 2
            print(f"L1: Unparseable/refused response for {len(items)} items (resp={preview!r}); binary-splitting to isolate.")
            self._classify(items[:mid])
            self._classify(items[mid:])
        else:
            it = items[0]
            print(f"L1: Isolated unparseable/refused item id={it['id']} ({it.get('source_name')}): {it.get('title')!r}; marking filtered.")
            db.update_l1_result(it['id'], 0, f"L1 unparseable/refused response: {preview}", "filtered")

l1_filter = L1Filter()
