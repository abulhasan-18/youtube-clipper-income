import os
import time
import shutil
import base64
import tarfile
import logging
from typing import Dict, Any, List
from uploader.base import BaseUploader

logger = logging.getLogger("Clipper.YouTubeStudio")

DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

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
                user_agent=DEFAULT_USER_AGENT,
                channel="chrome" if os.path.exists("/Applications/Google Chrome.app") else None,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page()
            page.goto("https://studio.youtube.com/?approve_browser_access=true")
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
            extra_args = ["--disable-blink-features=AutomationControlled"]
            if self.headless:
                extra_args.append("--headless=new")

            browser = p.chromium.launch_persistent_context(
                user_data_dir=self.session_dir,
                headless=self.headless,
                user_agent=DEFAULT_USER_AGENT,
                channel="chrome" if os.path.exists("/Applications/Google Chrome.app") else None,
                args=extra_args
            )
            page = browser.new_page()

            try:
                # Use domcontentloaded to prevent networkidle timeouts on YouTube websockets
                page.goto("https://studio.youtube.com/?approve_browser_access=true", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1200)

                # Check if "Skip to YouTube Studio" link exists and click it
                skip_link = page.locator("a:has-text('Skip to YouTube Studio'), a[href*='approve_browser_access']").first
                if skip_link.is_visible():
                    skip_link.click(force=True)
                    page.wait_for_timeout(1200)

                # Check if logged in
                if "accounts.google.com" in page.url:
                    browser.close()
                    raise RuntimeError("Not logged into YouTube Studio. Run 'python cli.py login' or set YOUTUBE_SESSION_B64 secret!")

                # Click CREATE button
                logger.info("Clicking Create button...")
                create_btn = page.locator("#create-icon, #upload-button, [aria-label='Create'], ytcp-button#create-icon").first
                create_btn.wait_for(state="visible", timeout=25000)
                create_btn.click(force=True)
                time.sleep(0.5)

                # Click "Upload videos"
                logger.info("Clicking Upload videos option...")
                upload_opt = page.locator("tp-yt-paper-item:has-text('Upload videos'), #text-item-0, ytcp-text-menu #text-item-0").first
                upload_opt.wait_for(state="visible", timeout=15000)
                upload_opt.click(force=True)

                # Set file input
                logger.info("Selecting video file...")
                with page.expect_file_chooser(timeout=30000) as fc_info:
                    select_btn = page.locator("#select-files-button, input[type='file']").first
                    select_btn.click(force=True)
                file_chooser = fc_info.value
                file_chooser.set_files(video_path)

                # Wait for upload modal
                logger.info("Waiting for upload details dialog...")
                page.wait_for_selector("#textbox", timeout=45000)
                time.sleep(0.8)

                # Set Title using execCommand for contenteditable Polymer textbox
                logger.info("Filling Title & Description...")
                title_elem = page.locator("#title-textarea #textbox, ytcp-social-suggestions-textbox[aria-label*='title' i] #textbox, #textbox[aria-label*='title' i]").first
                if title_elem.is_visible():
                    title_elem.click()
                    page.evaluate('''([el, text]) => {
                        el.focus();
                        document.execCommand('selectAll', false, null);
                        document.execCommand('insertText', false, text);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }''', [title_elem.element_handle(), title[:100]])
                    time.sleep(0.5)

                # Set Description
                desc_elem = page.locator("#description-textarea #textbox, ytcp-social-suggestions-textbox[aria-label*='description' i] #textbox").first
                if desc_elem.is_visible():
                    desc_elem.click()
                    full_desc = f"{description}\n\n{' '.join(['#' + t.strip('#') for t in tags])}"
                    page.evaluate('''([el, text]) => {
                        el.focus();
                        document.execCommand('selectAll', false, null);
                        document.execCommand('insertText', false, text);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }''', [desc_elem.element_handle(), full_desc[:5000]])
                    time.sleep(0.5)

                # Mark "Not made for kids"
                logger.info("Setting audience to Not Made for Kids...")
                time.sleep(0.3)
                page.evaluate("() => { const r = document.querySelector('tp-yt-paper-radio-button[name=\"VIDEO_MADE_FOR_KIDS_NOT_MFK\"]'); if(r) r.click(); }")
                time.sleep(0.5)

                # Helper to handle Google "Verify that it's you" prompt if triggered
                def handle_verification_if_needed():
                    verify_texts = ["Verify that it's you", "Confirm that it's really you", "Verify it's you"]
                    for vt in verify_texts:
                        if page.locator(f"text='{vt}'").is_visible():
                            logger.warning("=" * 65)
                            logger.warning("⚠️  ACTION REQUIRED: YouTube 'Verify that it's you' prompt detected.")
                            logger.warning("Please complete the verification prompt in the Chrome browser / on your phone.")
                            logger.warning("=" * 65)
                            try:
                                v_dialog = page.locator("tp-yt-paper-dialog, [role='dialog'], ytcp-dialog").filter(has_text=vt).first
                                v_btn = v_dialog.locator("#next-button, ytcp-button, button").filter(has_text="Next").first
                                if v_btn.is_visible():
                                    v_btn.click(force=True)
                            except Exception:
                                pass

                            for i in range(100):
                                time.sleep(3)
                                still_showing = any(page.locator(f"text='{t}'").is_visible() for t in verify_texts)
                                if not still_showing:
                                    logger.info("✓ Verification resolved! Continuing upload...")
                                    time.sleep(2)
                                    break
                                if i % 10 == 0:
                                    logger.info("Waiting for security verification to be completed in browser...")
                            break

                handle_verification_if_needed()

                # Extract video link if already visible in dialog
                short_url = ""
                try:
                    for el in page.locator("a[href*='youtu.be'], a[href*='youtube.com/shorts'], a.ytcp-video-info").all():
                        h = el.get_attribute("href")
                        if h and ("youtu.be" in h or "youtube.com" in h):
                            short_url = h
                            break
                except Exception:
                    pass

                # Direct Jump to Visibility Step Badge
                logger.info("Navigating to Visibility step...")
                vis_badge = page.locator("#step-badge-3, [test-id='VISIBILITY']").first
                if vis_badge.is_visible():
                    vis_badge.click(force=True)
                    time.sleep(1.2)
                else:
                    for _ in range(3):
                        handle_verification_if_needed()
                        time.sleep(0.3)
                        nb = page.locator("#next-button:not([hidden])").first
                        if nb.is_visible():
                            nb.click(force=True)
                            time.sleep(0.8)

                handle_verification_if_needed()

                # Set Visibility to Public
                logger.info(f"Setting visibility to {visibility}...")
                vis_selector = f"tp-yt-paper-radio-button[name='{visibility.upper()}']"
                page.wait_for_selector(vis_selector, timeout=20000)
                page.evaluate(f"() => {{ const r = document.querySelector(\"{vis_selector}\"); if(r) r.click(); }}")
                time.sleep(1.0)

                # Fetch URL before submitting if not yet found
                if not short_url:
                    try:
                        for el in page.locator("a[href*='youtu.be'], a[href*='youtube.com/shorts'], a.ytcp-video-info").all():
                            h = el.get_attribute("href")
                            if h and ("youtu.be" in h or "youtube.com" in h):
                                short_url = h
                                break
                    except Exception:
                        pass

                # Click Publish
                logger.info("Submitting publication...")
                done_btn = page.locator("#done-button:not([hidden]), #done-button, ytcp-button#done-button").first
                done_btn.wait_for(state="visible", timeout=20000)
                done_btn.click(force=True)

                # Wait for upload completion and publication confirmation
                logger.info("Waiting for video upload and publication to finalize...")
                for _ in range(30):
                    time.sleep(2)
                    if not short_url:
                        try:
                            for el in page.locator("a[href*='youtu.be'], a[href*='youtube.com/shorts'], a.ytcp-video-info").all():
                                h = el.get_attribute("href")
                                if h and ("youtu.be" in h or "youtube.com" in h):
                                    short_url = h
                                    break
                        except Exception:
                            pass

                    # Check if share dialog appeared or upload dialog closed
                    if page.locator("ytcp-video-share-dialog, #share-url, tp-yt-paper-dialog:has-text('published')").first.is_visible():
                        logger.info("Publication confirmed by Studio share dialog!")
                        break
                    if not page.locator("ytcp-uploads-dialog").is_visible():
                        logger.info("Upload dialog closed, publication saved!")
                        break

                # Close post-publish share dialog if open
                try:
                    close_btn = page.locator("ytcp-video-share-dialog #close-button, #close-button, ytcp-button#close-button").first
                    if close_btn.is_visible():
                        close_btn.click(force=True)
                except Exception:
                    pass

                if not short_url:
                    raise RuntimeError("Upload submitted, but could not detect published video URL.")

                # Format short link
                if "youtu.be/" in short_url:
                    vid_id = short_url.split("youtu.be/")[1].split("?")[0].strip()
                    short_url = f"https://youtube.com/shorts/{vid_id}"

                logger.info(f"Successfully uploaded short to YouTube Studio! URL: {short_url}")
                browser.close()
                return {
                    "status": "success",
                    "url": short_url,
                    "title": title
                }

            except Exception as e:
                logger.error(f"Studio upload failed: {e}")
                try:
                    page.screenshot(path="studio_error.png")
                except Exception:
                    pass
                browser.close()
                raise e
