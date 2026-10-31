from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import edge_tts
import feedparser
import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def plain(text: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def published(entry) -> datetime:
    for key in ("published", "updated"):
        try:
            dt = parsedate_to_datetime(entry.get(key, ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc) - timedelta(hours=1)


def get_story() -> dict:
    default_feeds = (
        "https://www.technologyreview.com/feed/,"
        "https://techcrunch.com/category/artificial-intelligence/feed/,"
        "https://hnrss.org/frontpage"
    )
    feeds = [
        item.strip()
        for item in os.getenv("RSS_FEEDS", default_feeds).split(",")
        if item.strip()
    ]
    default_keywords = (
        "AI,artificial intelligence,machine learning,LLM,robotics,"
        "OpenAI,Google Gemini,Claude,agent,technology,GPU"
    )
    keywords = [
        item.strip().lower()
        for item in os.getenv("TOPIC_KEYWORDS", default_keywords).split(",")
        if item.strip()
    ]
    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=env_int("MAX_STORY_AGE_HOURS", 72)
    )
    stories: list[dict] = []
    seen: set[str] = set()

    for url in feeds:
        try:
            feed = feedparser.parse(url)
            source = feed.feed.get("title", url.split("/")[2])
            for item in feed.entries[:40]:
                title = plain(item.get("title", ""))
                link = item.get("link", "")
                if not title or not link or link in seen:
                    continue
                date = published(item)
                if date < cutoff:
                    continue
                summary = plain(
                    item.get("summary", item.get("description", ""))
                )[:1000]
                text = (title + " " + summary).lower()
                score = sum(
                    3 if keyword in title.lower() else 1
                    for keyword in keywords
                    if keyword in text
                )
                if score:
                    stories.append(
                        {
                            "title": title,
                            "summary": summary,
                            "url": link,
                            "source": source,
                            "published": date.isoformat(),
                            "score": score,
                        }
                    )
                    seen.add(link)
        except Exception as exc:
            print(f"[WARN] Feed unavailable: {url}: {exc}")

    stories.sort(
        key=lambda story: (story["score"], story["published"]),
        reverse=True,
    )
    if not stories:
        raise RuntimeError(
            "No matching recent stories. Check RSS_FEEDS or increase "
            "MAX_STORY_AGE_HOURS."
        )
    return stories[0]


def fallback_script(story: dict) -> dict:
    summary = (
        story["summary"]
        or "This is a development worth watching. Open the source link for details."
    )[:420]
    narration = (
        f"Here is your AI tech update. {story['title']}. "
        f"According to {story['source']}, {summary} "
        "The key takeaway is to watch how this development affects AI users, "
        "developers, and businesses. Check the source link for the full report."
    )
    scenes = [
        {"heading": "AI TECH UPDATE", "caption": story["title"]},
        {"heading": "WHAT WE KNOW", "caption": summary[:220]},
        {
            "heading": "WHY IT MATTERS",
            "caption": (
                "A development to watch for AI users, developers, and businesses."
            ),
        },
        {
            "heading": "FOLLOW FOR MORE",
            "caption": "Daily AI and technology updates",
        },
    ]
    return {
        "title": story["title"],
        "narration": narration,
        "scenes": scenes,
    }


def make_script(story: dict) -> dict:
    if os.getenv("USE_OLLAMA", "false").lower() != "true":
        return fallback_script(story)

    prompt = (
        "Write a factual voiceover for a 60-second vertical short, around "
        "120-135 words. Use only facts in the supplied story; do not invent "
        "numbers or quotes. Return JSON with keys title, narration, scenes; "
        "scenes is four objects with heading and caption.\n"
        f"Headline: {story['title']}\nPublisher: {story['source']}\n"
        f"Summary: {story['summary']}\nURL: {story['url']}"
    )
    try:
        response = requests.post(
            os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            + "/api/generate",
            json={
                "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
            timeout=120,
        )
        response.raise_for_status()
        data = json.loads(response.json()["response"])
        if not isinstance(data.get("narration"), str):
            raise ValueError("Model response has no narration string")
        if not isinstance(data.get("scenes"), list):
            raise ValueError("Model response has no scenes array")
        data["scenes"] = data["scenes"][:4]
        return data
    except Exception as exc:
        print(f"[WARN] Ollama unavailable; using template script: {exc}")
        return fallback_script(story)


async def tts(text: str, path: Path) -> None:
    communicate = edge_tts.Communicate(
        text=text,
        voice=os.getenv("TTS_VOICE", "en-IN-PrabhatNeural"),
        rate=os.getenv("TTS_RATE", "+12%"),
        pitch=os.getenv("TTS_PITCH", "+0Hz"),
    )
    await communicate.save(str(path))


def font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf"
        if bold
        else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Bold.ttf"
        if bold
        else "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_text(draw, text: str, fnt, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in (text or "").split():
        test = (current + " " + word).strip()
        if draw.textbbox((0, 0), test, font=fnt)[2] <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:8]


def make_card(
    path: Path,
    heading: str,
    caption: str,
    source: str,
    index: int,
    total: int,
    width: int,
    height: int,
) -> None:
    image = Image.new("RGB", (width, height), (12, 18, 38))
    draw = ImageDraw.Draw(image)
    margin = int(width * 0.085)
    draw.rounded_rectangle(
        (margin, int(height * 0.08), width - margin, int(height * 0.12)),
        radius=18,
        fill=(0, 205, 185),
    )
    draw.text(
        (margin, int(height * 0.15)),
        "THE DAILY SIGNAL  /  AI + TECH",
        font=font(int(width * 0.032), True),
        fill=(100, 235, 220),
    )
    draw.text(
        (margin, int(height * 0.22)),
        heading.upper()[:40],
        font=font(int(width * 0.055), True),
        fill=(255, 205, 90),
    )
    body_font = font(int(width * 0.062), True)
    y = int(height * 0.32)
    for line in wrap_text(draw, caption, body_font, width - 2 * margin):
        draw.text(
            (margin, y),
            line,
            font=body_font,
            fill=(248, 250, 255),
            stroke_width=1,
            stroke_fill=(8, 12, 28),
        )
        y += int(width * 0.09)
    draw.rounded_rectangle(
        (
            margin,
            int(height * 0.82),
            width - margin,
            int(height * 0.895),
        ),
        radius=20,
        fill=(24, 34, 58),
        outline=(76, 100, 130),
        width=2,
    )
    draw.text(
        (margin + 20, int(height * 0.835)),
        f"STORY {index}/{total}",
        font=font(int(width * 0.03), True),
        fill=(0, 220, 195),
    )
    draw.text(
        (margin + 20, int(height * 0.865)),
        source[:46],
        font=font(int(width * 0.025)),
        fill=(220, 230, 242),
    )
    draw.text(
        (margin, int(height * 0.93)),
        "VERIFY THE SOURCE  •  FOLLOW FOR MORE",
        font=font(int(width * 0.024), True),
        fill=(185, 199, 220),
    )
    image.save(path)


def run_ffmpeg(args: list[str]) -> None:
    # Keep FFmpeg diagnostics visible in GitHub Actions logs when a render fails.
    subprocess.run(args, check=True)


def ffprobe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found. Install FFmpeg.")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def render(
    story: dict,
    scenes: list[dict],
    audio_path: Path,
    video_path: Path,
    width: int,
    height: int,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found. Install FFmpeg and verify PATH.")

    # Build a 60-second slideshow using image inputs directly. This avoids
    # encoding multiple MP4 files and then concatenating those MP4 streams.
    work = video_path.parent / "render_tmp"
    work.mkdir(parents=True, exist_ok=True)
    image_paths: list[Path] = []

    for index, scene in enumerate(scenes[:4]):
        image_path = work / f"scene_{index + 1:02d}.png"
        make_card(
            image_path,
            str(scene.get("heading", "AI UPDATE")),
            str(scene.get("caption", "")),
            story["source"],
            index + 1,
            min(len(scenes), 4),
            width,
            height,
        )
        image_paths.append(image_path)

    if not image_paths:
        raise RuntimeError("No scene cards were generated.")

    concat_path = work / "images.txt"
    entries = []
    for image_path in image_paths:
        entries.append(f"file '{image_path.resolve().as_posix()}'\\nduration 15\\n")
    entries.append(f"file '{image_paths[-1].resolve().as_posix()}'\\n")
    concat_path.write_text("".join(entries), encoding="utf-8")

    audio_duration = ffprobe_duration(audio_path)
    atempo = min(1.5, max(1.0, audio_duration / 59.0))
    audio_filter = f"atempo={atempo:.5f},apad,atrim=duration=60"

    run_ffmpeg(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            f"scale={width}:{height},fps=30,format=yuv420p",
            "-af",
            audio_filter,
            "-t",
            "60",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(video_path),
        ]
    )

