import os
import time
import yaml
import logging
from datetime import datetime, date
from rich.console import Console
from rich.panel import Panel

from core.discovery import ContentDiscovery
from pipeline import ClipperPipeline
from storage.database import Database
from uploader.youtube_studio import YouTubeStudioUploader
from uploader.youtube_api import YouTubeAPIUploader

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Clipper.AutoPilot")

class AutoPilotService:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        db_path = self.config.get("paths", {}).get("database", "storage/clipper.db")
        self.db = Database(db_path)
        self.discovery = ContentDiscovery(db=self.db)
        self.pipeline = ClipperPipeline(config_path=config_path)

        # Publishing settings
        self.target_daily = self.config.get("publishing", {}).get("target_daily_uploads", 50)
        self.interval_sec = self.config.get("publishing", {}).get("interval_minutes", 28) * 60
        self.visibility = self.config.get("publishing", {}).get("default_visibility", "public")
        self.reframe_mode = self.config.get("video", {}).get("reframe_mode", "face_track")

        backend = self.config.get("publishing", {}).get("upload_backend", "studio")
        if backend == "studio":
            self.uploader = YouTubeStudioUploader(headless=True)
        else:
            self.uploader = YouTubeAPIUploader()

        self.last_upload_time = 0.0

    def run_autonomous_loop(self):
        """
        100% Autonomous 24/7 Loop:
        - Discovers videos from the 50 monitored creators
        - Clips and renders 9:16 vertical shorts with dynamic subtitles
        - Schedules and uploads 50 shorts daily to YouTube Shorts
        """
        console.rule("[bold cyan]🤖 Clipper AutoPilot: 100% Autonomous 24/7 Service")
        console.print(Panel(
            f"[bold green]Monitored Creators:[/bold green] 50 Top Streamers (IShowSpeed, Kai Cenat, Ibai, xQc, Adin Ross, etc.)\n"
            f"[bold green]Target Output:[/bold green] 50 Viral Shorts / Day\n"
            f"[bold green]Upload Cadence:[/bold green] 1 Short every {self.interval_sec/60:.1f} minutes\n"
            f"[bold green]Auto-Reframe:[/bold green] 9:16 Vertical with Face Tracking & Hormozi Captions",
            title="AutoPilot Initialized",
            border_style="cyan"
        ))

        while True:
            try:
                today_count = self.db.get_todays_upload_count()
                queued_count = self.db.get_queued_count()
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                console.print(f"\n[bold][{now_str}][/bold] Today: [yellow]{today_count}/{self.target_daily}[/yellow] uploads | Ready in Queue: [cyan]{queued_count}[/cyan] clips")

                # 1. PRODUCTION STAGE: If queue buffer is low (< 10 clips), discover & produce new shorts
                if queued_count < 10 and today_count < self.target_daily:
                    console.print("[cyan]Queue buffer is low. Discovering fresh video from monitored creators...[/cyan]")
                    next_video = self.discovery.discover_next_unprocessed_video()

                    if next_video:
                        url = next_video["url"]
                        creator = next_video.get("creator_name", "Creator")
                        title = next_video.get("title", "Video")
                        console.print(f"[bold yellow]Ingesting fresh stream/video from {creator}:[/bold yellow] {title}")

                        try:
                            # Extract 3-5 high-virality clips from this video
                            new_clips = self.pipeline.process_video(
                                source_url=url,
                                max_clips=5,
                                reframe_mode=self.reframe_mode
                            )
                            console.print(f"[green]Produced {len(new_clips)} new viral shorts into queue.[/green]")
                        except Exception as pe:
                            logger.error(f"Failed processing video {url}: {pe}. Marking failed and continuing...")
                            self.db.add_video(source_url=url, source_type="youtube", title=title, creator_name=creator)
                    else:
                        console.print("[dim]No new videos found right now. Will check again in next cycle.[/dim]")

                # 2. PUBLISHING STAGE: Check if it's time to upload the next short
                time_since_last = time.time() - self.last_upload_time
                is_time_to_upload = (self.last_upload_time == 0.0) or (time_since_last >= self.interval_sec)

                if is_time_to_upload and today_count < self.target_daily:
                    queued_clips = self.db.get_queued_clips(limit=1)
                    if queued_clips:
                        clip = queued_clips[0]
                        console.print(f"\n[bold magenta]Publishing Short #{today_count + 1} to YouTube Shorts...[/bold magenta]")
                        console.print(f"Title: {clip['title']}")

                        res = self.uploader.upload_short(
                            video_path=clip["rendered_path"],
                            title=clip["title"],
                            description=clip["description"],
                            tags=[t.strip() for t in clip["tags"].split(",") if t.strip()],
                            visibility=self.visibility
                        )

                        if res.get("status") == "success":
                            pub_url = res.get("url", "https://youtube.com/shorts")
                            self.db.mark_clip_published(clip["id"], pub_url)
                            console.print(f"[bold green]Published Successfully![/bold green] URL: {pub_url}")
                            self.last_upload_time = time.time()
                        else:
                            self.db.mark_clip_failed(clip["id"], res.get("message", "Upload error"))

                elif today_count >= self.target_daily:
                    console.print("[bold green]Daily target of 50 uploads completed for today! Resting until midnight.[/bold green]")

                # 3. MAINTENANCE: Clean up temporary files in downloads/ and temp/
                self._cleanup_temp_files()

                # Sleep 60 seconds before next heartbeat check
                time.sleep(60)

            except KeyboardInterrupt:
                console.print("\n[yellow]AutoPilot stopped by user.[/yellow]")
                break
            except Exception as e:
                logger.error(f"AutoPilot loop error: {e}")
                time.sleep(30)

    def _cleanup_temp_files(self):
        """Cleans up raw audio and intermediate video files to save disk space."""
        downloads_dir = self.config.get("paths", {}).get("downloads", "downloads")
        if os.path.exists(downloads_dir):
            for f in os.listdir(downloads_dir):
                fp = os.path.join(downloads_dir, f)
                # Remove files older than 2 hours that are not final renders
                if os.path.isfile(fp) and (f.endswith(".mp3") or f.startswith("raw_")):
                    try:
                        if time.time() - os.path.getmtime(fp) > 7200:
                            os.remove(fp)
                    except Exception:
                        pass

if __name__ == "__main__":
    autopilot = AutoPilotService()
    autopilot.run_autonomous_loop()
