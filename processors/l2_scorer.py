import json
import os
from config import config
from database import db
from ai_service import ai_service

class L2Scorer:
    def __init__(self):
        self.prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'prompts', 'l2.md')
        self.model = config.AI_MODEL_L2

    def _load_prompt(self) -> str:
        with open(self.prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    def process_l1_passed(self):
        # Items that passed L1 but pending L2
        items = db.get_high_score_pending_l2(limit=config.L2_BATCH_SIZE)
        if not items:
            return 0

        print(f"L2: Processing {len(items)} items...")
        
        # Prepare input
        # L2 prompt asks for "Input list".
        news_list_str = ""
        for idx, item in enumerate(items):
            # Include URL so AI can return it in the JSON
            news_list_str += f"{idx+1}. \"{item['title']}\" ({item['source_name']}) - {item['url']}\n"

        system_prompt = self._load_prompt()
        user_prompt = f"Input:\n\n{news_list_str}\n\nPlease generate the output JSON feed."

        response_text = ai_service.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=self.model,
            response_format={"type": "json_object"}
        )

        if not response_text:
            print("L2: No response.")
            return

        try:
            clean_json = response_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            
            # Output format: { "feed": [ { "category":..., "title_optimized":..., "score":..., "original_sources":..., "technical_summary":..., "url":... } ] }
            # Again, matching back is tricky because the prompt is designed to "Process raw news list" which implies it handles the list.
            # But the prompt output example includes "url" which might be missing if I didn't provide it in user prompt?
            # Wait, I didn't provide URL in user_prompt above: f"{idx+1}. \"{item['title']}\" ({item['source_name']})\n"
            # So the AI cannot invent the URL.
            # I should include URL in the input so it can return it, OR I use the title to match back.
            # L2 prompt says: "url": "String (Link to the best source)".
            # So I must provide the URL in the input.
            
            # Let's Refine the User Prompt construction
            news_list_str = ""
            for idx, item in enumerate(items):
                news_list_str += f"{idx+1}. \"{item['title']}\" ({item['source_name']}) - {item['url']}\n"
                
            # Rerun logic with better input (conceptually, I'll just update the code below to use this)
            
            feed_items = data.get('feed', [])
            
            # Map back strategy: match by Title or URL. URL is safest.
            
            for feed_item in feed_items:
                optimized_title = feed_item.get('title_optimized')
                score = feed_item.get('score', 0)
                summary = feed_item.get('technical_summary')
                category = feed_item.get('category')
                
                # We need to find which original item this corresponds to.
                # The AI might have merged items (Deduplication).
                # "Group multiple articles about the same event."
                # If it merged, we might lose track of which specific ID it was.
                # But typically we want to update the DB record.
                # If it merges, we should pick one "representative" ID to update and mark others as "merged_out" or similar?
                # For simplicity, let's assume it picks one.
                
                # We'll try to match by similarity or just loop and see if url matches.
                # The AI output includes "url".
                out_url = feed_item.get('url')
                
                matched_id = None
                if out_url:
                    for item in items:
                        if item['url'] == out_url:
                            matched_id = item['id']
                            break
                
                # If ID found
                if matched_id:
                    db.update_l2_result(matched_id, score, summary, optimized_title, category)
                    print(f"  - L2 Done {matched_id}: {optimized_title}")
                else:
                    print(f"  - Warning: Could not match L2 output to DB: {optimized_title}")

        except Exception as e:
            print(f"L2 Error: {e}")
            
        return len(items)

l2_scorer = L2Scorer()
