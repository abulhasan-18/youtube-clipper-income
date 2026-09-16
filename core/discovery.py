import os
import sys
import yaml
import json
import random
import logging
import subprocess
from typing import List, Dict, Any, Optional
from storage.database import Database

logger = logging.getLogger("Clipper.Discovery")

CREATORS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "creators.yaml")

class ContentDiscovery:
    def __init__(self, creators_file: str = CREATORS_FILE, db: Optional[Database] = None):
        self.creators_file = creators_file
        self.db = db or Database()
        self.creators = self._load_creators()

    def _load_creators(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.creators_file):
            logger.warning(f"Creators file {self.creators_file} not found.")
            return []
        with open(self.creators_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("creators", [])

    def discover_next_unprocessed_video(self, min_duration_sec: float = 480.0,
                                        max_duration_sec: float = 14400.0) -> Optional[Dict[str, Any]]:
        """
        Picks a creator (shuffled for variety), searches for their latest videos/streams,
        and returns the first high-quality video that has NOT been clipped yet.
        """
        if not self.creators:
            logger.error("No creators registered in creators.yaml.")
            return None

        # Shuffle creators list so every run explores different creators
        shuffled_creators = list(self.creators)
        random.shuffle(shuffled_creators)

        for creator in shuffled_creators:
            creator_name = creator.get("name", "Unknown")
            search_q = creator.get("search_query") or f"{creator_name} full stream"
            logger.info(f"Checking fresh videos for creator: {creator_name}...")

            candidates = self.search_creator_videos(search_q, limit=5)
            for item in candidates:
                url = item.get("url")
                duration = item.get("duration", 0.0)

                # Check duration filters (ignore shorts or 10-hour loops)
                if duration and (duration < min_duration_sec or duration > max_duration_sec):
                    continue

                # Check if already clipped
                if not self.db.is_video_processed(url):
                    logger.info(f"Found new unprocessed video: '{item.get('title')}' by {creator_name}")
                    item["creator_name"] = creator_name
                    return item

        logger.info("No new unprocessed videos found across all creators right now.")
        return None

    def search_creator_videos(self, search_query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Uses yt-dlp python module to find recent videos matching search_query without downloading media.
        """
        cmd = [
            sys.executable, "-m", "yt_dlp",
            f"ytsearch{limit}:{search_query}",
            "--dump-json",
            "--flat-playlist",
            "--no-playlist"
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            results = []
            for line in res.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    video_url = data.get("url")
                    if not video_url or not video_url.startswith("http"):
                        video_id = data.get("id")
                        if video_id:
                            video_url = f"https://www.youtube.com/watch?v={video_id}"

                    if video_url:
                        results.append({
                            "url": video_url,
                            "title": data.get("title", "Untitled"),
                            "duration": data.get("duration", 0.0),
                            "id": data.get("id", ""),
                            "view_count": data.get("view_count", 0)
                        })
                except json.JSONDecodeError:
                    continue
            return results
        except Exception as e:
            logger.warning(f"Failed searching with query '{search_query}': {e}")
            return []
