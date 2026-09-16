import os
import sys
import unittest
import tempfile
from storage.database import Database
from core.subtitle_engine import SubtitleEngine
from ai.router import AIRouter

class TestClipper(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_clipper.db")
        self.db = Database(self.db_path)

    def test_database_lifecycle(self):
        # 1. Add video
        vid_id = self.db.add_video("https://youtube.com/watch?v=12345", "youtube", "Test Stream", 3600.0)
        self.assertTrue(vid_id > 0)

        # 2. Add clips
        clip1_id = self.db.add_clip(
            video_id=vid_id,
            start_time=10.0,
            end_time=45.0,
            virality_score=9.5,
            hook_text="Did you see that?",
            title="INSANE MOMENT! #Shorts",
            description="Test description",
            tags="Shorts,viral"
        )
        self.assertTrue(clip1_id > 0)

        # 3. Render clip
        rendered_path = os.path.join(self.temp_dir, "clip1.mp4")
        self.db.update_clip_rendered(clip1_id, rendered_path)

        # 4. Check queued clips
        queued = self.db.get_queued_clips(limit=5)
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["title"], "INSANE MOMENT! #Shorts")

        # 5. Mark published
        self.db.mark_clip_published(clip1_id, "https://youtube.com/shorts/xyz123")
        count = self.db.get_todays_upload_count()
        self.assertEqual(count, 1)

    def test_subtitle_generation(self):
        sub_engine = SubtitleEngine(font_size=40)
        words = [
            {"word": "This", "start": 0.0, "end": 0.4},
            {"word": "is", "start": 0.4, "end": 0.6},
            {"word": "unbelievable", "start": 0.6, "end": 1.2},
            {"word": "viral", "start": 1.2, "end": 1.6},
            {"word": "content", "start": 1.6, "end": 2.2},
        ]
        out_sub_dir = os.path.join(self.temp_dir, "subs")
        overlays = sub_engine.create_subtitle_overlays(
            words=words, clip_start=0.0, clip_end=3.0, output_dir=out_sub_dir
        )
        self.assertTrue(len(overlays) > 0)
        # Verify overlay PNGs exist
        self.assertTrue(os.path.exists(overlays[0]["image_path"]))

if __name__ == "__main__":
    unittest.main()
