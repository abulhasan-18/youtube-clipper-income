# AI Video Clipper & YouTube Shorts Auto-Publisher (50 Clips/Day)

An autonomous, multi-model AI pipeline that ingests long-form videos (YouTube, Twitch, Podcasts, Streams), transcribes audio with millisecond word timestamps using **Groq Whisper**, identifies high-retention viral moments using **OpenRouter DeepSeek & Groq Qwen**, reframes to **9:16 vertical video** with face tracking, burns **dynamic Hormozi-style subtitles**, and drip-publishes **50 viral Shorts/day** directly to YouTube without hitting API quota limits.

---

## ⚡ Key Features

- **Multi-Model AI Brain**:
  - **Groq Whisper Large v3**: Transcribes 1-hour audio in ~3 seconds with millisecond word timings.
  - **Groq Qwen 27B / Cerebras**: Rapidly parses full transcripts for 25–60s viral candidates.
  - **OpenRouter DeepSeek-Chat/R1**: Deep reasoning on viral psychology, hook retention (first 3 seconds), and curiosity gaps.
  - **Google Gemini 3.6 Flash**: Multimodal visual inspection of scene clarity and speaker dynamics.
  - **Failover Matrix**: Cascades automatically across providers so the pipeline never stops.
- **Smart 9:16 Vertical Video Reframing**:
  - `face_track`: Dynamically centers active speakers using OpenCV/MediaPipe with smoothed camera panning.
  - `blur_bg`: Centers 16:9 content over a stylized blurred background for multi-speaker podcasts or gameplay.
  - `split_screen`: Streamer facecam on top, gameplay on bottom.
- **Hormozi / MrBeast Dynamic Subtitles**:
  - 2–3 words per screen, highlighted in neon yellow (`#FFE600`) as each word is spoken.
  - Bold TrueType typography with heavy black outline and shadow for maximum mobile contrast.
- **Quota-Free YouTube Auto-Publisher**:
  - Official API is capped at ~6 uploads/day (10,000 units/day, 1,600 units/upload).
  - Included **Playwright Studio Uploader** connects directly to YouTube Creator Studio with persistent sessions, allowing **50 uploads/day** at zero API quota cost.
- **24/7 Drip Scheduler**:
  - Drip-feeds clips every ~28 minutes across 24 hours to maximize YouTube algorithm reach and avoid spam throttling.

---

## 🚀 Quickstart

### 1. Check Installation
The project runs inside the isolated `.venv`:
```bash
source .venv/bin/activate
```

### 2. Extract Clips from a Video or Stream
```bash
python cli.py clip "https://www.youtube.com/watch?v=VIDEO_ID" --max-clips 5 --mode face_track
```

### 3. Check Queued Clips
```bash
python cli.py queue
```

### 4. Authenticate YouTube Studio (One-time Setup)
To enable zero-quota publishing, log in once:
```bash
python cli.py login
```
A browser will open. Log into your YouTube channel in YouTube Studio, and press Enter in the terminal. Your credentials are securely cached in `session_data/` for all future headless uploads.

### 5. Start Autonomous 50 Clips/Day Publishing
```bash
python cli.py schedule
```

---

## 📁 Project Structure

```
.
├── ai/
│   ├── router.py            # Multi-model AI client with auto-failover
│   ├── transcriber.py       # Groq whisper-large-v3 transcription
│   ├── candidate_scanner.py # Rapid transcript candidate extractor
│   ├── viral_evaluator.py   # DeepSeek viral psychology judge
│   ├── visual_verifier.py   # Gemini visual keyframe inspector
│   └── copywriter.py        # High-CTR title & SEO tags generator
├── core/
│   ├── downloader.py        # yt-dlp audio-first & video segment downloader
│   ├── face_tracker.py      # Face detection & speaker trajectory centering
│   ├── subtitle_engine.py   # Hormozi animated subtitle generator (Pillow overlays)
│   └── video_processor.py   # FFmpeg 1080x1920 60fps compositor
├── uploader/
│   ├── youtube_studio.py    # Playwright automated zero-quota uploader
│   └── youtube_api.py       # Official YouTube Data API v3 uploader
├── storage/
│   └── database.py          # SQLite queue & daily upload tracker
├── config.yaml              # Global settings (durations, styles, schedule)
├── pipeline.py              # Single-run master orchestrator
├── scheduler.py             # 24/7 drip publishing daemon
└── cli.py                   # Command-line interface
```
