from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseUploader(ABC):
    @abstractmethod
    def upload_short(self, video_path: str, title: str, description: str,
                     tags: List[str], visibility: str = "public") -> Dict[str, Any]:
        """
        Uploads a short video and returns a dict with status and published URL.
        """
        pass
