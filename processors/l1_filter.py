import json
import os
from typing import List, Dict
from config import config
from database import db
from ai_service import ai_service

class L1Filter:
    def __init__(self):
        self.prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'prompts', 'l1.md')
        self.model = config.AI_MODEL_L1

    def _load_prompt(self) -> str:
        with open(self.prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    def process_pending(self, batch_size: int = config.L1_BATCH_SIZE) -> int:
        items = db.get_pending_news(limit=batch_size)
        if not items:
            return 0

        print(f"L1: Processing {len(items)} items...")
        
        # Prepare input for AI
        news_list_str = ""
        id_map = {} # Map temporary ID to DB ID
        
        for idx, item in enumerate(items):
            temp_id = idx + 1
            id_map[temp_id] = item['id']
            news_list_str += f"{temp_id}. {item['title']} ({item['source_name']})\n"

        # Construct Prompt
        system_prompt = self._load_prompt()
        user_prompt = f"Here is the list of news items to filter:\n\n{news_list_str}\n\nPlease output the JSON object as specified."

        # Call AI
        response_text = ai_service.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=self.model,
            response_format={"type": "json_object"}
        )

        if not response_text:
            print("L1: No response from AI.")
            return

        try:
            # Handle potential markdown fencing
            clean_json = response_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)
            
            # Categories in JSON based on prompt: "AI_Algorithms", "Aerospace_HardTech", "Major_Industry_Moves"
            # We need to map these back to our items.
            # The prompt example shows output does NOT use IDs, but titles.
            # This is risky. Let's see if we can enforce IDs or matches by title.
            # The prompt instructions say: "Format: Output the result as a strict, valid JSON object."
            # It creates lists under categories.
            # PROMPT ISSUE: The prompt examples output "title", "sources", "score".
            # It doesn't reference the Input ID.
            # We can fuzzy match titles or just trust the response.
            # Better strategy: Modify prompt dynamically to ask for ID? 
            # Or just match by title since we have the list.
            
            processed_titles = set()
            
            # Helper to update
            def update_item(item_data, category):
                title = item_data.get('title')
                score = item_data.get('score', 0)
                context = item_data.get('context')
                
                # Find the original item by title
                # Simple exact match first
                matched_id = None
                for candidate in items:
                    # Normalize for comparison
                    if candidate['title'].strip() == title.strip():
                        matched_id = candidate['id']
                        break
                
                # If valid match
                if matched_id:
                    processed_titles.add(matched_id)
                    # Decide status
                    status = 'l1_done' if score >= 70 else 'filtered'
                    reason = f"Category: {category}. Context: {context}"
                    db.update_l1_result(matched_id, score, reason, status)
                    print(f"  - Update {matched_id}: Score {score} ({status})")

            for category in ["AI_Algorithms", "Aerospace_HardTech", "Major_Industry_Moves"]:
                if category in data:
                    for item_data in data[category]:
                        update_item(item_data, category)
            
            # Mark others as filtered (low score, implicit) if not in list?
            # The prompt says: "Discard any item with a Score < 70."
            # So if it's not in the output, it's filtered.
            for item in items:
                if item['id'] not in processed_titles:
                    db.update_l1_result(item['id'], 0, "Implicitly filtered by AI (Low Score)", "filtered")
                    
        except json.JSONDecodeError:
            print(f"L1: Failed to parse JSON: {response_text}")
        except Exception as e:
            print(f"L1: Processing Error: {e}")
            
        return len(items)

l1_filter = L1Filter()
