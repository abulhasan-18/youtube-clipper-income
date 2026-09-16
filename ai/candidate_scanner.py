import json
import logging
from typing import List, Dict, Any
from ai.router import AIRouter

logger = logging.getLogger("Clipper.Scanner")

CANDIDATE_SYSTEM_PROMPT = """You are an expert viral content strategist specializing in YouTube Shorts, TikTok, and Instagram Reels.
Your task is to analyze a timestamped transcript from a long-form video, stream, or podcast, and extract all candidate segments (between 25 and 60 seconds) that have high viral potential.

Rules for Viral Candidates:
1. Strong Hook: The first 3 seconds must grab attention (surprising statement, bold claim, intense question, punchy humor).
2. Self-Contained: The viewer must understand the context without needing the rest of the 2-hour video.
3. High Engagement: Contains emotional intensity, humor, surprising facts, dramatic conflict, or actionable insight.
4. Clean Boundaries: Exact start and end times should align with natural sentence boundaries.
5. Duration: Each clip MUST be strictly between 25 and 60 seconds.

Return ONLY a valid JSON object matching this schema:
{
  "candidates": [
    {
      "start_time": 124.5,
      "end_time": 168.0,
      "duration": 43.5,
      "hook_text": "The first sentence spoken...",
      "topic": "Brief topic summary",
      "initial_reason": "Why this moment will keep viewers watching"
    }
  ]
}
"""

class CandidateScanner:
    def __init__(self, ai_router: AIRouter):
        self.router = ai_router

    def scan_transcript(self, segments: List[Dict[str, Any]], max_candidates: int = 60) -> List[Dict[str, Any]]:
        """
        Uses Cerebras Llama-3.3-70B for ultra-fast candidate extraction across the transcript.
        """
        logger.info(f"Scanning transcript ({len(segments)} segments) for viral candidates...")

        # Build timestamped transcript string
        formatted_lines = []
        for s in segments:
            start_m = int(s["start"] // 60)
            start_s = int(s["start"] % 60)
            formatted_lines.append(f"[{start_m:02d}:{start_s:02d} - {s['start']:.1f}s] {s['text'].strip()}")

        transcript_text = "\n".join(formatted_lines)

        user_prompt = f"""Here is the timestamped transcript:
---
{transcript_text}
---

Find up to {max_candidates} high-potential viral moments (25 to 60 seconds each).
Output strictly in the specified JSON schema.
"""

        try:
            raw_response = self.router.generate_chat(
                prompt=user_prompt,
                system_prompt=CANDIDATE_SYSTEM_PROMPT,
                preferred_provider="cerebras",
                json_mode=True
            )
            # Parse JSON
            data = json.loads(raw_response)
            candidates = data.get("candidates", [])
            logger.info(f"Extracted {len(candidates)} candidate clips from transcript.")
            return candidates
        except Exception as e:
            logger.error(f"Candidate scanning failed: {e}")
            return []
