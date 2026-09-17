import json
import logging
from typing import Dict, Any, List
from ai.router import AIRouter

logger = logging.getLogger("Clipper.Copywriter")

COPYWRITER_SYSTEM_PROMPT = """You are an elite YouTube Shorts title specialist and algorithm SEO copywriter.
Your goal is to package video clips with titles and descriptions that maximize Click-Through Rate (CTR) while strictly matching what is actually spoken or happening in the clip.

Critical Rules for Titles:
- MUST DIRECTLY MATCH AND ACCURATELY DESCRIBE what is actually spoken or happening in the clip dialogue.
- Do NOT invent fake storylines, mention unrelated people or creators, or make false claims.
- If a creator is speaking, use their actual name or topic.
- Punchy, emotional, or polarizing (under 60 characters).
- Include 1-2 relevant emojis (💀, 🔥, 😱, 😂, 😳).
- Always include #Shorts in the title.

Rules for Descriptions:
- 2-3 sentences providing context and teasing the climax.
- 5-8 hyper-relevant viral tags (e.g., #Shorts #viral #trending #fyp #funny).
- 1 engaging question to drive comments.

Return ONLY a valid JSON object matching this schema:
{
  "title": "Exact Matching Viral Title 😱 #Shorts",
  "description": "Watch what happens next... What would you do in this situation? \\n\\n#Shorts #viral #trending #fyp",
  "tags": ["Shorts", "viral", "trending", "funny", "clip"],
  "pinned_comment": "Did he go too far? Let me know below 👇"
}
"""

class Copywriter:
    def __init__(self, ai_router: AIRouter):
        self.router = ai_router

    def generate_metadata(self, clip_transcript: str, hook_text: str = "", creator_name: str = "", video_title: str = "") -> Dict[str, Any]:
        """
        Uses Cerebras / Groq Llama-3.3-70B to generate viral title, description, and hashtags
        based strictly on the actual spoken words of the clip.
        """
        user_prompt = f"""Creator: {creator_name}
Original Video: {video_title}
Clip Hook / First Sentence: "{hook_text}"
Exact Clip Dialogue / Spoken Words:
\"\"\"{clip_transcript}\"\"\"

Generate an accurate, high-CTR YouTube Shorts title that specifically and truthfully matches what the creator says or does in this exact clip. Output in the specified JSON format.
"""
        try:
            raw_response = self.router.generate_chat(
                prompt=user_prompt,
                system_prompt=COPYWRITER_SYSTEM_PROMPT,
                preferred_provider="cerebras",
                json_mode=True
            )
            data = json.loads(raw_response)
            return data
        except Exception as e:
            logger.error(f"Copywriting failed: {e}")
            return {
                "title": f"Wait for the end... 🤯 #Shorts",
                "description": f"{hook_text}\n\n#Shorts #viral #trending",
                "tags": ["Shorts", "viral", "trending"],
                "pinned_comment": "What are your thoughts on this? 👇"
            }
