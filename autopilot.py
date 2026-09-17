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
from uploader.multi_platform import MultiPlatformDispatcher
from core.vyro_monetization import VyroMonetizationHub

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
        self.vyro_hub = VyroMonetizationHub(db=self.db)

        # Publishing settings: Instant upload as soon as video is ready
        self.target_daily = self.config.get("publishing", {}).get("target_daily_uploads", 96)
        self.cooldown_sec = self.config.get("publishing", {}).get("cooldown_seconds", 10)
        self.visibility = self.config.get("publishing", {}).get("default_visibility", "public")
        self.reframe_mode = self.config.get("video", {}).get("reframe_mode", "face_track")

        backend = self.config.get("publishing", {}).get("upload_backend", "studio")
        headless_mode = self.config.get("publishing", {}).get("headless", False)
        if backend == "studio":
            self.uploader = YouTubeStudioUploader(headless=headless_mode)
        else:
            self.uploader = YouTubeAPIUploader()

        self.multi_dispatcher = MultiPlatformDispatcher(youtube_uploader=self.uploader, db=self.db)
        self.last_upload_time = 0.0

    def run_autonomous_loop(self):
        """
        100% Autonomous 24/7 Loop:
        - Instant Upload: As soon as a clip is ready, immediately upload to YouTube Studio
        - Instant Repeat: Once uploaded, logged, and cleaned up, immediately process next clip/video
        """
        console.rule("[bold cyan]🤖 Clipper AutoPilot: Instant Upload 24/7 Service")
        console.print(Panel(
            f"[bold green]Monitored Creators:[/bold green] 50 Top Streamers (IShowSpeed, Kai Cenat, Sidemen, AMP, etc.)\n"
            f"[bold green]Target Output:[/bold green] {self.target_daily} Viral Shorts / Day\n"
            f"[bold green]Upload Cadence:[/bold green] Instant (as soon as video is ready)\n"
            f"[bold green]Auto-Reframe:[/bold green] 9:16 Vertical with Centered 16:9 Video & Hormozi Captions",
            title="AutoPilot Initialized (Instant Upload Mode)",
            border_style="cyan"
        ))

        while True:
            try:
                today_count = self.db.get_todays_upload_count()
                queued_count = self.db.get_queued_count()
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                console.print(f"\n[bold][{now_str}][/bold] Today: [yellow]{today_count}/{self.target_daily}[/yellow] uploads | Ready in Queue: [cyan]{queued_count}[/cyan] clips")

                # 1. PUBLISHING STAGE: If any clip is ready in queue, upload immediately to YouTube Studio!
                time_since_last = time.time() - self.last_upload_time
                can_upload = (self.last_upload_time == 0.0) or (time_since_last >= self.cooldown_sec)

                if can_upload and queued_count > 0 and today_count < self.target_daily:
                    queued_clips = self.db.get_queued_clips(limit=1)
                    if queued_clips:
                        clip = queued_clips[0]
                        console.print(f"\n[bold magenta]⚡ Instant Publishing Short #{today_count + 1}/{self.target_daily} to YouTube Studio...[/bold magenta]")
                        console.print(f"Title: {clip['title']}")

                        dispatch_res = self.multi_dispatcher.publish_clip(
                            clip=clip,
                            visibility=self.visibility,
                            platforms=["youtube", "tiktok", "instagram"]
                        )

                        yt_res = dispatch_res.get("youtube", {})
                        if yt_res.get("status") == "success":
                            pub_url = yt_res.get("url", "https://youtube.com/shorts")
                            console.print(f"[bold green]Published Successfully![/bold green] URL: {pub_url}")
                            self.last_upload_time = time.time()

                            # Append URL to youtube_uploaded_urls.txt
                            self._record_uploaded_url(clip["title"], pub_url)

                            # Delete local video file immediately - we don't need it on machine anymore
                            rendered_file = clip.get("rendered_path")
                            if rendered_file and os.path.exists(rendered_file):
                                try:
                                    os.remove(rendered_file)
                                    logger.info(f"Deleted local video {rendered_file} to free disk space.")
                                    console.print(f"[dim]Deleted local video file {rendered_file}.[/dim]")
                                except Exception as de:
                                    logger.warning(f"Could not delete {rendered_file}: {de}")

                            # Automatically update Vyro payout submission manifests
                            try:
                                self.vyro_hub.export_unsubmitted_submissions()
                            except Exception:
                                pass
                        else:
                            self.db.mark_clip_failed(clip["id"], yt_res.get("message", "Upload error"))

                        # Short 3s cooldown, then immediately loop to upload next ready clip or produce!
                        time.sleep(3)
                        continue

                elif today_count >= self.target_daily:
                    console.print("[bold green]Daily target of uploads completed for today! Resting until midnight.[/bold green]")

                # 2. PRODUCTION STAGE: If ready queue buffer is low (< 4 clips), discover & produce new shorts immediately!
                queued_count = self.db.get_queued_count()
                if queued_count < 4 and today_count < self.target_daily:
                    console.print("[cyan]Queue buffer is low. Discovering fresh video from monitored creators...[/cyan]")
                    next_video = self.discovery.discover_next_unprocessed_video()

                    if next_video:
                        url = next_video["url"]
                        creator = next_video.get("creator_name", "Creator")
                        title = next_video.get("title", "Video")
                        console.print(f"[bold yellow]Ingesting fresh stream/video from {creator}:[/bold yellow] {title}")

                        try:
                            # Extract 4 high-virality clips from this video
                            new_clips = self.pipeline.process_video(
                                source_url=url,
                                max_clips=4,
                                reframe_mode=self.reframe_mode
                            )
                            console.print(f"[green]Produced {len(new_clips)} new viral shorts into queue.[/green]")
                            # Immediately loop back to upload the newly rendered clips!
                            continue
                        except Exception as pe:
                            logger.error(f"Failed processing video {url}: {pe}. Marking failed and continuing...")
                            self.db.add_video(source_url=url, source_type="youtube", title=title, creator_name=creator)
                    else:
                        console.print("[dim]No new videos found right now. Will check again shortly.[/dim]")

                # 3. MAINTENANCE: Clean up temporary files in downloads/ and temp/
                self._cleanup_temp_files()

                # Short 10-second sleep before checking queue / cooldown
                time.sleep(10)

            except KeyboardInterrupt:
                console.print("\n[yellow]AutoPilot stopped by user.[/yellow]")
                break
            except Exception as e:
                logger.error(f"AutoPilot loop error: {e}")
                time.sleep(30)

    def _record_uploaded_url(self, title: str, pub_url: str):
        """Appends the uploaded video URL to youtube_uploaded_urls.txt and youtube_uploaded_url.txt."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n[{timestamp}] {title}\nURL: {pub_url}\n"
        for fname in ["youtube_uploaded_urls.txt", "youtube_uploaded_url.txt"]:
            try:
                with open(fname, "a", encoding="utf-8") as f:
                    f.write(entry)
                logger.info(f"Recorded URL to {fname}: {pub_url}")
            except Exception as e:
                logger.warning(f"Failed writing to {fname}: {e}")

    def _cleanup_temp_files(self):
        """Cleans up raw audio, temporary downloads, and already published videos to save disk space."""
        downloads_dir = self.config.get("paths", {}).get("downloads", "downloads")
        output_dir = self.config.get("paths", {}).get("output", "output")
        temp_dir = self.config.get("paths", {}).get("temp", "temp")

        for folder in [downloads_dir, temp_dir]:
            if os.path.exists(folder):
                for f in os.listdir(folder):
                    fp = os.path.join(folder, f)
                    if os.path.isfile(fp) and (f.endswith(".mp3") or f.startswith("raw_") or f.endswith(".part") or f.endswith(".webm")):
                        try:
                            if time.time() - os.path.getmtime(fp) > 1800: # 30 mins
                                os.remove(fp)
                        except Exception:
                            pass

        # Also purge any already published or discarded videos from output
        if os.path.exists(output_dir):
            for f in os.listdir(output_dir):
                if f.endswith(".mp4"):
                    fp = os.path.join(output_dir, f)
                    try:
                        with self.db._get_conn() as conn:
                            c = conn.cursor()
                            c.execute("SELECT status FROM clips WHERE rendered_path = ?", (fp,))
                            row = c.fetchone()
                            if row and row["status"] in ["published", "discarded"]:
                                os.remove(fp)
                                logger.info(f"Deleted previously published/discarded video: {fp}")
                    except Exception:
                        pass

if __name__ == "__main__":
    autopilot = AutoPilotService()
    autopilot.run_autonomous_loop()
