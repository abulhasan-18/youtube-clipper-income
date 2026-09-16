import argparse
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from pipeline import ClipperPipeline
from scheduler import ShortsScheduler
from storage.database import Database
from uploader.youtube_studio import YouTubeStudioUploader
from core.discovery import ContentDiscovery
from autopilot import AutoPilotService

console = Console()

def cmd_clip(args):
    pipeline = ClipperPipeline()
    pipeline.process_video(args.url, max_clips=args.max_clips, reframe_mode=args.mode)

def cmd_login(args):
    uploader = YouTubeStudioUploader(headless=False)
    uploader.login_session()

def cmd_export_session(args):
    uploader = YouTubeStudioUploader(headless=True)
    try:
        b64_str = uploader.export_session_b64()
        console.rule("[bold green]Exported YouTube Session for GitHub / Cloud Hosting")
        console.print(Panel(
            b64_str,
            title="Copy this string into your GitHub Repository Secrets as YOUTUBE_SESSION_B64",
            border_style="green"
        ))
        console.print("[yellow]Keep this string secret! It contains your authenticated YouTube Studio session.[/yellow]\n")
    except Exception as e:
        console.print(f"[red]Error exporting session: {e}[/red]")
        console.print("Run 'python cli.py login' first to authenticate on your Mac.\n")

def cmd_queue(args):
    db = Database()
    clips = db.get_queued_clips(limit=50)
    today_count = db.get_todays_upload_count()
    console.rule("[bold cyan]YouTube Shorts Queue Status")
    console.print(f"Daily uploads today: [bold yellow]{today_count}/96[/bold yellow] (1 every 15 minutes 24/7)\n")

    if not clips:
        console.print("[dim]No clips currently waiting in queue. Run 'python cli.py autopilot' or 'clip'.[/dim]\n")
        return

    table = Table(title=f"Queued Shorts ({len(clips)} ready)")
    table.add_column("ID", style="cyan")
    table.add_column("Score", style="magenta")
    table.add_column("Title", style="green")
    table.add_column("Duration", style="yellow")
    table.add_column("Status", style="blue")

    for c in clips:
        table.add_row(str(c["id"]), f"{c['virality_score']:.1f}", c["title"], f"{c['duration']:.1f}s", c["status"])

    console.print(table)
    console.print()

def cmd_creators(args):
    discovery = ContentDiscovery()
    creators = discovery.creators
    table = Table(title=f"Monitored Top Creators ({len(creators)} Creators)")
    table.add_column("#", style="cyan")
    table.add_column("Creator", style="green")
    table.add_column("Platform", style="magenta")
    table.add_column("Country", style="yellow")
    table.add_column("Search Query", style="white")

    for c in creators:
        table.add_row(str(c["id"]), c["name"], c["platform"], c["country"], c["search_query"])

    console.print(table)

def cmd_discover(args):
    console.rule("[bold cyan]Discovering Fresh Videos from 50 Creators")
    discovery = ContentDiscovery()
    video = discovery.discover_next_unprocessed_video()
    if video:
        console.print(f"\n[bold green]Found Fresh Video:[/bold green]")
        console.print(f"Creator: [yellow]{video.get('creator_name')}[/yellow]")
        console.print(f"Title:   [cyan]{video.get('title')}[/cyan]")
        console.print(f"URL:     [white]{video.get('url')}[/white]")
        console.print(f"Length:  {video.get('duration', 0.0)/60:.1f} minutes\n")
    else:
        console.print("[yellow]No unprocessed videos found right now.[/yellow]\n")

def cmd_autopilot(args):
    autopilot = AutoPilotService()
    autopilot.run_autonomous_loop()

def cmd_schedule(args):
    scheduler = ShortsScheduler()
    scheduler.run_scheduler_daemon()

def main():
    parser = argparse.ArgumentParser(description="AI Video Clipper & Autonomous 96 Shorts/Day AutoPilot")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # autopilot command (Primary 100% automated mode)
    auto_parser = subparsers.add_parser("autopilot", help="Start 100% autonomous 24/7 video clipping and daily 96-shorts uploading (every 15 mins)")
    auto_parser.set_defaults(func=cmd_autopilot)

    # clip command
    clip_parser = subparsers.add_parser("clip", help="Extract viral shorts from a specific video/stream URL")
    clip_parser.add_argument("url", help="YouTube, Twitch, or Podcast URL")
    clip_parser.add_argument("--max-clips", type=int, default=5, help="Number of viral shorts to extract (default: 5)")
    clip_parser.add_argument("--mode", choices=["face_track", "blur_bg", "split_screen", "center_crop"],
                             default="face_track", help="Reframe layout mode")
    clip_parser.set_defaults(func=cmd_clip)

    # login command
    login_parser = subparsers.add_parser("login", help="One-time login to YouTube Studio for quota-free uploads")
    login_parser.set_defaults(func=cmd_login)

    # export-session command
    export_parser = subparsers.add_parser("export-session", help="Export authenticated YouTube session for GitHub Secrets or Cloud Hosting")
    export_parser.set_defaults(func=cmd_export_session)

    # queue command
    queue_parser = subparsers.add_parser("queue", help="Inspect queued and rendered clips")
    queue_parser.set_defaults(func=cmd_queue)

    # creators command
    creators_parser = subparsers.add_parser("creators", help="List the 50 registered streamers and creators")
    creators_parser.set_defaults(func=cmd_creators)

    # discover command
    disc_parser = subparsers.add_parser("discover", help="Search and find fresh unprocessed videos from the 50 creators")
    disc_parser.set_defaults(func=cmd_discover)

    # schedule command
    sched_parser = subparsers.add_parser("schedule", help="Start the publishing scheduler only")
    sched_parser.set_defaults(func=cmd_schedule)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)

if __name__ == "__main__":
    main()
