import os
import sys
import yaml
import logging
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.table import Table

from ai import (
    AIRouter,
    GroqTranscriber,
    CandidateScanner,
    ViralEvaluator,
    VisualVerifier,
    Copywriter
)
from core import (
    MediaDownloader,
    VideoProcessor
)
from storage.database import Database

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Clipper.Pipeline")

class ClipperPipeline:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.db = Database(self.config.get("paths", {}).get("database", "storage/clipper.db"))
        self.router = AIRouter()
        self.transcriber = GroqTranscriber()
        self.scanner = CandidateScanner(self.router)
        self.evaluator = ViralEvaluator(self.router)
        self.visual_verifier = VisualVerifier(self.router)
        self.copywriter = Copywriter(self.router)

        self.downloader = MediaDownloader(self.config.get("paths", {}).get("downloads", "downloads"))
        self.video_processor = VideoProcessor(
            target_width=self.config.get("video", {}).get("target_width", 1080),
            target_height=self.config.get("video", {}).get("target_height", 1920)
        )
        self.output_dir = self.config.get("paths", {}).get("output", "output")
        os.makedirs(self.output_dir, exist_ok=True)

    def process_video(self, source_url: str, max_clips: int = 5,
                      reframe_mode: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Executes end-to-end automated clipping flow:
        Download -> Groq Whisper -> AI Selection -> Render 9:16 Shorts with Subtitles
        """
        mode = reframe_mode or self.config.get("video", {}).get("reframe_mode", "face_track")
        console.rule("[bold cyan]AI Video Clipper Pipeline")
        console.print(f"[bold yellow]Ingesting:[/bold yellow] {source_url}")

        # 1. Metadata & Video Record
        info = self.downloader.extract_info(source_url)
        video_title = info.get("title", "Untitled")
        duration = info.get("duration", 0.0)
        console.print(f"[green]Title:[/green] {video_title} ({duration/60:.1f} minutes)")

        video_id = self.db.add_video(
            source_url=source_url,
            source_type="youtube" if "youtu" in source_url else "stream",
            title=video_title,
            duration=duration
        )

        # 2. Ultra-Fast Audio Extraction
        console.print("[cyan]Step 1/5: Downloading high-speed audio...[/cyan]")
        audio_path = self.downloader.download_audio_fast(source_url)

        # 3. Groq Whisper Transcription with Word Timings
        console.print("[cyan]Step 2/5: Transcribing on Groq Whisper LPU...[/cyan]")
        transcript_data = self.transcriber.transcribe_audio(audio_path)
        all_words = transcript_data.get("words", [])
        segments = transcript_data.get("segments", [])
        self.db.update_video_transcript(video_id, transcript_data.get("text", ""))
        console.print(f"[green]Transcription complete: {len(segments)} segments, {len(all_words)} words.[/green]")

        # 4. Multi-Model Viral Candidates Extraction & Deep Reasoning
        console.print("[cyan]Step 3/5: Scanning for viral candidate clips...[/cyan]")
        candidates = self.scanner.scan_transcript(segments, max_candidates=max_clips * 2)
        if not candidates:
            console.print("[red]No candidate clips found in transcript.[/red]")
            return []

        console.print(f"[cyan]Step 4/5: Evaluating viral psychology & ranking top {max_clips} clips...[/cyan]")
        approved_clips = self.evaluator.evaluate_and_rank(candidates, top_n=max_clips)

        # 5. Video Slicing, Copywriting, Reframing, Subtitling
        console.print(f"[cyan]Step 5/5: Processing and rendering {len(approved_clips)} vertical shorts...[/cyan]")
        final_rendered_clips = []

        for idx, clip in enumerate(approved_clips, start=1):
            start_t = clip["start_time"]
            end_t = clip["end_time"]
            hook_text = clip.get("hook_text", "")
            topic = clip.get("topic", video_title)

            console.print(f"\n[bold magenta]Processing Clip {idx}/{len(approved_clips)}[/bold magenta] ({start_t:.1f}s -> {end_t:.1f}s)")

            # Generate High-CTR Metadata
            metadata = self.copywriter.generate_metadata(topic, hook_text, video_title)
            clip_title = metadata.get("title", f"Viral Moment #{idx} #Shorts")
            clip_desc = metadata.get("description", "")
            tags = metadata.get("tags", ["Shorts", "viral"])
            tags_str = ",".join(tags)

            console.print(f"  [bold]Title:[/bold] {clip_title}")
            console.print(f"  [bold]Hook:[/bold] {hook_text[:60]}...")

            # Save clip record to DB
            clip_id = self.db.add_clip(
                video_id=video_id,
                start_time=start_t,
                end_time=end_t,
                virality_score=clip.get("virality_score", 8.5),
                hook_text=hook_text,
                title=clip_title,
                description=clip_desc,
                tags=tags_str
            )

            # Download targeted video segment
            raw_clip_name = f"raw_{video_id}_{clip_id}_{int(start_t)}.mp4"
            raw_clip_path = self.downloader.download_clip_segment(source_url, start_t, end_t, raw_clip_name)

            # Render final 9:16 vertical video with dynamic subtitles
            rendered_clip_name = f"short_{video_id}_{clip_id}.mp4"
            rendered_path = os.path.join(self.output_dir, rendered_clip_name)

            self.video_processor.process_clip(
                input_video=raw_clip_path,
                words=all_words,
                clip_start=start_t,
                clip_end=end_t,
                output_path=rendered_path,
                mode=mode
            )

            # Update DB
            self.db.update_clip_rendered(clip_id, rendered_path)
            clip["rendered_path"] = rendered_path
            clip["title"] = clip_title
            clip["id"] = clip_id
            final_rendered_clips.append(clip)

            # Remove raw temporary slice
            try:
                os.remove(raw_clip_path)
            except Exception:
                pass

        # Print summary table
        table = Table(title="Generated Viral YouTube Shorts")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="green")
        table.add_column("Duration", style="yellow")
        table.add_column("Score", style="magenta")
        table.add_column("Path", style="white")

        for c in final_rendered_clips:
            dur = c["end_time"] - c["start_time"]
            table.add_row(str(c["id"]), c["title"], f"{dur:.1f}s", f"{c.get('virality_score', 8.5):.1f}", c["rendered_path"])

        console.print("\n")
        console.print(table)
        console.print(f"\n[bold green]Success! {len(final_rendered_clips)} shorts rendered and added to the upload queue.[/bold green]\n")
        return final_rendered_clips

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <YOUTUBE_URL_OR_FILE> [MAX_CLIPS]")
        sys.exit(1)
    url = sys.argv[1]
    clips_num = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    pipeline = ClipperPipeline()
    pipeline.process_video(url, max_clips=clips_num)
