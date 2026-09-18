import os
import sys
import time
import signal
import threading
import yaml
import logging
from datetime import datetime, date
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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
    def __init__(self, config_path: str = "config.yaml", headless: Optional[bool] = None):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        db_path = self.config.get("paths", {}).get("database", "storage/clipper.db")
        self.db = Database(db_path)
        self.discovery = ContentDiscovery(db=self.db)
        self.pipeline = ClipperPipeline(config_path=config_path)
        self.vyro_hub = VyroMonetizationHub(db=self.db)

        # Simultaneous pipeline targets & buffers
        self.target_daily = self.config.get("publishing", {}).get("target_daily_uploads", 200)
        self.cooldown_sec = self.config.get("publishing", {}).get("cooldown_seconds", 5)
        self.visibility = self.config.get("publishing", {}).get("default_visibility", "public")
        self.reframe_mode = self.config.get("video", {}).get("reframe_mode", "blur_bg")
        self.max_queue_buffer = self.config.get("autopilot", {}).get("max_queue_buffer", 10)
        self.clips_per_stream = self.config.get("autopilot", {}).get("clips_per_stream", 6)

        # Frontend upload mode (headless=False opens visible Chrome browser on screen)
        if headless is not None:
            self.headless = headless
        else:
            self.headless = self.config.get("publishing", {}).get("headless", False)

        backend = self.config.get("publishing", {}).get("upload_backend", "studio")
        if backend == "studio":
            self.uploader = YouTubeStudioUploader(headless=self.headless)
        else:
            self.uploader = YouTubeAPIUploader()

        self.multi_dispatcher = MultiPlatformDispatcher(youtube_uploader=self.uploader, db=self.db)
        self.last_upload_time = 0.0

        # Concurrency coordination
        self._stop_event = threading.Event()
        self.producer_status = "Idle / Initializing"
        self.uploader_status = "Idle / Initializing"
        self.last_produced_clip = ""
        self.last_uploaded_clip = ""

    def run_autonomous_loop(self):
        """
        Option A: Simultaneous Concurrent Pipeline
        - Producer Thread: Continuously discovers streams and renders 9:16 Shorts with Hormozi captions.
        - Uploader Thread: Simultaneously picks up each rendered clip and publishes it via visible
          frontend Chrome browser to YouTube Shorts, then deletes the local .mp4 to keep disk usage ~0 MB.
        - Main Thread: Displays a live frontend status dashboard.
        """
        console.rule("[bold cyan]🤖 Clipper AutoPilot: Simultaneous Concurrent 200 Shorts Service")
        console.print(Panel(
            f"[bold green]Monitored Creators:[/bold green] 44 Exclusive Titans (Speed, Kai, MrBeast, WWE, Sidemen, AMP, etc.)\n"
            f"[bold green]Daily Target Output:[/bold green] {self.target_daily} Viral Shorts / Day\n"
            f"[bold green]Pipeline Architecture:[/bold green] Dual-Threaded Producer + Consumer (Option A)\n"
            f"[bold green]Uploader Mode:[/bold green] {'Visible UI in Frontend (Browser Window)' if not self.headless else 'Headless Background'}\n"
            f"[bold green]Buffer Limit:[/bold green] {self.max_queue_buffer} Rendered Clips Max (< 100 MB on disk)\n"
            f"[bold green]Auto-Reframe:[/bold green] 9:16 Vertical with Hormozi Captions",
            title="AutoPilot Initialized (Concurrent Pipeline)",
            border_style="cyan"
        ))

        # Recover any stuck clips from prior runs
        self.db.reset_unrendered_uploading_clips()

        # Start Producer and Uploader worker threads
        producer_thread = threading.Thread(target=self._producer_worker, name="ProducerThread", daemon=True)
        uploader_thread = threading.Thread(target=self._uploader_worker, name="UploaderThread", daemon=True)

        producer_thread.start()
        uploader_thread.start()

        # Handle clean interruption
        def signal_handler(signum, frame):
            console.print("\n[yellow]Received stop signal. Gracefully shutting down AutoPilot threads...[/yellow]")
            self._stop_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            while not self._stop_event.is_set():
                today_count = self.db.get_todays_upload_count()
                queued_count = self.db.get_queued_count()
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                disk_mb = self._get_output_dir_size_mb()

                table = Table(show_header=True, header_style="bold cyan", border_style="dim")
                table.add_column("Metric / Component", style="bold")
                table.add_column("Current Live Status", style="green")

                table.add_row("Timestamp", now_str)
                table.add_row("Today's Uploads", f"[bold yellow]{today_count} / {self.target_daily}[/bold yellow] ({round((today_count/max(1, self.target_daily))*100, 1)}%)")
                table.add_row("Queue Buffer", f"[cyan]{queued_count} / {self.max_queue_buffer}[/cyan] clips ready")
                table.add_row("Output Folder Disk Size", f"[magenta]{disk_mb} MB[/magenta] (Auto-purged after upload)")
                table.add_row("Producer (Clipping)", self.producer_status)
                table.add_row("Uploader (Frontend UI)", self.uploader_status)
                if self.last_uploaded_clip:
                    table.add_row("Last Uploaded", f"[bold white]{self.last_uploaded_clip}[/bold white]")

                console.clear()
                console.rule("[bold cyan]🤖 YouTube Shorts 200/Day Concurrent AutoPilot")
                console.print(table)
                console.print("[dim]Press Ctrl+C to stop. Producer & Frontend Uploader running concurrently.[/dim]")

                self._stop_event.wait(5.0)

        except KeyboardInterrupt:
            self._stop_event.set()

        console.print("\n[bold yellow]Stopping threads...[/bold yellow]")
        producer_thread.join(timeout=3.0)
        uploader_thread.join(timeout=3.0)
        console.print("[bold green]AutoPilot stopped cleanly.[/bold green]")

    def _producer_worker(self):
        """Producer Thread: continuously discovers fresh creator streams and renders clips into queue."""
        logger.info("Producer thread started.")
        while not self._stop_event.is_set():
            try:
                today_count = self.db.get_todays_upload_count()
                queued_count = self.db.get_queued_count()

                # Check if daily target already achieved
                if today_count >= self.target_daily:
                    self.producer_status = f"Daily goal of {self.target_daily} reached! Resting."
                    self._stop_event.wait(60.0)
                    continue

                # If queue already has enough clips or buffer is full, wait for uploader to consume
                if queued_count >= self.max_queue_buffer:
                    self.producer_status = f"Buffer full ({queued_count}/{self.max_queue_buffer}). Waiting for uploader..."
                    self._stop_event.wait(10.0)
                    continue

                if (today_count + queued_count) >= self.target_daily:
                    self.producer_status = f"Sufficient clips queued ({queued_count}) to reach daily target. Waiting..."
                    self._stop_event.wait(15.0)
                    continue

                # Discover next fresh stream from 44 creators
                self.producer_status = "Scanning 44 creators for fresh streams..."
                next_video = self.discovery.discover_next_unprocessed_video()

                if next_video:
                    url = next_video["url"]
                    creator = next_video.get("creator_name", "Creator")
                    title = next_video.get("title", "Video")
                    self.producer_status = f"Ingesting {creator}: {title[:35]}..."
                    logger.info(f"[Producer] Ingesting stream from {creator}: {title}")

                    try:
                        new_clips = self.pipeline.process_video(
                            source_url=url,
                            max_clips=self.clips_per_stream,
                            reframe_mode=self.reframe_mode
                        )
                        if new_clips:
                            self.last_produced_clip = new_clips[-1].get("title", "")
                            self.producer_status = f"Produced {len(new_clips)} shorts from {creator}"
                            logger.info(f"[Producer] Successfully rendered {len(new_clips)} clips into queue.")
                        else:
                            self.producer_status = f"No viral hooks found in {creator} video. Moving on."
                    except Exception as pe:
                        logger.error(f"[Producer] Failed processing video {url}: {pe}")
                        self.db.add_video(source_url=url, source_type="youtube", title=title, creator_name=creator)
                        self.producer_status = f"Error processing {creator} video: {str(pe)[:30]}"
                else:
                    self.producer_status = "No new stream found across 44 creators. Retrying in 15s..."
                    self._stop_event.wait(15.0)

                # Clean up temp audio and downloaded parts
                self._cleanup_temp_files()
                self._stop_event.wait(3.0)

            except Exception as e:
                logger.error(f"[Producer] Worker error: {e}")
                self.producer_status = f"Error: {str(e)[:40]}"
                self._stop_event.wait(10.0)

        logger.info("Producer thread exiting.")

    def _uploader_worker(self):
        """Uploader Thread: claims rendered clips and publishes them via visible Chrome in the frontend."""
        logger.info("Uploader thread started (Frontend mode).")
        while not self._stop_event.is_set():
            try:
                today_count = self.db.get_todays_upload_count()

                if today_count >= self.target_daily:
                    self.uploader_status = f"Daily goal of {self.target_daily} uploads completed! Resting."
                    self._stop_event.wait(60.0)
                    continue

                # Atomically claim the next rendered clip
                clip = self.db.claim_next_queued_clip()
                if not clip:
                    self.uploader_status = "Waiting for clips from Producer thread..."
                    self._stop_event.wait(5.0)
                    continue

                rendered_path = clip.get("rendered_path")
                if not rendered_path or not os.path.exists(rendered_path):
                    logger.warning(f"[Uploader] Clip file missing ({rendered_path}). Marking discarded.")
                    with self.db._get_conn() as conn:
                        conn.execute("UPDATE clips SET status = 'discarded' WHERE id = ?", (clip["id"],))
                        conn.commit()
                    continue

                # Respect cooldown between uploads
                time_since_last = time.time() - self.last_upload_time
                if (self.last_upload_time > 0.0) and (time_since_last < self.cooldown_sec):
                    wait_sec = self.cooldown_sec - time_since_last
                    self.uploader_status = f"Cooldown buffer ({wait_sec:.1f}s remaining)..."
                    self._stop_event.wait(wait_sec)

                title = clip.get("title", "Viral Short")
                self.uploader_status = f"Opening frontend Chrome for Short #{today_count + 1}: '{title[:30]}...'"
                logger.info(f"[Uploader] Publishing Short #{today_count + 1}/{self.target_daily}: {title}")

                # Publish to YouTube Studio in the frontend browser
                dispatch_res = self.multi_dispatcher.publish_clip(
                    clip=clip,
                    visibility=self.visibility,
                    platforms=["youtube", "tiktok", "instagram"]
                )

                yt_res = dispatch_res.get("youtube", {})
                if yt_res.get("status") == "success":
                    pub_url = yt_res.get("url", "https://youtube.com/shorts")
                    self.last_upload_time = time.time()
                    self.last_uploaded_clip = f"#{today_count + 1} {title[:40]} -> {pub_url}"
                    self.uploader_status = f"Published #{today_count + 1}! URL: {pub_url}"
                    logger.info(f"[Uploader] Successfully uploaded Short #{today_count + 1}! URL: {pub_url}")

                    # Append to tracking files
                    self._record_uploaded_url(title, pub_url)

                    # Delete local MP4 file immediately to ensure near 0 MB disk accumulation
                    if os.path.exists(rendered_path):
                        try:
                            os.remove(rendered_path)
                            logger.info(f"[Uploader] Deleted local file {rendered_path} (Disk space preserved).")
                        except Exception as de:
                            logger.warning(f"[Uploader] Could not remove {rendered_path}: {de}")

                    # Update Vyro payouts manifest
                    try:
                        self.vyro_hub.export_unsubmitted_submissions()
                    except Exception:
                        pass

                else:
                    err_msg = yt_res.get("message", yt_res.get("error", "Upload error"))
                    logger.error(f"[Uploader] Upload failed for clip {clip['id']}: {err_msg}")
                    self.db.mark_clip_failed(clip["id"], str(err_msg))
                    self.uploader_status = f"Upload failed: {str(err_msg)[:40]}"
                    self._stop_event.wait(5.0)

                # Cooldown before checking next clip
                self._stop_event.wait(self.cooldown_sec)

            except Exception as e:
                logger.error(f"[Uploader] Worker error: {e}")
                self.uploader_status = f"Error: {str(e)[:40]}"
                self._stop_event.wait(10.0)

        logger.info("Uploader thread exiting.")

    def _get_output_dir_size_mb(self) -> float:
        """Returns the total megabytes of files currently inside output/."""
        output_dir = self.config.get("paths", {}).get("output", "output")
        if not os.path.exists(output_dir):
            return 0.0
        try:
            total_bytes = sum(
                os.path.getsize(os.path.join(output_dir, f))
                for f in os.listdir(output_dir)
                if os.path.isfile(os.path.join(output_dir, f))
            )
            return round(total_bytes / (1024 * 1024), 2)
        except Exception:
            return 0.0

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
                            if time.time() - os.path.getmtime(fp) > 900: # 15 mins
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
    # Support --headless or --frontend flag from command line
    headless_flag = None
    if "--frontend" in sys.argv or "--visible" in sys.argv:
        headless_flag = False
    elif "--headless" in sys.argv:
        headless_flag = True

    autopilot = AutoPilotService(headless=headless_flag)
    autopilot.run_autonomous_loop()
