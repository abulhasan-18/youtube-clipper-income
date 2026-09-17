import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime, date
from typing import List, Dict, Any, Optional

DB_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage", "clipper.db")

class Database:
    def __init__(self, db_path: str = DB_DEFAULT_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url TEXT UNIQUE,
                source_type TEXT,
                creator_name TEXT,
                title TEXT,
                duration REAL,
                transcript_text TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS clips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER,
                start_time REAL,
                end_time REAL,
                duration REAL,
                virality_score REAL,
                hook_text TEXT,
                title TEXT,
                description TEXT,
                tags TEXT,
                rendered_path TEXT,
                status TEXT DEFAULT 'pending', -- pending, rendered, queued, uploading, published, failed
                scheduled_time TIMESTAMP,
                youtube_url TEXT,
                published_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(video_id) REFERENCES videos(id)
            )
            """)

            # Try to add creator_name if existing table doesn't have it
            try:
                cursor.execute("ALTER TABLE videos ADD COLUMN creator_name TEXT")
            except sqlite3.OperationalError:
                pass

            # Multi-platform & Vyro monetization columns
            for col, col_type in [
                ("edit_style", "TEXT DEFAULT 'auto'"),
                ("tiktok_url", "TEXT"),
                ("instagram_url", "TEXT"),
                ("vyro_campaign_id", "TEXT"),
                ("vyro_submitted", "INTEGER DEFAULT 0"),
                ("estimated_earnings", "REAL DEFAULT 0.0")
            ]:
                try:
                    cursor.execute(f"ALTER TABLE clips ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass

            conn.commit()

    def is_video_processed(self, source_url: str) -> bool:
        """Returns True if this video has already been ingested or clipped."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM videos WHERE source_url = ?", (source_url,))
            return cursor.fetchone() is not None

    def add_video(self, source_url: str, source_type: str, title: str = "",
                  duration: float = 0.0, creator_name: str = "") -> int:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO videos (source_url, source_type, creator_name, title, duration, status)
                VALUES (?, ?, ?, ?, ?, 'downloaded')
                ON CONFLICT(source_url) DO UPDATE SET title=excluded.title, creator_name=excluded.creator_name
            """, (source_url, source_type, creator_name, title, duration))
            conn.commit()
            if cursor.lastrowid:
                return cursor.lastrowid
            cursor.execute("SELECT id FROM videos WHERE source_url = ?", (source_url,))
            row = cursor.fetchone()
            return row["id"] if row else 0

    def update_video_transcript(self, video_id: int, transcript_text: str):
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE videos SET transcript_text = ?, status = 'transcribed' WHERE id = ?
            """, (transcript_text, video_id))
            conn.commit()

    def add_clip(self, video_id: int, start_time: float, end_time: float, virality_score: float,
                 hook_text: str, title: str, description: str, tags: str, edit_style: str = "auto") -> int:
        duration = end_time - start_time
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO clips (video_id, start_time, end_time, duration, virality_score,
                                   hook_text, title, description, tags, edit_style, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (video_id, start_time, end_time, duration, virality_score, hook_text, title, description, tags, edit_style))
            conn.commit()
            return cursor.lastrowid

    def update_clip_rendered(self, clip_id: int, rendered_path: str):
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE clips SET rendered_path = ?, status = 'rendered' WHERE id = ?
            """, (rendered_path, clip_id))
            conn.commit()

    def mark_clip_published(self, clip_id: int, youtube_url: str):
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE clips SET status = 'published', youtube_url = ?, published_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (youtube_url, clip_id))
            conn.commit()

    def update_clip_multiplatform(self, clip_id: int, platform: str, url: str):
        """Updates live published URL for tiktok or instagram."""
        col = f"{platform.lower()}_url"
        if col in ["tiktok_url", "instagram_url", "youtube_url"]:
            with self._get_conn() as conn:
                conn.execute(f"UPDATE clips SET {col} = ? WHERE id = ?", (url, clip_id))
                conn.commit()

    def mark_vyro_submitted(self, clip_id: int, campaign_id: str = "", estimated_earnings: float = 0.0):
        """Records that this clip has been submitted to a Vyro payout campaign."""
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE clips SET vyro_submitted = 1, vyro_campaign_id = ?, estimated_earnings = ?
                WHERE id = ?
            """, (campaign_id, estimated_earnings, clip_id))
            conn.commit()

    def get_unsubmitted_vyro_clips(self) -> List[Dict[str, Any]]:
        """Returns all published clips that have not yet been submitted to Vyro."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, v.title as video_title, v.creator_name
                FROM clips c
                JOIN videos v ON c.video_id = v.id
                WHERE (c.youtube_url IS NOT NULL OR c.tiktok_url IS NOT NULL OR c.instagram_url IS NOT NULL)
                  AND c.vyro_submitted = 0
                ORDER BY c.published_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_all_monetized_clips(self) -> List[Dict[str, Any]]:
        """Returns all published clips across all platforms with monetization metrics."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, v.title as video_title, v.creator_name
                FROM clips c
                JOIN videos v ON c.video_id = v.id
                WHERE c.status = 'published'
                ORDER BY c.published_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def mark_clip_failed(self, clip_id: int, error_message: str):
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE clips SET status = 'failed', error_message = ? WHERE id = ?
            """, (error_message, clip_id))
            conn.commit()

    def get_queued_clips(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM clips WHERE status = 'rendered'
                ORDER BY virality_score DESC, id ASC LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_queued_count(self) -> int:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM clips WHERE status = 'rendered'")
            row = cursor.fetchone()
            return row["count"] if row else 0

    def get_todays_upload_count(self) -> int:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            today_str = date.today().isoformat()
            cursor.execute("""
                SELECT COUNT(*) as count FROM clips 
                WHERE status = 'published' AND date(published_at) = date(?)
            """, (today_str,))
            row = cursor.fetchone()
            return row["count"] if row else 0