def main() -> None:
    output = Path(os.getenv("OUTPUT_DIR", "output"))
    output.mkdir(parents=True, exist_ok=True)
    print("[1/4] Collecting news...")
    story = get_story()
    print("Selected:", story["title"], "|", story["source"])

    script = make_script(story)
    scenes = script.get("scenes", [])[:4]
    while len(scenes) < 4:
        scenes.append(
            {"heading": "AI TECH UPDATE", "caption": story["title"]}
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    slug = (
        re.sub(r"[^a-zA-Z0-9]+", "-", story["title"].lower()).strip("-")[:48]
        or "ai-news"
    )
    stem = f"{timestamp}-{slug}"
    narration = str(script.get("narration", "")).strip()
    if not narration:
        raise RuntimeError("Generated narration is empty.")

    audio_path = output / f"{stem}-voice.mp3"
    print("[2/4] Generating voice-over...")
    asyncio.run(tts(narration, audio_path))

    script_path = output / f"{stem}.json"
    script_path.write_text(
        json.dumps(
            {
                "title": script.get("title", story["title"]),
                "narration": narration,
                "scenes": scenes,
                "source": story,
                "review_required": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    video_path = output / f"{stem}.mp4"
    print("[3/4] Rendering vertical video...")
    render(
        story,
        scenes,
        audio_path,
        video_path,
        env_int("VIDEO_WIDTH", 1080),
        env_int("VIDEO_HEIGHT", 1920),
    )

    (output / f"{stem}-source.txt").write_text(
        f"Headline: {story['title']}\n"
        f"Publisher: {story['source']}\n"
        f"Source URL: {story['url']}\n\n"
        "Review claims and audio before publishing.\n",
        encoding="utf-8",
    )
    print("[4/4] Complete:", video_path.resolve())
    print("Script:", script_path.resolve())
    print("Source:", story["url"])


if __name__ == "__main__":
    main()
