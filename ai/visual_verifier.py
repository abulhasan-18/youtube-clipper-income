import os
import json
import logging
import subprocess
from typing import Dict, Any, List
from ai.router import AIRouter

logger = logging.getLogger("Clipper.VisualVerifier")

class VisualVerifier:
    def __init__(self, ai_router: AIRouter):
        self.router = ai_router

    def extract_keyframes(self, video_path: str, start_time: float, end_time: float, num_frames: int = 3) -> List[str]:
        """
        Extracts representative keyframes from the clip segment using FFmpeg.
        """
        duration = end_time - start_time
        step = duration / (num_frames + 1)
        frame_paths = []
        temp_dir = os.path.join(os.path.dirname(video_path), "keyframes")
        os.makedirs(temp_dir, exist_ok=True)

        for i in range(1, num_frames + 1):
            ts = start_time + (step * i)
            out_img = os.path.join(temp_dir, f"frame_{int(start_time)}_{i}.jpg")
            cmd = [
                "ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
                "-vframes", "1", "-q:v", "2", out_img
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(out_img):
                frame_paths.append(out_img)

        return frame_paths

    def verify_clip_visuals(self, frame_paths: List[str], topic: str) -> Dict[str, Any]:
        """
        Uses Google Gemini to visually inspect keyframes for camera clarity,
        facial expressions, and dynamic screen content.
        """
        if not self.router.gemini_client or not frame_paths:
            return {"visual_score": 8.0, "status": "approved", "note": "Gemini verification bypassed or no frames"}

        try:
            from PIL import Image
            images = [Image.open(p) for p in frame_paths if os.path.exists(p)]
            if not images:
                return {"visual_score": 8.0, "status": "approved"}

            prompt = f"""These are keyframes from a candidate short video about: "{topic}".
Analyze the visual quality:
1. Are faces / subjects clearly visible and well-lit?
2. Is there dynamic action, emotion, or high visual interest (not a blank/static screen)?
3. Rate visual appeal (1-10) and recommend framing (speaker_centered, split_screen, or standard_crop).

Output strictly in JSON:
{{
  "visual_score": 8.5,
  "status": "approved",
  "recommended_framing": "speaker_centered",
  "reasoning": "Clear speaker expression with high engagement"
}}
"""
            contents = [*images, prompt]
            response = self.router.gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=contents,
                config={"response_mime_type": "application/json"}
            )
            data = json.loads(response.text)
            return data
        except Exception as e:
            logger.warning(f"Visual verification via Gemini skipped: {e}")
            return {"visual_score": 8.0, "status": "approved", "note": str(e)}
