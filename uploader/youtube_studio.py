import os
import time
import shutil
import base64
import tarfile
import logging
from typing import Dict, Any, List
from uploader.base import BaseUploader

logger = logging.getLogger("Clipper.YouTubeStudio")

class YouTubeStudioUploader(BaseUploader):
    def __init__(self, session_dir: str = "session_data/chrome_profile", headless: bool = True):
        self.session_dir = os.path.abspath(session_dir)
        self.headless = headless
        os.makedirs(self.session_dir, exist_ok=True)
        self._check_env_session()

    def _check_env_session(self):
        """If YOUTUBE_SESSION_B64 is in environment, restore it into session_dir."""
        b64_data = os.getenv("YOUTUBE_SESSION_B64")
        if b64_data and not os.path.exists(os.path.join(self.session_dir, "Default", "Cookies")):
            logger.info("Restoring YouTube session from YOUTUBE_SESSION_B64 environment variable...")
            self.import_session_b64(b64_data)

    def export_session_b64(self) -> str:
        """
        Packs the essential cookies and authentication tokens into a portable,
        ultra-compact base64 string (< 30 KB) that easily fits inside GitHub Secrets.
        """
        if not os.path.exists(self.session_dir) or not os.listdir(self.session_dir):
            raise ValueError(f"Session directory {self.session_dir} is empty. Run 'python cli.py login' first!")

        def filter_essentials(tarinfo):
            name = tarinfo.name
            essentials = [
                "profile",
                "profile/Default",
                "profile/Default/Cookies",
                "profile/Default/Cookies-journal",
                "profile/Default/Network Persistent State",
                "profile/Default/Preferences",
                "profile/Default/Secure Preferences",
                "profile/Default/Local Storage",
            ]
            if any(name == e or name.startswith("profile/Default/Local Storage") for e in essentials):
                return tarinfo
            return None

        archive_path = "session_temp.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(self.session_dir, arcname="profile", filter=filter_essentials)

        with open(archive_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        if os.path.exists(archive_path):
            os.remove(archive_path)

        return encoded

    def import_session_b64(self, b64_str: str):
        """Unpacks base64 session string into session_dir."""
        archive_path = "session_temp.tar.gz"
        with open(archive_path, "wb") as f:
            f.write(base64.b64decode(b64_str))

        extract_temp = "session_temp_extract"
        os.makedirs(extract_temp, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(extract_temp)

        extract_dir = os.path.join(extract_temp, "profile")
        if os.path.exists(extract_dir):
            for root, dirs, files in os.walk(extract_dir):
                rel_path = os.path.relpath(root, extract_dir)
                target_root = os.path.join(self.session_dir, rel_path)
                os.makedirs(target_root, exist_ok=True)
                for f in files:
                    src_f = os.path.join(root, f)
                    dst_f = os.path.join(target_root, f)
                    shutil.copy2(src_f, dst_f)

        # Cleanup
        if os.path.exists(archive_path):
            os.remove(archive_path)
        if os.path.exists(extract_temp):
            shutil.rmtree(extract_temp)

        logger.info(f"Successfully restored session into {self.session_dir}")

    def login_session(self):
        """
        Launches a visible browser window allowing the user to log into YouTube Studio once.
        The session cookies and tokens will be permanently saved to session_data.
        """
        from playwright.sync_api import sync_playwright
        logger.info("Opening browser for one-time YouTube Studio authentication...")
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=self.session_dir,
                headless=False,
                channel="chrome" if os.path.exists("/Applications/Google Chrome.app") else None,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page()
            page.goto("https://studio.youtube.com")
            print("\n=======================================================")
            print("Please log in to your YouTube account in the browser window.")
            print("Once logged into YouTube Studio, press ENTER here in the terminal.")
            print("=======================================================\n")
            input("Press Enter after logging in...")
            browser.close()
        logger.info("Session saved successfully!")

    def upload_short(self, video_path: str, title: str, description: str,
                     tags: List[str], visibility: str = "public") -> Dict[str, Any]:
        """
        Uploads a video to YouTube Studio using the saved persistent session.
        Uses ZERO official API quota.
        """
        from playwright.sync_api import sync_playwright
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        logger.info(f"Starting automated Studio upload for: {title}")
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=self.session_dir,
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page()

            try:
                page.goto("https://studio.youtube.com", wait_until="networkidle", timeout=60000)
                
                # Check if logged in
                if "accounts.google.com" in page.url:
                    browser.close()
                    raise RuntimeError("Not logged into YouTube Studio. Run 'python cli.py login' or set YOUTUBE_SESSION_B64 secret!")

                # Click CREATE button or upload icon
                logger.info("Clicking Create / Upload button...")
                page.locator("#create-icon, #upload-button, button:has-text('Create')").first.click(timeout=10000)
                time.sleep(1)
                page.locator("tp-yt-paper-item:has-text('Upload videos'), #text-item-0").first.click(timeout=10000)

                # Set file input
                logger.info("Selecting video file...")
                with page.expect_file_chooser() as fc_info:
                    page.locator("#select-files-button, input[type='file']").first.click()
                file_chooser = fc_info.value
                file_chooser.set_files(video_path)

                # Wait for upload modal
                page.wait_for_selector("#textbox", timeout=30000)
                time.sleep(3)

                # Set Title
                logger.info("Filling Title & Description...")
                title_box = page.locator("#textbox").first
                title_box.fill(title[:100])

                # Set Description
                desc_boxes = page.locator("#textbox").all()
                if len(desc_boxes) > 1:
                    full_desc = f"{description}\n\n{' '.join(['#' + t.strip('#') for t in tags])}"
                    desc_boxes[1].fill(full_desc[:5000])

                # Mark "Not made for kids"
                logger.info("Setting audience settings...")
                page.locator("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']").click()
                time.sleep(1)

                # Click Next through video elements & checks
                logger.info("Advancing through steps...")
                for _ in range(3):
                    next_btn = page.locator("#next-button").first
                    if next_btn.is_visible():
                        next_btn.click()
                        time.sleep(2)

                # Set Visibility
                logger.info(f"Setting visibility to {visibility}...")
                if visibility == "public":
                    page.locator("tp-yt-paper-radio-button[name='PUBLIC']").click()
                elif visibility == "unlisted":
                    page.locator("tp-yt-paper-radio-button[name='UNLISTED']").click()
                else:
                    page.locator("tp-yt-paper-radio-button[name='PRIVATE']").click()

                time.sleep(2)

                # Get generated short video link if visible
                short_url = ""
                try:
                    link_elem = page.locator("a.ytcp-video-info").first
                    if link_elem.is_visible():
                        short_url = link_elem.get_attribute("href") or ""
                except Exception:
                    pass

                # Click Publish / Done
                logger.info("Submitting publication...")
                done_btn = page.locator("#done-button").first
                done_btn.click()
                time.sleep(5)

                logger.info(f"Successfully uploaded short to YouTube Studio! URL: {short_url}")
                browser.close()
                return {
                    "status": "success",
                    "url": short_url or "https://youtube.com/shorts",
                    "title": title
                }

            except Exception as e:
                logger.error(f"Studio upload failed: {e}")
                browser.close()
                raise e
