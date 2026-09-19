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

                # Dismiss any lingering confirmation dialogs or backdrops
                try:
                    for btn in page.locator("ytcp-confirmation-dialog #confirm-button, ytcp-confirmation-dialog button:has-text('Save'), ytcp-confirmation-dialog button:has-text('Discard')").all():
                        if btn.is_visible():
                            btn.click(force=True)
                            time.sleep(0.5)
                except Exception:
                    pass

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
                try:
                    file_input = page.locator("input[type='file']").first
                    file_input.wait_for(state="attached", timeout=20000)
                    file_input.set_input_files(video_path)
                except Exception as fe:
                    logger.info(f"Direct set_input_files failed ({fe}), falling back to file chooser...")
                    with page.expect_file_chooser(timeout=30000) as fc_info:
                        select_btn = page.locator("#select-files-button, input[type='file']").first
                        select_btn.click(force=True)
                    file_chooser = fc_info.value
                    file_chooser.set_files(video_path)

                # Wait for upload modal
                logger.info("Waiting for upload details dialog...")
                page.wait_for_selector("#textbox", timeout=45000)
                time.sleep(1.0)

                # Set Title using keyboard typing
                logger.info(f"Setting Title: {title[:80]}...")
                title_elem = page.locator("#title-textarea #textbox, #textbox[aria-label*='title' i]").first
                title_elem.wait_for(state="visible", timeout=30000)
                title_elem.click(force=True)
                page.keyboard.press("Meta+A")
                page.keyboard.press("Backspace")
                page.keyboard.type(title[:100], delay=5)
                time.sleep(0.5)
                page.keyboard.press("Escape")

                # Set Description
                desc_elem = page.locator("#description-textarea #textbox, #textbox[aria-label*='description' i]").first
                if desc_elem.is_visible():
                    desc_elem.click(force=True)
                    page.keyboard.press("Meta+A")
                    page.keyboard.press("Backspace")
                    full_desc = f"{description}\n\n{' '.join(['#' + t.strip('#') for t in tags])}"
                    page.keyboard.type(full_desc[:4000], delay=2)
                    time.sleep(0.5)
                    page.keyboard.press("Escape")

                # Mark "Not made for kids" (Strictly required by YouTube to unlock Visibility/Publish)
                logger.info("Setting audience to: No, it's not 'Made for Kids'...")
                not_mfk = page.locator("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK'], tp-yt-paper-radio-button:has-text(\"No, it's not 'Made for Kids'\"), tp-yt-paper-radio-button:has-text(\"Not made for kids\")").first
                not_mfk.wait_for(state="visible", timeout=15000)
                not_mfk.click(force=True)
                time.sleep(0.8)

                # Expand Age restriction and explicitly select: "No, don't restrict my video to viewers over 18 only"
                logger.info("Setting Age restriction to: No, don't restrict my video to viewers over 18 only...")
                try:
                    not_age_restricted = page.locator("tp-yt-paper-radio-button:has-text(\"don't restrict my video to viewers over 18 only\"), tp-yt-paper-radio-button:has-text(\"don't restrict my video\"), tp-yt-paper-radio-button[name*='AGE_RESTRICTION_SAFE'], tp-yt-paper-radio-button[name*='NOT_RESTRICTED'], tp-yt-paper-radio-button[name*='SAFE']").first
                    if not not_age_restricted.is_visible():
                        age_toggle = page.locator("#age-restriction, [aria-label*='Age restriction' i], ytcp-button:has-text('Age restriction'), div:has-text('Age restriction'), span:has-text('Age restriction')").first
                        if age_toggle.is_visible():
                            age_toggle.click(force=True)
                            time.sleep(0.6)

                    if not_age_restricted.is_visible():
                        not_age_restricted.click(force=True)
                        logger.info("✓ Selected: No, don't restrict my video to viewers over 18 only")
                        time.sleep(0.6)
                    else:
                        page.evaluate("""() => {
                            const radios = Array.from(document.querySelectorAll('tp-yt-paper-radio-button, paper-radio-button'));
                            for (const r of radios) {
                                if (r.innerText && (r.innerText.includes("don't restrict") || r.innerText.includes("viewers over 18 only"))) {
                                    r.click();
                                    return true;
                                }
                            }
                            return false;
                        }""")
                        time.sleep(0.5)
                except Exception as ae:
                    logger.warning(f"Notice on age restriction selection: {ae}")


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
                vis_radio = page.locator(vis_selector).first
                vis_radio.wait_for(state="visible", timeout=20000)
                vis_radio.click(force=True)
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
                time.sleep(1.0)

                # Helper to auto-click "Publish anyway" if YouTube prompts with "Publish anyway" or "Go back"
                def click_publish_anyway_if_prompted():
                    try:
                        publish_anyway_selectors = [
                            "ytcp-button:has-text('Publish anyway')",
                            "button:has-text('Publish anyway')",
                            "#publish-anyway-button",
                            "#secondary-action-button:has-text('Publish anyway')",
                            "[aria-label*='Publish anyway' i]",
                            "ytcp-confirmation-dialog ytcp-button:has-text('Publish')",
                            "tp-yt-paper-dialog button:has-text('Publish anyway')",
                            "ytcp-dialog button:has-text('Publish anyway')"
                        ]
                        clicked = False
                        for sel in publish_anyway_selectors:
                            btn = page.locator(sel).first
                            if btn.is_visible():
                                logger.info("⚡ Detected 'Publish anyway' prompt from YouTube. Clicking 'Publish anyway'...")
                                btn.click(force=True)
                                clicked = True
                                time.sleep(1.0)
                                break
                        if not clicked:
                            page.evaluate("""() => {
                                const elements = Array.from(document.querySelectorAll('button, ytcp-button, tp-yt-paper-button, ytcp-confirmation-dialog ytcp-button'));
                                for (const el of elements) {
                                    if (el.innerText && el.innerText.toLowerCase().includes('publish anyway')) {
                                        el.click();
                                        return true;
                                    }
                                }
                                return false;
                            }""")
                    except Exception:
                        pass

                # Check immediately after clicking done
                click_publish_anyway_if_prompted()

                # Wait for upload completion and publication confirmation
                logger.info("Waiting for video upload and publication to finalize...")
                for _ in range(30):
                    time.sleep(2)
                    click_publish_anyway_if_prompted()
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
