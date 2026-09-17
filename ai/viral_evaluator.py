import json
import logging
from typing import List, Dict, Any
from ai.router import AIRouter

logger = logging.getLogger("Clipper.ViralEvaluator")

EVALUATOR_SYSTEM_PROMPT = """You are a master viral algorithm expert who has generated billions of views across YouTube Shorts, Instagram Reels, and TikTok.

Your goal is to critically judge candidate video clips and rate their viral psychology.
Evaluate each candidate on:
1. Hook Retention Score (1-10): Will a user scrolling past stop in 0.5 to 2 seconds?
2. Curiosity Gap (1-10): Does it create an open loop that compels watching until the end?
3. Emotional / Humor Intensity (1-10): Is it laugh-out-loud funny, shocking, or intense?
4. Shareability / Re-watch Value (1-10): Would viewers share this or re-watch?
5. Overall Virality Score (1-10): The composite metric determining algorithm push.

Return ONLY a valid JSON object matching this schema:
{
  "ranked_clips": [
    {
      "start_time": 124.5,
      "end_time": 168.0,
      "hook_score": 9.2,
      "curiosity_gap": 8.8,
      "virality_score": 9.4,
      "hook_critique": "Why the hook works or how to maximize impact",
      "pacing_verdict": "fast / medium / slow",
      "status": "approved"
    }
  ]
}
"""

class ViralEvaluator:
    def __init__(self, ai_router: AIRouter):
        self.router = ai_router

    def evaluate_and_rank(self, candidates: List[Dict[str, Any]], top_n: int = 50) -> List[Dict[str, Any]]:
        """
        Uses OpenRouter (DeepSeek R1 / V3) or Gemini for deep viral reasoning and scoring.
        """
        if not candidates:
            return []

        logger.info(f"Evaluating viral psychology of {len(candidates)} candidates...")

        user_prompt = f"""Evaluate these candidate clips:
{json.dumps(candidates, indent=2)}

Rank them strictly by virality_score. Return the approved clips in the specified JSON format.
"""

        try:
            raw_response = self.router.generate_chat(
                prompt=user_prompt,
                system_prompt=EVALUATOR_SYSTEM_PROMPT,
                preferred_provider="openrouter",
                json_mode=True
            )
            data = json.loads(raw_response)
            ranked = data.get("ranked_clips", [])
            
            # Filter approved and sort
            approved = [c for c in ranked if c.get("status") == "approved" or c.get("virality_score", 0) >= 7.0]
            approved.sort(key=lambda x: x.get("virality_score", 0), reverse=True)
            
            # Merge original candidate metadata (hook_text, topic) if present
            merged_results = []
            for item in approved[:top_n]:
                # find matching candidate by start_time
                match = next((c for c in candidates if abs(c["start_time"] - item["start_time"]) < 2.0), {})
                merged_results.append({**match, **item})

            logger.info(f"Evaluated & approved {len(merged_results)} viral clips.")
            return merged_results
        except Exception as e:
            logger.error(f"Viral evaluation failed: {e}. Falling back to candidate scores...")
            # Fallback: keep top candidates
            return candidates[:top_n]
