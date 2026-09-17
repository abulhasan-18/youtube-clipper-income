import os
import csv
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.table import Table

from storage.database import Database

logger = logging.getLogger("Clipper.VyroMonetization")
console = Console()

# Active Vyro Campaign Catalog & Top-Paying Multi-Platform Benchmark Rates (CPM per 1,000 views)
VYRO_CAMPAIGNS = {
    "mrbeast": {
        "campaign_id": "vyro_mrbeast_viral",
        "name": "MrBeast Global Clipping Program",
        "cpm_usd": 2.50, # $2.50 per 1,000 views
        "keywords": ["mrbeast", "beast", "challenge", "giveaway", "money"]
    },
    "mark_rober": {
        "campaign_id": "vyro_markrober_stem",
        "name": "Mark Rober Engineering & Glitch",
        "cpm_usd": 2.20,
        "keywords": ["mark rober", "glitterbomb", "science", "experiment"]
    },
    "amp_creators": {
        "campaign_id": "vyro_amp_creators",
        "name": "AMP Members (Kai Cenat, Duke Dennis, Fanum)",
        "cpm_usd": 1.85,
        "keywords": ["kai", "cenat", "duke", "dennis", "fanum", "agent", "amp", "rizz"]
    },
    "sidemen": {
        "campaign_id": "vyro_sidemen_sunday",
        "name": "Sidemen & All Members Official",
        "cpm_usd": 1.75,
        "keywords": ["sidemen", "ksi", "w2s", "miniminter", "zerkaa", "tbjzl", "behzinga", "vikkstar"]
    },
    "streamer_highlights": {
        "campaign_id": "vyro_streamer_highlights",
        "name": "Top Streamers & Creators Syndicate",
        "cpm_usd": 2.10,
        "keywords": ["speed", "ishowspeed", "chunkz", "filly", "beta squad", "podcast", "stream", "funny", "rage"]
    },
    "general_viral": {
        "campaign_id": "vyro_viral_general",
        "name": "General Viral & High-Retention Shorts",
        "cpm_usd": 1.20,
        "keywords": []
    }
}

PLATFORM_BENCHMARKS = {
    "vyro_cpm": 2.00,        # Average Vyro campaign payout ($2.00 / 1k views)
    "tiktok_rpm": 0.85,      # TikTok Creator Rewards ($0.85 / 1k qualified views)
    "instagram_rpm": 0.50,   # Instagram Reels bonus/brand ($0.50 / 1k views)
    "youtube_shorts_rpm": 0.12 # YouTube Shorts partner rev ($0.12 / 1k views)
}

class VyroMonetizationHub:
    def __init__(self, db: Optional[Database] = None, output_dir: str = "output"):
        self.db = db or Database()
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.vyro_api_key = os.getenv("VYRO_API_KEY", "")
        self.vyro_session = os.getenv("VYRO_SESSION_COOKIE", "")

    def match_best_campaign(self, title: str, creator: str = "", tags: str = "") -> Dict[str, Any]:
        """
        Determines the highest-paying Vyro campaign for a given clip ('whoever pays the most').
        """
        text = f"{title} {creator} {tags}".lower()
        best_match = VYRO_CAMPAIGNS["general_viral"]
        highest_cpm = best_match["cpm_usd"]

        for key, camp in VYRO_CAMPAIGNS.items():
            if camp["keywords"]:
                for kw in camp["keywords"]:
                    if kw in text:
                        if camp["cpm_usd"] > highest_cpm:
                            highest_cpm = camp["cpm_usd"]
                            best_match = camp
                        break

        return best_match

    def export_unsubmitted_submissions(self) -> List[Dict[str, Any]]:
        """
        Gathers all published clips across YouTube Shorts, TikTok, and Instagram,
        matches each to its highest-paying campaign, and exports them to JSON & CSV.
        """
        clips = self.db.get_unsubmitted_vyro_clips()
        if not clips:
            logger.info("No unsubmitted clips found for Vyro.")
            return []

        submissions = []
        for clip in clips:
            c_id = clip["id"]
            title = clip.get("title", "")
            creator = clip.get("creator_name", "")
            tags = clip.get("tags", "")

            # Prioritize primary live URL (YouTube, TikTok, or Instagram)
            primary_url = clip.get("youtube_url") or clip.get("tiktok_url") or clip.get("instagram_url") or ""
            if not primary_url:
                continue

            camp = self.match_best_campaign(title, creator, tags)
            # Estimate potential earnings based on benchmark viral views (e.g. 50k views)
            benchmark_views = 50000
            est_payout = (benchmark_views / 1000.0) * camp["cpm_usd"]

            item = {
                "clip_id": c_id,
                "title": title,
                "creator": creator,
                "platform": "YouTube Shorts" if "youtube.com" in primary_url or "youtu.be" in primary_url else "TikTok",
                "post_url": primary_url,
                "all_urls": {
                    "youtube": clip.get("youtube_url"),
                    "tiktok": clip.get("tiktok_url"),
                    "instagram": clip.get("instagram_url")
                },
                "matched_campaign_id": camp["campaign_id"],
                "campaign_name": camp["name"],
                "cpm_rate_usd": camp["cpm_usd"],
                "est_earnings_at_50k_views": round(est_payout, 2),
                "staged_at": datetime.now().isoformat()
            }
            submissions.append(item)

        # 1. Save to JSON
        json_path = os.path.join(self.output_dir, "vyro_submissions.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(submissions, f, indent=2)

        # 2. Save to CSV
        csv_path = os.path.join(self.output_dir, "vyro_submissions.csv")
        fieldnames = ["clip_id", "title", "creator", "platform", "post_url", "matched_campaign_id", "campaign_name", "cpm_rate_usd", "est_earnings_at_50k_views"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for s in submissions:
                writer.writerow(s)

        logger.info(f"Exported {len(submissions)} Vyro submissions to {json_path} and {csv_path}")
        return submissions

    def print_monetization_dashboard(self):
        """Displays rich console payout dashboard for clippers."""
        submissions = self.export_unsubmitted_submissions()
        all_monetized = self.db.get_all_monetized_clips()

        table = Table(title="💰 Multi-Platform Vyro Monetization Hub & Payout Optimizer")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="bold white")
        table.add_column("Primary URL", style="blue")
        table.add_column("Vyro Campaign", style="yellow")
        table.add_column("CPM Rate", style="green")
        table.add_column("Est. Earnings (50k views)", style="magenta")

        for s in submissions:
            table.add_row(
                str(s["clip_id"]),
                s["title"][:38] + "..." if len(s["title"]) > 40 else s["title"],
                s["post_url"],
                s["campaign_name"][:25],
                f"${s['cpm_rate_usd']:.2f}/k",
                f"${s['est_earnings_at_50k_views']:.2f}"
            )

        console.print(table)
        console.print(f"\n[green]✓ Ready-to-submit manifests generated:[/green]")
        console.print(f"  • JSON: [cyan]{os.path.join(self.output_dir, 'vyro_submissions.json')}[/cyan]")
        console.print(f"  • CSV:  [cyan]{os.path.join(self.output_dir, 'vyro_submissions.csv')}[/cyan]")
        console.print(f"[dim]Paste URLs directly into your Vyro (vyro.com) dashboard to collect CPM payouts![/dim]\n")

if __name__ == "__main__":
    hub = VyroMonetizationHub()
    hub.print_monetization_dashboard()
