import json
import logging
from typing import List, Dict, Any
from ai.router import AIRouter

logger = logging.getLogger("Clipper.Scanner")

CANDIDATE_SYSTEM_PROMPT = """You are an expert viral content strategist specializing in YouTube Shorts, TikTok, and Instagram Reels.
Your task is to analyze a timestamped transcript from a long-form video, stream, or podcast, and extract all candidate segments (between 25 and 60 seconds) that have high viral potential.

Rules for Viral Candidates:
1. Strong Hook: The first 3 seconds must grab attention (hilarious statement, unexpected joke, drama, heated debate, or shocking story).
2. Self-Contained Climax: The viewer gets an immediate punchline, jaw-dropping moment, or satisfying conclusion.
3. Clean Boundaries: Exact start and end times aligned with natural speech flow.
4. Duration: Strictly between 25 and 60 seconds.

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

        max_duration = max([float(s.get("end", s.get("start", 0))) for s in segments], default=0.0)

        user_prompt = f"""Here is the timestamped transcript:
---
{transcript_text}
---

Total video duration is {max_duration:.1f} seconds.
All start_time and end_time values MUST be strictly within 0.0s and {max_duration:.1f}s.
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
            raw_candidates = data.get("candidates", [])

            # Filter out out-of-bounds or invalid candidates
            candidates = []
            for c in raw_candidates:
                st = float(c.get("start_time", 0))
                et = float(c.get("end_time", 0))
                if max_duration > 0 and (st >= max_duration or et > max_duration + 1.5):
                    continue
                if et <= st or (et - st) < 15 or (et - st) > 75:
                    continue
                c["start_time"] = round(st, 1)
                c["end_time"] = round(min(et, max_duration) if max_duration > 0 else et, 1)
                candidates.append(c)

            logger.info(f"Extracted {len(candidates)} valid candidate clips (from {len(raw_candidates)} suggested) within {max_duration:.1f}s bounds.")
            return candidates
        except Exception as e:
            logger.error(f"Candidate scanning failed: {e}")
            return []
