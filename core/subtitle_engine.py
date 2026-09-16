import os
import logging
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("Clipper.Subtitles")

class SubtitleEngine:
    def __init__(self, font_size: int = 56,
                 text_color: str = "#FFFFFF",
                 highlight_color: str = "#FFE600",
                 outline_color: str = "#000000",
                 outline_width: int = 6):
        self.font_size = font_size
        self.text_color = text_color
        self.highlight_color = highlight_color
        self.outline_color = outline_color
        self.outline_width = outline_width

        # Try to load a bold system font on macOS
        self.font = self._load_font()

    def _load_font(self):
        font_candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Impact.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        for f in font_candidates:
            if os.path.exists(f):
                try:
                    return ImageFont.truetype(f, self.font_size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def create_subtitle_overlays(self, words: List[Dict[str, Any]], clip_start: float, clip_end: float,
                                 output_dir: str, canvas_w: int = 1080, canvas_h: int = 1920,
                                 words_per_card: int = 3) -> List[Dict[str, Any]]:
        """
        Creates transparent PNG overlays for each word-highlight event and
        returns metadata with [start_sec, end_sec, image_path].
        """
        os.makedirs(output_dir, exist_ok=True)

        # 1. Filter and normalize words to clip start time
        clip_words = []
        for w in words:
            w_start = w.get("start", 0.0)
            w_end = w.get("end", 0.0)
            word_str = w.get("word", "").strip()
            if not word_str:
                continue

            if w_end >= clip_start and w_start <= clip_end:
                rel_start = max(0.0, w_start - clip_start)
                rel_end = max(rel_start + 0.08, min(clip_end - clip_start, w_end - clip_start))
                clip_words.append({
                    "word": word_str.upper(),
                    "start": rel_start,
                    "end": rel_end
                })

        if not clip_words:
            logger.warning("No words found for subtitle overlay.")
            return []

        overlays = []
        card_id = 0

        # 2. Group into chunks of 2-4 words
        for i in range(0, len(clip_words), words_per_card):
            chunk = clip_words[i:i + words_per_card]

            # For each word in this chunk, create a frame where this word is highlighted
            for active_idx, active_word in enumerate(chunk):
                w_start = active_word["start"]
                w_end = active_word["end"]

                # Render transparent RGBA image
                img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)

                # Calculate line layout
                word_spacing = 16
                widths = []
                for item in chunk:
                    bbox = draw.textbbox((0, 0), item["word"], font=self.font)
                    w = bbox[2] - bbox[0]
                    h = bbox[3] - bbox[1]
                    widths.append((w, h))

                total_text_w = sum(w for w, _ in widths) + word_spacing * (len(chunk) - 1)
                start_x = (canvas_w - total_text_w) // 2
                base_y = canvas_h - 480 # Safe vertical placement for YouTube Shorts

                # Draw words
                current_x = start_x
                for j, item in enumerate(chunk):
                    w, h = widths[j]
                    color = self.highlight_color if j == active_idx else self.text_color

                    # Draw thick black outline
                    for ox in range(-self.outline_width, self.outline_width + 1):
                        for oy in range(-self.outline_width, self.outline_width + 1):
                            if ox * ox + oy * oy <= self.outline_width * self.outline_width:
                                draw.text((current_x + ox, base_y + oy), item["word"],
                                          font=self.font, fill=self.outline_color)

                    # Draw foreground text
                    draw.text((current_x, base_y), item["word"], font=self.font, fill=color)
                    current_x += w + word_spacing

                img_path = os.path.join(output_dir, f"sub_{card_id:04d}.png")
                img.save(img_path, "PNG")
                overlays.append({
                    "image_path": img_path,
                    "start": w_start,
                    "end": w_end
                })
                card_id += 1

        logger.info(f"Generated {len(overlays)} Hormozi animated subtitle cards in {output_dir}")
        return overlays
