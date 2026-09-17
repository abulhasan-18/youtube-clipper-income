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
                     output_path: str, mode: str = "face_track") -> str:
        """
        Reframes video to 9:16 vertical (1080x1920), normalizes audio,
        and burns dynamic Hormozi subtitles using frame overlays.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        temp_dir = os.path.abspath(os.path.join(os.path.dirname(output_path), "temp_subtitles"))
        os.makedirs(temp_dir, exist_ok=True)

        logger.info(f"Processing clip {input_video} in mode '{mode}' -> {output_path}...")

        # 1. Base Reframe filter
        # Keeps native 16:9 widescreen video 100% intact and centers it in the 9:16 vertical Shorts canvas
        if mode in ["blur_bg", "face_track", "center_crop"]:
            base_reframe = (
                f"[0:v]scale={self.target_width}:{self.target_height}:force_original_aspect_ratio=increase,"
                f"crop={self.target_width}:{self.target_height},"
                f"boxblur=25:2,eq=brightness=-0.15:contrast=1.05[bg];"
                f"[0:v]scale={self.target_width}:-2[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
            )
        elif mode == "split_screen":
            base_reframe = (
                f"[0:v]crop=iw/3:ih/2:0:0,scale={self.target_width}:{self.target_height//2}[top];"
                f"[0:v]crop=iw*2/3:ih:iw/3:0,scale={self.target_width}:{self.target_height//2}[bot];"
                f"[top][bot]vstack"
            )
        else:
            base_reframe = (
                f"[0:v]scale={self.target_width}:{self.target_height}:force_original_aspect_ratio=increase,"
                f"crop={self.target_width}:{self.target_height},"
                f"boxblur=25:2,eq=brightness=-0.15:contrast=1.05[bg];"
                f"[0:v]scale={self.target_width}:-2[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
            )

        # 2. Build Subtitle Overlays if words are available
        overlays = self.subtitle_engine.create_subtitle_overlays(
            words=words, clip_start=clip_start, clip_end=clip_end,
            output_dir=temp_dir, canvas_w=self.target_width, canvas_h=self.target_height
        )

        clip_duration = clip_end - clip_start

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

            filter_str = f"{base_reframe}[base];[base][1:v]overlay=0:0:eof_action=pass[outv]"

            cmd = [
                "ffmpeg", "-y",
                "-i", input_video,
                "-f", "concat", "-safe", "0", "-i", concat_path,
                "-filter_complex", filter_str,
                "-map", "[outv]",
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
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", input_video,
                "-vf", base_reframe,
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

        logger.info("Rendering final 9:16 vertical short with FFmpeg...")
        subprocess.run(cmd, check=True)
        logger.info(f"Render successfully completed: {output_path}")

        # Cleanup temp subtitle files
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except Exception:
            pass

        return output_path
