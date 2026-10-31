# AI News Reels

Turn recent AI and technology news into an **exactly 60-second vertical 9:16 MP4** with Telugu or English narration and matching on-screen text.

The workflow generates a downloadable artifact for review. A separate publishing workflow can automatically publish it to YouTube Shorts and Instagram Reels when configured.

## Features

- Reads recent articles from configurable RSS feeds.
- Ranks stories using topic keywords and publication recency.
- Lets you select **Telugu or English** when manually running the GitHub Actions workflow; Telugu is the default for scheduled runs.
- Creates a factual narration in the selected language using a template fallback (optional local Ollama is available for local runs).
- Generates voice-over audio with Edge TTS.
- Downloads an article thumbnail from RSS media fields or article summary HTML when available, then uses it as a darkened full-screen background behind each scene's text.
- Falls back to designed text cards when the selected RSS item has no downloadable image.
- Renders four 15-second scenes into a 1080×1920 H.264/AAC MP4, with final duration checked by `ffprobe`.
- Always renders a fixed 60-second MP4; duration is not a workflow option. The audio is trimmed/padded to the same 60-second timeline.
- Saves the MP4, script JSON, voice-over MP3, and source note under `output/`.

## Requirements

- Python 3.11+
- FFmpeg and ffprobe on PATH
- Internet access for RSS feeds and Edge TTS
- Optional: Ollama for locally generated scripts

## Run locally on Windows

Open PowerShell in the project directory:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.main
```

Install FFmpeg separately and verify that `ffmpeg -version` and `ffprobe -version` work in the terminal.

For Linux/macOS, activate the virtual environment using the platform-appropriate command, install FFmpeg with your package manager, then run:

```bash
python -m pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

Generated files appear in `output/`.

## Optional Ollama script generation

Install [Ollama](https://ollama.com/) and pull a model:

```bash
ollama pull llama3.2
```

Set `USE_OLLAMA=true` in `.env`. The app calls the local Ollama HTTP API. When Ollama is disabled or unavailable, a deterministic template script is used. GitHub-hosted runners do not have your local Ollama instance.

## Run with GitHub Actions

1. Open the repository's **Actions** tab and enable workflows if GitHub prompts you.
2. Select **Generate AI News Reel**.
3. Click **Run workflow** to start it manually.
4. Choose **Telugu (`te`)** or **English (`en`)** in the Language dropdown. The video duration is fixed at 60 seconds.
5. When the run completes, open it and download the `ai-news-reel-*` artifact.

The workflow is also scheduled daily at **03:30 UTC / 09:00 India Standard Time**.

## Configuration

Copy `.env.example` to `.env` and adjust:

| Variable | Purpose |
|---|---|
| `RSS_FEEDS` | Comma-separated RSS feed URLs |
| `TOPIC_KEYWORDS` | Comma-separated keywords used for relevance ranking |
| `MAX_STORY_AGE_HOURS` | Maximum article age |
| `LANGUAGE` | `te` for Telugu or `en` for English; defaults to Telugu in GitHub Actions |
| `TTS_VOICE` | Optional Edge TTS voice override; defaults based on language |
| `TTS_RATE` | Speech rate adjustment |
| `TTS_PITCH` | Voice pitch adjustment |
| `USE_OLLAMA` | Enable local Ollama script generation |
| `OLLAMA_BASE_URL` | Ollama API base URL |
| `OLLAMA_MODEL` | Ollama model name |
| `VIDEO_WIDTH`, `VIDEO_HEIGHT` | Output dimensions |

## Limitations and review

- Keyword ranking is a simple relevance heuristic; it is not a measure of global trend popularity.
- Visuals use the selected article's thumbnail when the RSS feed exposes one. Some feeds do not provide images, so the app falls back to typographic cards. This version does not generate original images with a diffusion model. Telugu headline/summary translation requires access to Google's public translation endpoint.
- Edge TTS needs an internet connection.
- Review names, facts, pronunciation, narration timing, source attribution, and media rights before publishing.
- The generation workflow stores output as an Actions artifact for 14 days. Social publishing is handled by the separate Publish AI News Reel workflow.

## Automatic social publishing

A separate **Publish AI News Reel** workflow can publish generated videos to YouTube Shorts and Instagram Reels. See [Social Publishing Setup](docs/SOCIAL_PUBLISHING_SETUP.md) for the required OAuth credentials, Meta professional-account setup, GitHub Actions secrets/variables, and how to run the workflow. Instagram uses direct resumable upload to Meta; no AWS or S3 setup is required. YouTube visibility defaults to private; change it only after testing. Instagram Reels publishing requires an eligible Business or Creator account.

## Project structure

```text
ai-news-reels/
├── .github/workflows/generate-reel.yml
├── app/
│   ├── __init__.py
│   └── main.py
├── output/.gitkeep
├── tests/test_smoke.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```
