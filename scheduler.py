import time
import yaml
import logging
from datetime import datetime
from rich.console import Console
from storage.database import Database
from uploader.youtube_studio import YouTubeStudioUploader
from uploader.youtube_api import YouTubeAPIUploader

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Clipper.Scheduler")

class ShortsScheduler:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        db_path = self.config.get("paths", {}).get("database", "storage/clipper.db")
        self.db = Database(db_path)
        self.target_daily = self.config.get("publishing", {}).get("target_daily_uploads", 96)
        self.interval_sec = self.config.get("publishing", {}).get("interval_minutes", 15) * 60
        self.visibility = self.config.get("publishing", {}).get("default_visibility", "public")

        backend = self.config.get("publishing", {}).get("upload_backend", "studio")
        if backend == "studio":
            self.uploader = YouTubeStudioUploader(headless=True)
        else:
            self.uploader = YouTubeAPIUploader()

    def run_scheduler_daemon(self):
        """
        Main 24/7 background scheduler loop.
        Drip-feeds clips to achieve up to 96 uploads per day (every 15 minutes).
        """
        console.rule("[bold green]YouTube Shorts Publishing Daemon (96 Clips/Day)")
        console.print(f"Target: [cyan]{self.target_daily} uploads/day (4/hr)[/cyan] | Interval: [cyan]{self.interval_sec/60:.1f} minutes[/cyan]\n")

        while True:
            try:
                today_count = self.db.get_todays_upload_count()
                console.print(f"[{datetime.now().strftime('%H:%M:%S')}] Daily uploads so far: [bold yellow]{today_count}/{self.target_daily}[/bold yellow]")

                if today_count >= self.target_daily:
                    console.print("[green]Daily target of 96 uploads reached! Sleeping until midnight...[/green]")
                    time.sleep(3600)
                    continue

                # Get next queued clip
                queued = self.db.get_queued_clips(limit=1)
                if not queued:
                    console.print("[dim]No rendered clips in queue. Waiting 5 minutes for new clips...[/dim]")
                    time.sleep(300)
                    continue

                clip = queued[0]
                clip_id = clip["id"]
                title = clip["title"]
                desc = clip["description"]
                tags = [t.strip() for t in clip["tags"].split(",") if t.strip()]
                rendered_path = clip["rendered_path"]

                console.print(f"\n[bold magenta]Publishing Short #{today_count + 1}/96:[/bold magenta] {title}")
                console.print(f"File: {rendered_path}")

                res = self.uploader.upload_short(
                    video_path=rendered_path,
                    title=title,
                    description=desc,
                    tags=tags,
                    visibility=self.visibility
                )

                if res.get("status") == "success":
                    pub_url = res.get("url", "https://youtube.com/shorts")
                    self.db.mark_clip_published(clip_id, pub_url)
                    console.print(f"[bold green]Published successfully![/bold green] URL: {pub_url}")
                else:
                    self.db.mark_clip_failed(clip_id, res.get("message", "Upload error"))

                console.print(f"Next upload in {self.interval_sec/60:.1f} minutes...\n")
                time.sleep(self.interval_sec)

            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    scheduler = ShortsScheduler()
    scheduler.run_scheduler_daemon()
