import os
import subprocess
import logging
from typing import Optional, List, Dict, Any
from core.face_tracker import FaceTracker
from core.subtitle_engine import SubtitleEngine

logger = logging.getLogger("Clipper.VideoProcessor")

class VideoProcessor:
    def __init__(self, target_width: int = 1080, target_height: int = 1920):
        self.target_width = target_width
        self.target_height = target_height
        self.face_tracker = FaceTracker()
        self.subtitle_engine = SubtitleEngine()

    def process_clip(self, input_video: str, words: List[Dict[str, Any]],
                     clip_start: float, clip_end: float,
                     output_path: str, mode: str = "blur_bg",
                     edit_style: str = "auto",
                     banner_text: str = "") -> str:
        """
        Reframes video to 9:16 vertical (1080x1920) keeping native 16:9 widescreen 100% visible,
        normalizes audio for mobile platforms, and burns dynamic Hormozi animated subtitles.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        temp_dir = os.path.abspath(os.path.join(os.path.dirname(output_path), "temp_subtitles"))
        os.makedirs(temp_dir, exist_ok=True)

        logger.info(f"Processing clip {input_video} -> {output_path}...")

        # Professional broadcast grading with ambient blurred background
        bg_grade = "boxblur=25:2,eq=brightness=-0.16:contrast=1.06"
        fg_grade = "eq=contrast=1.08:saturation=1.12:brightness=0.01"

        # Base Reframe filter: Native 16:9 video 100% visible & centered in 9:16 canvas
        base_reframe = (
            f"[0:v]scale={self.target_width}:{self.target_height}:force_original_aspect_ratio=increase,"
            f"crop={self.target_width}:{self.target_height},{bg_grade}[bg];"
            f"[0:v]scale={self.target_width}:-2,{fg_grade}[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )

        # Build Subtitle Overlays
        overlays = self.subtitle_engine.create_subtitle_overlays(
            words=words, clip_start=clip_start, clip_end=clip_end,
            output_dir=temp_dir, canvas_w=self.target_width, canvas_h=self.target_height,
            edit_style="standard"
        )

        clip_duration = clip_end - clip_start
        inputs = ["-i", input_video]
        input_idx = 1
        filter_chain = f"{base_reframe}[base]"
        last_v = "base"

        # Add subtitles concat stream if overlays exist
        if overlays:
            concat_path = os.path.join(temp_dir, "subtitles_concat.txt")
            current_time = 0.0
            blank_png = os.path.abspath(os.path.join(temp_dir, "blank.png"))
            from PIL import Image
            Image.new("RGBA", (self.target_width, self.target_height), (0, 0, 0, 0)).save(blank_png, "PNG")

            with open(concat_path, "w", encoding="utf-8") as f:
                for item in overlays:
                    start_t = item["start"]
                    end_t = item["end"]
                    dur = max(0.04, end_t - start_t)
                    img_abs = os.path.abspath(item["image_path"])

                    # If gap before subtitle, pad with blank
                    if start_t > current_time + 0.04:
                        gap_dur = start_t - current_time
                        f.write(f"file '{blank_png}'\n")
                        f.write(f"duration {gap_dur:.3f}\n")
                        current_time += gap_dur

                    f.write(f"file '{img_abs}'\n")
                    f.write(f"duration {dur:.3f}\n")
                    current_time += dur

                if current_time < clip_duration:
                    f.write(f"file '{blank_png}'\n")
                    f.write(f"duration {(clip_duration - current_time):.3f}\n")

                f.write(f"file '{blank_png}'\n")

            inputs.extend(["-f", "concat", "-safe", "0", "-i", concat_path])
            filter_chain += f";[{last_v}][{input_idx}:v]overlay=0:0:eof_action=pass[outv]"
            last_v = "outv"
            input_idx += 1
        else:
            filter_chain += f";[{last_v}]null[outv]"
            last_v = "outv"

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_chain,
            "-map", f"[{last_v}]",
            "-map", "0:a?",
            "-af", "loudnorm=I=-14:LRA=7:tp=-1.5",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "21",
            "-c:a", "aac",
            "-b:a", "192k",
            "-r", "30",
            "-pix_fmt", "yuv420p",
            output_path
        ]

        logger.info(f"Rendering final 9:16 vertical short with trending edits ({edit_style})...")
        subprocess.run(cmd, check=True)
        logger.info(f"Render successfully completed: {output_path}")

        # Cleanup temp subtitle files
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except Exception:
            pass

        return output_path
