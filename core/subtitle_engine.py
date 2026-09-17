import os
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("Clipper.Subtitles")

EMOJI_KEYWORD_MAP = {
    "MONEY": "💰", "DOLLAR": "💵", "CASH": "💸", "RICH": "🤑", "MILLION": "💰", "PAID": "💳",
    "DEAD": "💀", "DYING": "💀", "LOL": "😂", "FUNNY": "🤣", "LAUGH": "😂", "JOKE": "🤡",
    "COLD": "🥶", "ICE": "❄️",
    "FIRE": "🔥", "CRAZY": "🔥", "INSANE": "🤯", "GOAT": "🐐", "KING": "👑", "WIN": "🏆",
    "WHAT": "😱", "OMG": "😱", "SHOCKED": "😳", "NO": "❌", "STOP": "🛑",
    "POLICE": "🚨", "CAUGHT": "👀", "EXPOSED": "📸", "SECRET": "🤫",
    "FIGHT": "🥊", "KNOCKOUT": "💥", "PUNCH": "👊", "UFC": "🥋",
    "GOAL": "⚽", "RONALDO": "🐐", "MESSI": "🐐", "FOOTBALL": "⚽"
}

class SubtitleEngine:
    def __init__(self, font_size: int = 54,
                 text_color: str = "#FFFFFF",
                 highlight_color: str = "#FFE600",
                 outline_color: str = "#000000",
                 outline_width: int = 6):
        self.font_size = font_size
        self.text_color = text_color
        self.highlight_color = highlight_color
        self.outline_color = outline_color
        self.outline_width = outline_width

        # Load fonts
        self.font = self._load_font(self.font_size)
        self.font_pop = self._load_font(int(self.font_size * 1.12))
        self.font_banner = self._load_font(38)
        self.font_emoji = self._load_emoji_font(48)

    def _load_font(self, size: int):
        font_candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Impact.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        for f in font_candidates:
            if os.path.exists(f):
                try:
                    return ImageFont.truetype(f, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _load_emoji_font(self, size: int = 48):
        emoji_path = "/System/Library/Fonts/Apple Color Emoji.ttc"
        if os.path.exists(emoji_path):
            try:
                return ImageFont.truetype(emoji_path, size)
            except Exception:
                pass
        return None

    def get_style_colors(self, edit_style: str) -> Tuple[str, str, str]:
        """
        Returns (highlight_color, accent_color, badge_border) based on content profile.
        """
        s = edit_style.lower() if edit_style else ""
        if "cyan" in s or "chill" in s:
            return ("#00F0FF", "#38E54D", "#00F0FF") # Electric Cyan & Neon Green
        elif "hype" in s:
            return ("#FFE600", "#FF3B30", "#FFE600") # Neon Yellow & Red
        else:
            return ("#FFE600", "#FFFFFF", "#FFE600") # Classic Hormozi Yellow

    def create_top_banner(self, banner_text: str, output_path: str,
                          canvas_w: int = 1080, canvas_h: int = 1920,
                          edit_style: str = "auto") -> Optional[str]:
        """
        Generates a sleek, high-CTR top curiosity badge banner overlay.
        Placed in the upper safe area (y = 200) clear of YouTube Shorts controls.
        """
        if not banner_text or not banner_text.strip():
            return None

        raw_text = banner_text.strip()
        # Separate emojis from plain text
        clean_text = re.sub(r"[^\w\s\+\,\-\!\?\$\#\%\:\.\']", "", raw_text).strip().upper()
        if not clean_text:
            clean_text = raw_text.upper()

        # Find emojis in banner
        emojis = [c for c in raw_text if ord(c) > 10000 or c in EMOJI_KEYWORD_MAP.values()]
        emoji_char = emojis[0] if emojis else ""

        highlight_col, _, border_col = self.get_style_colors(edit_style)

        img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        bbox = draw.textbbox((0, 0), clean_text, font=self.font_banner)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        emoji_w = 48 if (emoji_char and self.font_emoji) else 0

        # Pill background dimensions
        pad_x = 36
        pad_y = 16
        box_w = text_w + (emoji_w * 2 if emoji_w else 0) + pad_x * 2
        box_h = max(text_h, 40) + pad_y * 2
        box_x = (canvas_w - box_w) // 2
        box_y = 200 # Safe upper area

        # Draw dark frosted glass pill with rounded corners
        corner_r = 18
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=corner_r,
            fill=(10, 10, 15, 215),
            outline=border_col,
            width=3
        )

        curr_x = box_x + pad_x
        ty = box_y + (box_h - text_h) // 2 - 2

        if emoji_char and self.font_emoji:
            draw.text((curr_x, box_y + (box_h - 48) // 2), emoji_char, font=self.font_emoji, embedded_color=True)
            curr_x += emoji_w + 10

        # Outline
        for ox in range(-2, 3):
            for oy in range(-2, 3):
                if ox != 0 or oy != 0:
                    draw.text((curr_x + ox, ty + oy), clean_text, font=self.font_banner, fill="#000000")

        # Text
        draw.text((curr_x, ty), clean_text, font=self.font_banner, fill="#FFFFFF")
        curr_x += text_w + 10

        if emoji_char and self.font_emoji:
            draw.text((curr_x, box_y + (box_h - 48) // 2), emoji_char, font=self.font_emoji, embedded_color=True)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, "PNG")
        logger.info(f"Generated top hook banner: '{clean_text}' -> {output_path}")
        return output_path

    def create_subtitle_overlays(self, words: List[Dict[str, Any]], clip_start: float, clip_end: float,
                                 output_dir: str, canvas_w: int = 1080, canvas_h: int = 1920,
                                 words_per_card: int = 3,
                                 edit_style: str = "auto") -> List[Dict[str, Any]]:
        """
        Creates transparent PNG overlays for each word-highlight event with
        trending pop animations, content-adaptive colors, and contextual emojis.
        """
        os.makedirs(output_dir, exist_ok=True)
        highlight_col, _, _ = self.get_style_colors(edit_style)

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

            # Detect contextual emoji for this chunk
            chunk_emoji = ""
            for item in chunk:
                clean_w = re.sub(r"[^A-Z]", "", item["word"])
                if clean_w in EMOJI_KEYWORD_MAP:
                    chunk_emoji = EMOJI_KEYWORD_MAP[clean_w]
                    break

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
                for idx_c, item in enumerate(chunk):
                    font_to_use = self.font_pop if idx_c == active_idx else self.font
                    bbox = draw.textbbox((0, 0), item["word"], font=font_to_use)
                    w = bbox[2] - bbox[0]
                    h = bbox[3] - bbox[1]
                    widths.append((w, h))

                total_text_w = sum(w for w, _ in widths) + word_spacing * (len(chunk) - 1)
                emoji_w = 0
                if chunk_emoji:
                    e_bbox = draw.textbbox((0, 0), chunk_emoji, font=self.font)
                    emoji_w = e_bbox[2] - e_bbox[0] + 16
                    total_text_w += emoji_w

                start_x = (canvas_w - total_text_w) // 2
                base_y = canvas_h - 480 # Safe vertical placement for YouTube Shorts

                # Draw words
                current_x = start_x
                for j, item in enumerate(chunk):
                    w, h = widths[j]
                    is_active = (j == active_idx)
                    font_to_use = self.font_pop if is_active else self.font
                    color = highlight_col if is_active else self.text_color
                    # Slight upward pop for active word
                    y_offset = -4 if is_active else 0

                    # Draw thick black outline with shadow depth
                    ow = self.outline_width + (1 if is_active else 0)
                    for ox in range(-ow, ow + 1):
                        for oy in range(-ow, ow + 1):
                            if ox * ox + oy * oy <= ow * ow:
                                draw.text((current_x + ox, base_y + oy + y_offset), item["word"],
                                          font=font_to_use, fill=self.outline_color)

                    # Draw foreground text
                    draw.text((current_x, base_y + y_offset), item["word"], font=font_to_use, fill=color)
                    current_x += w + word_spacing

                # Draw trailing emoji if present
                if chunk_emoji:
                    if self.font_emoji:
                        draw.text((current_x, base_y - 2), chunk_emoji, font=self.font_emoji, embedded_color=True)
                    else:
                        draw.text((current_x, base_y - 2), chunk_emoji, font=self.font, fill="#FFFFFF")

                img_path = os.path.join(output_dir, f"sub_{card_id:04d}.png")
                img.save(img_path, "PNG")
                overlays.append({
                    "image_path": img_path,
                    "start": w_start,
                    "end": w_end
                })
                card_id += 1

        logger.info(f"Generated {len(overlays)} trending Hormozi animated subtitle cards in {output_dir}")
        return overlays
