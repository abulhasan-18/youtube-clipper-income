import os
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger("Clipper.FaceTracker")

class FaceTracker:
    def __init__(self):
        self.face_cascade = None
        try:
            import cv2
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            if os.path.exists(cascade_path):
                self.face_cascade = cv2.CascadeClassifier(cascade_path)
        except Exception as e:
            logger.warning(f"OpenCV face cascade unavailable: {e}. Fallback to center crop.")

    def analyze_speaker_trajectory(self, video_path: str, sample_interval_sec: float = 0.5) -> float:
        """
        Samples video frames at intervals, detects faces, and computes
        the optimal smoothed horizontal center coordinate (0.0 to 1.0).
        """
        if self.face_cascade is None:
            return 0.5

        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return 0.5

            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_step = max(1, int(fps * sample_interval_sec))

            centers = []
            frame_idx = 0

            while frame_idx < total_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.2,
                    minNeighbors=4,
                    minSize=(60, 60)
                )

                if len(faces) > 0:
                    largest = max(faces, key=lambda b: b[2] * b[3])
                    x, y, w, h = largest
                    center_norm = (x + w / 2.0) / frame_width
                    centers.append(center_norm)

                frame_idx += frame_step

            cap.release()

            if not centers:
                return 0.5

            avg_center = sum(centers) / len(centers)
            crop_ratio = (9.0 / 16.0) / (16.0 / 9.0)
            min_center = crop_ratio / 2.0
            max_center = 1.0 - (crop_ratio / 2.0)

            clamped_center = max(min_center, min(max_center, avg_center))
            return clamped_center
        except Exception as e:
            logger.warning(f"Face tracking error: {e}. Defaulting to center 0.5.")
            return 0.5
