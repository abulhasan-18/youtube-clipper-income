import os
import sys
import re
import json
import logging
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger("Clipper.Downloader")

class MediaDownloader:
    def __init__(self, downloads_dir: str = "downloads"):
        self.downloads_dir = downloads_dir
        os.makedirs(self.downloads_dir, exist_ok=True)

    def extract_info(self, url: str) -> Dict[str, Any]:
        """
        Extracts metadata from YouTube, Twitch, or podcast link without downloading.
        """
        logger.info(f"Extracting metadata from {url}...")
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--dump-json",
            "--no-playlist",
            url
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        return {
            "title": data.get("title", "Untitled"),
            "duration": data.get("duration", 0.0),
            "uploader": data.get("uploader", ""),
            "id": data.get("id", ""),
            "url": url
        }

    def _extract_video_id(self, url: str) -> str:
        m = re.search(r"(?:v=|\/shorts\/|youtu\.be\/)([a-zA-Z0-9_-]{11})", url)
        if m:
            return m.group(1)
        return re.sub(r"[^a-zA-Z0-9_-]", "_", url)[-15:]

    def download_audio_fast(self, url: str) -> str:
        """
        Downloads high-speed compressed audio (MP3) for Whisper transcription.
        Downloads in seconds even for 2-hour streams.
        """
        vid_id = self._extract_video_id(url)
        expected_file = os.path.join(self.downloads_dir, f"{vid_id}_audio.mp3")
        if os.path.exists(expected_file):
            return expected_file

        logger.info(f"Downloading high-speed audio for {url} (ID: {vid_id})...")
        output_template = os.path.join(self.downloads_dir, f"{vid_id}_audio.%(ext)s")
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "5", # ~128kbps, perfect for Whisper
            "--no-playlist",
            "-o", output_template,
            url
        ]
        subprocess.run(cmd, check=True)

        if os.path.exists(expected_file):
            return expected_file

        # Locate exact downloaded file matching this video ID
        for f in os.listdir(self.downloads_dir):
            if f.startswith(vid_id) and f.endswith(".mp3"):
                return os.path.join(self.downloads_dir, f)
        raise FileNotFoundError(f"Audio file for video {vid_id} not found after download.")

    def download_clip_segment(self, url: str, start_time: float, end_time: float, output_filename: str) -> str:
        """
        Downloads ONLY the specific slice of video (e.g. 120s to 165s) directly from the stream.
        Saves massive bandwidth and disk space.
        """
        out_path = os.path.join(self.downloads_dir, output_filename)
        section_arg = f"*{int(start_time)}-{int(end_time)}"
        logger.info(f"Downloading video section {section_arg} to {out_path}...")

        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--download-sections", section_arg,
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--force-keyframes-at-cuts",
            "-o", out_path,
            "--no-playlist",
            url
        ]
        subprocess.run(cmd, check=True)
        return out_path
