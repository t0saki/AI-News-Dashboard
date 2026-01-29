from openai import OpenAI
from config import config
import json

class AIService:
    def __init__(self):
        self.client = OpenAI(
            base_url=config.AI_BASE_URL,
            api_key=config.AI_API_KEY
        )

    def chat_completion(self, messages, model, response_format=None):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
            }
            if response_format:
                # Support for JSON mode if API supports it, or just prompt
                # Some OpenAI compatible APIs might not support strict json_object
                # We'll try to just ask for it in prompt, but passing it if confident
                kwargs["response_format"] = response_format

            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            print(f"AI Service Error: {e}")
            return None

ai_service = AIService()
