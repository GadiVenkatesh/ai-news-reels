# AI News Reels

Turn recent AI and technology news into a **60-second vertical 9:16 MP4** with a generated voice-over and four on-screen scene cards.

The workflow generates a downloadable artifact for you to review. It does **not** automatically publish to Instagram or YouTube.

## Features

- Reads recent articles from configurable RSS feeds.
- Ranks stories using topic keywords and publication recency.
- Creates a short factual narration using optional local Ollama, with a template fallback.
- Generates voice-over audio with Edge TTS.
- Renders four 15-second branded cards into a 1080×1920 H.264/AAC MP4.
- Targets a 60-second output: shorter voice-overs are padded with silence; longer ones are sped up by up to 1.5× before the 60-second trim.
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
4. When the run completes, open it and download the `ai-news-reel-*` artifact.

The workflow is also scheduled daily at **03:30 UTC / 09:00 India Standard Time**.

## Configuration

Copy `.env.example` to `.env` and adjust:

| Variable | Purpose |
|---|---|
| `RSS_FEEDS` | Comma-separated RSS feed URLs |
| `TOPIC_KEYWORDS` | Comma-separated keywords used for relevance ranking |
| `MAX_STORY_AGE_HOURS` | Maximum article age |
| `TTS_VOICE` | Edge TTS voice |
| `TTS_RATE` | Speech rate adjustment |
| `TTS_PITCH` | Voice pitch adjustment |
| `USE_OLLAMA` | Enable local Ollama script generation |
| `OLLAMA_BASE_URL` | Ollama API base URL |
| `OLLAMA_MODEL` | Ollama model name |
| `VIDEO_WIDTH`, `VIDEO_HEIGHT` | Output dimensions |

## Limitations and review

- Keyword ranking is a simple relevance heuristic; it is not a measure of global trend popularity.
- Current visuals are typographic cards, not AI-generated photographic scenes.
- Edge TTS needs an internet connection.
- Review names, facts, pronunciation, narration timing, source attribution, and media rights before publishing.
- The workflow stores output as an Actions artifact for 14 days; it does not post to social accounts.

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
