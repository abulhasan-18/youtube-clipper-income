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

        # Publishing & batch clipping settings
        self.batch_target = self.config.get("autopilot", {}).get("batch_target", 200)
        self.target_daily = self.config.get("publishing", {}).get("target_daily_uploads", 200)
        self.cooldown_sec = self.config.get("publishing", {}).get("cooldown_seconds", 5)
        self.visibility = self.config.get("publishing", {}).get("default_visibility", "public")
        self.reframe_mode = self.config.get("video", {}).get("reframe_mode", "face_track")

        backend = self.config.get("publishing", {}).get("upload_backend", "studio")
        headless_mode = self.config.get("publishing", {}).get("headless", True)
        if backend == "studio":
            self.uploader = YouTubeStudioUploader(headless=headless_mode)
        else:
            self.uploader = YouTubeAPIUploader()

        self.multi_dispatcher = MultiPlatformDispatcher(youtube_uploader=self.uploader, db=self.db)
        self.last_upload_time = 0.0

        # State machine: "clipping" (produce 200 clips first) -> "uploading" (upload 1-by-1 once clipping is done)
        current_queue = self.db.get_queued_count()
        self.mode = "uploading" if current_queue >= self.batch_target else "clipping"

    def run_autonomous_loop(self):
        """
        100% Autonomous 24/7 Loop:
        1. Batch Clipping Stage: Clip & render 200 viral shorts into queue first
        2. Sequential Uploading Stage: Once 200 are ready, upload one-by-one to YouTube Studio
        """
        console.rule("[bold cyan]🤖 Clipper AutoPilot: 200 Videos Batch Clipping & Upload Service")
        console.print(Panel(
            f"[bold green]Monitored Creators:[/bold green] 44 Exclusive Top Creators (IShowSpeed, Kai Cenat, Sidemen, AMP, WWE, etc.)\n"
            f"[bold green]Daily Target Output:[/bold green] {self.target_daily} Viral Shorts / Day\n"
            f"[bold green]Batch Target:[/bold green] Clip {self.batch_target} videos first, then upload 1-by-1\n"
            f"[bold green]Current Mode:[/bold green] {self.mode.upper()}\n"
            f"[bold green]Auto-Reframe:[/bold green] 9:16 Vertical with Centered Video & Hormozi Captions",
            title="AutoPilot Initialized (200 Shorts / Day)",
            border_style="cyan"
        ))

        while True:
            try:
                today_count = self.db.get_todays_upload_count()
                queued_count = self.db.get_queued_count()
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # State machine transition:
                if self.mode == "clipping" and queued_count >= self.batch_target:
                    console.print(f"\n[bold green]🎉 Batch clipping target reached ({queued_count}/{self.batch_target} clips)! Switching to sequential upload mode...[/bold green]")
                    self.mode = "uploading"
                elif self.mode == "uploading" and queued_count == 0:
                    console.print("\n[bold green]All queued clips uploaded! Switching back to batch clipping mode...[/bold green]")
                    self.mode = "clipping"

                console.print(f"\n[bold][{now_str}][/bold] Mode: [bold magenta]{self.mode.upper()}[/bold magenta] | Today Uploaded: [yellow]{today_count}/{self.target_daily}[/yellow] | Ready in Queue: [cyan]{queued_count}/{self.batch_target}[/cyan] clips")

                # =========================================================================
                # STAGE 1: BATCH CLIPPING MODE (Clip 200 videos before uploading)
                # =========================================================================
                if self.mode == "clipping":
                    if queued_count < self.batch_target:
                        console.print(f"[cyan]Clipping in progress ({queued_count}/{self.batch_target} ready). Finding fresh stream from exclusive creators...[/cyan]")
                        next_video = self.discovery.discover_next_unprocessed_video()

                        if next_video:
                            url = next_video["url"]
                            creator = next_video.get("creator_name", "Creator")
                            title = next_video.get("title", "Video")
                            console.print(f"[bold yellow]Ingesting stream from {creator}:[/bold yellow] {title}")

                            try:
                                # Extract 6 high-virality clips per stream
                                new_clips = self.pipeline.process_video(
                                    source_url=url,
                                    max_clips=6,
                                    reframe_mode=self.reframe_mode
                                )
                                console.print(f"[green]Produced {len(new_clips)} new viral shorts! (Queue: {self.db.get_queued_count()}/{self.batch_target})[/green]")
                            except Exception as pe:
                                logger.error(f"Failed processing video {url}: {pe}. Marking failed and continuing...")
                                self.db.add_video(source_url=url, source_type="youtube", title=title, creator_name=creator)
                        else:
                            console.print("[dim]No unprocessed videos found right now. Will scan again in 15s.[/dim]")
                            time.sleep(15)

                        # Clean up temp audio and downloaded source files to conserve disk space
                        self._cleanup_temp_files()
                        time.sleep(2)
                        continue

                # =========================================================================
                # STAGE 2: SEQUENTIAL UPLOADING MODE (Upload 1-by-1 once clipping is done)
                # =========================================================================
                elif self.mode == "uploading":
                    if today_count >= self.target_daily:
                        console.print(f"[bold green]Daily target of {self.target_daily} uploads completed for today! Resting until midnight.[/bold green]")
                        time.sleep(60)
                        continue

                    time_since_last = time.time() - self.last_upload_time
                    can_upload = (self.last_upload_time == 0.0) or (time_since_last >= self.cooldown_sec)

                    if can_upload and queued_count > 0:
                        queued_clips = self.db.get_queued_clips(limit=1)
                        if queued_clips:
                            clip = queued_clips[0]
                            console.print(f"\n[bold magenta]⚡ Uploading Short #{today_count + 1}/{self.target_daily} (Queue remaining: {queued_count})...[/bold magenta]")
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

                                # Append URL to upload logs
                                self._record_uploaded_url(clip["title"], pub_url)

                                # Delete local video file immediately to free disk space
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

                            # Brief 5s cooldown between consecutive uploads
                            time.sleep(self.cooldown_sec)
                            continue

                # Maintenance
                self._cleanup_temp_files()
                time.sleep(5)

            except KeyboardInterrupt:
                console.print("\n[yellow]AutoPilot stopped by user.[/yellow]")
                break
            except Exception as e:
                logger.error(f"AutoPilot loop error: {e}")
                time.sleep(15)

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
