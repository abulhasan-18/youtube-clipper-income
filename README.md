# 🎬 Autonomous AI Video Clipper & YouTube Shorts Income Engine (50 Clips/Day)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Multi-Model AI](https://img.shields.io/badge/AI-Groq%20%7C%20DeepSeek%20%7C%20Gemini%20%7C%20Cerebras-orange.svg)]()
[![Free Hosting: GitHub Actions](https://img.shields.io/badge/Hosting-GitHub%20Actions%20(100%25%20Free)-green.svg)]()

A 100% autonomous, zero-touch video clipping and publishing pipeline. It monitors the **top 50 global creators & streamers** (*IShowSpeed, Kai Cenat, Ibai, xQc, MrBeast, CaseOh, etc.*), transcribes audio in ~3 seconds using **Groq Whisper Large v3**, extracts high-retention viral moments using **OpenRouter DeepSeek & Groq Qwen**, reframes to **9:16 vertical video** with face tracking, burns **animated Hormozi subtitles**, and publishes **50 YouTube Shorts daily** without human intervention or API quota fees.

---

## ⚡ Architecture Flow

```mermaid
flowchart TD
    subgraph 24/7 Cloud Execution
        A[GitHub Actions / Free Cloud Host] --> B{Queue has < 10 clips?}
        B -->|Yes| C[Discovery Engine: 50 Monitored Creators]
        C --> D[Ingest Fresh Video & Audio via yt-dlp]
        D -->|Groq Whisper Large v3| E[Timestamped Transcript ~3s]
        E -->|OpenRouter DeepSeek R1/V3 & Gemini| F[Score & Rank Viral Hooks]
        F -->|FFmpeg + Face Tracking + Pillow Overlays| G[Render 9:16 1080x1920 with Hormozi Captions]
        G --> H[Store in SQLite Database]
        B -->|No: Queue Ready| I[Publishing Timer]
        H --> I
        I -->|Every 28.8 minutes| J[Playwright Studio Uploader: Zero API Quota]
        J --> K[YouTube Shorts Channel: 50 Clips/Day]
    end
```

---

## 🌟 Multi-Model AI Brain ("Wisely Allocated")

| Stage | Model & Provider | Superpower |
| :--- | :--- | :--- |
| **Speech-to-Text** | **Groq** (`whisper-large-v3`) | Transcribes 1 hour in ~3 seconds with millisecond word timestamps. |
| **Candidate Scanning** | **Groq** (`qwen/qwen3.8-27b`) / **Cerebras** (`gpt-oss-120b`) | Rapidly parses entire multi-hour transcripts for 25s–60s segments in < 1 second. |
| **Viral Psychology** | **OpenRouter** (`deepseek/deepseek-chat` or `r1`) | Evaluates hook retention (first 3 seconds), curiosity gaps, and humor. |
| **Scene Verification**| **Google Gemini** (`gemini-3.6-flash`) | Multimodal video inspection of speaker emotion and visual clarity. |
| **SEO Copywriting** | **Groq** (`qwen/qwen3.8-27b`) | High-CTR click-worthy titles, descriptions, and trending tags (`#Shorts`, `#viral`). |

---

## 📋 Monitored Top 50 Creators Registry (`creators.yaml`)

The pipeline continuously monitors 50 of the world's most viewed streamers and creators across YouTube, Twitch, and Kick:

- **USA / English**: IShowSpeed, Kai Cenat, xQc, Adin Ross, Ninja, MrBeast, Pokimane, Jynxzi, Shroud, HasanAbi, CaseOh, Clix, Stable Ronaldo, Fanum, PlaqueBoyMax, Cinna, Ludwig, Valkyrae, AMP, Buddha, Trainwreckstv, Amouranth, Tarik, Duke Dennis, TimTheTatman, Dr DisRespect, Nickmercs, Summit1g, Sodapoppin, Markiplier, CoryxKenshin, CaseyNeistat, Speedy Morman, Pestily.
- **Spain & Latin America**: Ibai, AuronPlay, Rubius, TheGrefg, ElMariana, JuanSGuarnizo, Casimito, WestCOL, MrStivenTC, Davoo Xeneize, Lacobraaa.
- **International**: PewDiePie (Sweden), Baka Prase (Serbia), Eray Özkenar (Turkey), EasyLiker (Russia).

---

## 🚀 Quick Setup & 100% Free Hosting Deployment

### 1. Push to GitHub
```bash
# Set your remote repository
git remote add origin https://github.com/abulhasan-18/youtube-clipper-income.git
git branch -M main
git push -u origin main
```

*(Your `.env`, media files, and local session cookies are automatically protected by `.gitignore`.)*

---

### 2. Run 100% Free via GitHub Actions (Zero Server Cost)

This repository includes a scheduled workflow at `.github/workflows/clipper_autopilot.yml` that runs every 30 minutes on GitHub's free Ubuntu cloud runners.

#### Step A: Authenticate YouTube Studio Once Locally
On your Mac/PC:
```bash
# 1. Create and activate venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pillow opencv-python-headless
playwright install chromium

# 2. Log in once to YouTube Studio
python cli.py login
```
*(A browser will open. Sign into your YouTube channel in YouTube Studio once, then press **Enter** in your terminal.)*

#### Step B: Export Session for the Cloud
```bash
python cli.py export-session
```
Copy the generated base64 string.

#### Step C: Add Secrets in GitHub
In your GitHub repo (`https://github.com/abulhasan-18/youtube-clipper-income`), go to:  
**Settings** $\to$ **Secrets and variables** $\to$ **Actions** $\to$ **New repository secret**:

| Secret Name | Description |
| :--- | :--- |
| `GEMINI_API_KEY` | Your Google Gemini API Key |
| `GROQ_API_KEY` | Your Groq Cloud API Key |
| `OPENROUTER_API_KEY`| Your OpenRouter API Key |
| `CEREBRAS_API_KEY` | Your Cerebras Cloud API Key |
| `YOUTUBE_SESSION_B64` | The exported base64 session string from Step B |

#### Step D: Enable Workflow
Go to the **Actions** tab on your GitHub repository, click **Autonomous AI Video Clipper**, and click **Run workflow**! It will now run automatically on a cron schedule every 30 minutes!

---

### 3. Alternative Free Hosting (Render / Koyeb / Hugging Face Spaces)

A production `Dockerfile` is included:
- **Hugging Face Spaces**: Create a Space, select **Docker**, link this GitHub repo. (Free 2-vCPU / 16GB RAM 24/7 forever).
- **Render / Koyeb**: Deploy as a background worker with `python cli.py autopilot`.

---

## 💻 Local CLI Commands

```bash
# 1. View the 50 monitored creators
python cli.py creators

# 2. Test content discovery (finds a fresh video right now)
python cli.py discover

# 3. Clip a specific video manually
python cli.py clip "https://www.youtube.com/watch?v=VIDEO_ID" --max-clips 5 --mode face_track

# 4. View queue status and daily upload count
python cli.py queue

# 5. Run full 100% autonomous 24/7 AutoPilot locally
python cli.py autopilot
```

---

## ⚖️ License
MIT License. Built for autonomous content creation and automated media distribution.
