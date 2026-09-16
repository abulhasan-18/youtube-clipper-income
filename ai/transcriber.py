import os
import json
import logging
from typing import Dict, Any, List, Optional
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("Clipper.Transcriber")

class GroqTranscriber:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not set in environment or config.")
        self.client = Groq(api_key=self.api_key)

    def transcribe_audio(self, audio_path: str, language: str = "en") -> Dict[str, Any]:
        """
        Transcribes audio using Groq whisper-large-v3 with word-level timestamps.
        Returns a dict containing 'text', 'segments', and 'words'.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        logger.info(f"Transcribing audio with Groq whisper-large-v3 ({file_size_mb:.2f} MB)...")

        # Check Groq file size limit (25MB max per request)
        if file_size_mb > 24.5:
            logger.info("File exceeds 25MB, splitting into chunks...")
            return self._transcribe_chunked(audio_path)

        with open(audio_path, "rb") as f:
            transcription = self.client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), f),
                model="whisper-large-v3",
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"],
                temperature=0.0
            )

        result = transcription.to_dict() if hasattr(transcription, "to_dict") else dict(transcription)
        return result

    def _transcribe_chunked(self, audio_path: str) -> Dict[str, Any]:
        """
        Splits large audio into 15-minute segments using FFmpeg,
        transcribes each via Groq, and combines timestamps.
        """
        import subprocess
        temp_dir = os.path.join(os.path.dirname(audio_path), "audio_chunks")
        os.makedirs(temp_dir, exist_ok=True)

        chunk_pattern = os.path.join(temp_dir, "chunk_%03d.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-i", audio_path,
            "-f", "segment", "-segment_time", "600", # 10 min chunks
            "-c:a", "libmp3lame", "-b:a", "64k",
            chunk_pattern
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        chunk_files = sorted([os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.endswith(".mp3")])
        
        full_text = []
        all_segments = []
        all_words = []
        time_offset = 0.0

        for chunk_file in chunk_files:
            with open(chunk_file, "rb") as f:
                res = self.client.audio.transcriptions.create(
                    file=(os.path.basename(chunk_file), f),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    timestamp_granularities=["word", "segment"]
                )
            res_dict = res.to_dict() if hasattr(res, "to_dict") else dict(res)
            
            full_text.append(res_dict.get("text", ""))
            
            for seg in res_dict.get("segments", []):
                seg["start"] += time_offset
                seg["end"] += time_offset
                all_segments.append(seg)

            for w in res_dict.get("words", []):
                w["start"] += time_offset
                w["end"] += time_offset
                all_words.append(w)

            # Determine chunk duration
            if res_dict.get("segments"):
                time_offset = res_dict["segments"][-1]["end"]
            else:
                time_offset += 600.0

            os.remove(chunk_file)

        return {
            "text": " ".join(full_text),
            "segments": all_segments,
            "words": all_words,
        }
