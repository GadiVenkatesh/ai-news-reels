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


def extract_image_url(entry) -> str:
    """Best-effort thumbnail discovery from common RSS image fields."""
    for field in ("media_thumbnail", "media_content", "image", "thumbnail"):
        value = entry.get(field)
        if isinstance(value, list) and value:
            value = value[0]
        if isinstance(value, dict):
            url = value.get("url") or value.get("href")
            if url and str(url).startswith(("https://", "http://")):
                return str(url)
    for enclosure in entry.get("enclosures", []) or []:
        if isinstance(enclosure, dict):
            url = enclosure.get("href") or enclosure.get("url")
            mime = enclosure.get("type", "")
            if url and (mime.startswith("image/") or re.search(r"\\.(jpg|jpeg|png|webp)(?:\\?|$)", url, re.I)):
                return str(url)
    html = " ".join(
        str(entry.get(key, ""))
        for key in ("summary", "description", "content")
    )
    match = re.search(r"""<img[^>]+src=["']([^"']+)["']""", html, re.I)
    if match and match.group(1).startswith(("https://", "http://")):
        return match.group(1)
    return ""


def download_story_image(story: dict, destination: Path) -> Path | None:
    """Download the article thumbnail when the feed provides one."""
    url = story.get("image_url")
    if not url:
        return None
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "ai-news-reels/1.0 (+RSS thumbnail fetch)"},
        )
        response.raise_for_status()
        from io import BytesIO
        image = Image.open(BytesIO(response.content)).convert("RGB")
        image.thumbnail((1080, 1920))
        image.save(destination, format="JPEG", quality=90)
        return destination
    except Exception as exc:
        print(f"[WARN] Could not download article thumbnail: {exc}")
        return None


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
                            "image_url": extract_image_url(item),
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


def translate_text(text: str, target_language: str) -> str:
    """Translate a short news field using Google's public translation endpoint."""
    if not text.strip() or target_language == "en":
        return text
    response = requests.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "auto", "tl": "te", "dt": "t", "q": text},
        timeout=25,
        headers={"User-Agent": "Mozilla/5.0 ai-news-reels/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    translated = "".join(part[0] for part in payload[0] if part and part[0])
    if not translated.strip():
        raise RuntimeError("Translation returned empty Telugu text.")
    return translated.strip()


def localize_story(story: dict, language: str) -> dict:
    localized = dict(story)
    if language == "te":
        localized["title"] = translate_text(story["title"], language)
        localized["summary"] = translate_text(story["summary"], language)
    return localized


def fallback_script(story: dict, language: str = "en") -> dict:
    summary = (
        story["summary"]
        or ("ఈ వార్తపై మరిన్ని వివరాల కోసం మూల కథనాన్ని చూడండి." if language == "te"
            else "This is a development worth watching. Open the source link for details.")
    )[:420]
    if language == "te":
        narration = (
            f"ఇది మీ రోజువారీ ఏఐ టెక్నాలజీ వార్త. {story['title']}. "
            f"{story['source']} కథనం ప్రకారం, {summary} "
            "ఈ పరిణామం ఏఐ వినియోగదారులు, డెవలపర్లు, వ్యాపారాలపై ఎలా ప్రభావం చూపుతుందో గమనించాలి. "
            "ఈ వార్తలోని వివరాలు ప్రచురణ సమయంలో అందుబాటులో ఉన్న సమాచారంపై ఆధారపడి ఉన్నాయి. "
            "తదుపరి అధికారిక ప్రకటనలు, కొత్త వివరాలు వచ్చినప్పుడు పరిస్థితి మారవచ్చు. "
            "ఈ టెక్నాలజీ అందుబాటులోకి వచ్చే సమయం, ఉపయోగించే విధానం, నిజ జీవితంలో దాని ఫలితాలను గమనించండి. "
            "ఏదైనా నిర్ణయం తీసుకునే ముందు అసలు వార్తా మూలాన్ని పరిశీలించండి. "
            "మరిన్ని వివరాల కోసం మూల కథనాన్ని చూడండి."
        )
        scenes = [
            {"heading": "ఏఐ టెక్ అప్‌డేట్", "caption": story["title"]},
            {"heading": "మనకు తెలిసిన విషయం", "caption": summary[:220]},
            {"heading": "ఇది ఎందుకు ముఖ్యం", "caption": "ఏఐ వినియోగదారులు, డెవలపర్లు, వ్యాపారాలకు ఈ వార్త ముఖ్యం."},
            {"heading": "మరిన్ని వార్తల కోసం", "caption": "రోజువారీ ఏఐ మరియు టెక్నాలజీ అప్‌డేట్స్"},
        ]
    else:
        narration = (
            f"Here is your AI tech update. {story['title']}. "
            f"According to {story['source']}, {summary} "
            "The key takeaway is to watch how this development affects AI users, "
            "developers, and businesses. The details in this video reflect information "
            "available when the source report was published, and new official updates may change the picture. "
            "Watch for availability, practical results, and further announcements before drawing conclusions. "
            "Always read the original report before making decisions. We will continue to explain "
            "important AI and technology updates in simple terms. Check the source link for the full report."
        )
        scenes = [
            {"heading": "AI TECH UPDATE", "caption": story["title"]},
            {"heading": "WHAT WE KNOW", "caption": summary[:220]},
            {"heading": "WHY IT MATTERS", "caption": "A development to watch for AI users, developers, and businesses."},
            {"heading": "FOLLOW FOR MORE", "caption": "Daily AI and technology updates"},
        ]
    return {"title": story["title"], "narration": narration, "scenes": scenes}


def make_script(story: dict, language: str = "en") -> dict:
    if os.getenv("USE_OLLAMA", "false").lower() != "true":
        return fallback_script(story, language)

    language_name = "Telugu" if language == "te" else "English"
    prompt = (
        f"Write a factual {language_name} voiceover for exactly a 60-second vertical short, "
        "around 120-135 words. Use only facts in the supplied story; do not invent "
        "numbers or quotes. All narration and on-screen text must be in the requested language. "
        "Return JSON with keys title, narration, scenes; scenes is four objects with heading and caption.\n"
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
        return fallback_script(story, language)


async def tts(text: str, path: Path, language: str = "en") -> None:
    default_voice = "te-IN-ShrutiNeural" if language == "te" else "en-US-GuyNeural"
    communicate = edge_tts.Communicate(
        text=text,
        voice=os.getenv("TTS_VOICE", default_voice),
        rate=os.getenv("TTS_RATE", "+12%"),
        pitch=os.getenv("TTS_PITCH", "+0Hz"),
    )
    await communicate.save(str(path))


def font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf"
        if bold
        else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansTelugu-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf",
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
    photo_path: Path | None = None,
    language: str = "en",
) -> None:
    # Use the real article thumbnail as a full-bleed background when available.
    if photo_path and photo_path.exists():
        with Image.open(photo_path) as source_image:
            source_image = source_image.convert("RGB")
            src_ratio = source_image.width / source_image.height
            target_ratio = width / height
            if src_ratio > target_ratio:
                new_w = int(source_image.height * target_ratio)
                left = (source_image.width - new_w) // 2
                source_image = source_image.crop((left, 0, left + new_w, source_image.height))
            else:
                new_h = int(source_image.width / target_ratio)
                top = (source_image.height - new_h) // 2
                source_image = source_image.crop((0, top, source_image.width, top + new_h))
            image = source_image.resize((width, height))
        # Dark translucent overlay keeps white headline text readable.
        overlay = Image.new("RGBA", (width, height), (4, 10, 26, 145))
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    else:
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
        "రోజువారీ ఏఐ వార్తలు / టెక్" if language == "te" else "THE DAILY SIGNAL  /  AI + TECH",
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
        (f"వార్త {index}/{total}" if language == "te" else f"STORY {index}/{total}"),
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
        "మూలాన్ని పరిశీలించండి • మరిన్ని వార్తల కోసం" if language == "te" else "VERIFY THE SOURCE  •  FOLLOW FOR MORE",
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
    language: str = "en",
    duration: int = 60,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found. Install FFmpeg and verify PATH.")
    if duration != 60:
        raise ValueError("This project always renders exactly 60-second videos.")

    work = video_path.parent / "render_tmp"
    work.mkdir(parents=True, exist_ok=True)
    photo_path = download_story_image(story, work / "article-thumbnail.jpg")
    if photo_path:
        print("[INFO] Using the article thumbnail as the scene background.")
    else:
        print("[WARN] This feed item has no downloadable thumbnail; using designed cards.")

    selected_scenes = scenes[:4]
    while len(selected_scenes) < 4:
        selected_scenes.append({"heading": "AI TECH UPDATE", "caption": story["title"]})
    image_paths: list[Path] = []
    for index, scene in enumerate(selected_scenes):
        image_path = work / f"scene_{index + 1:02d}.png"
        make_card(
            image_path,
            str(scene.get("heading", "AI UPDATE")),
            str(scene.get("caption", "")),
            story["source"],
            index + 1,
            4,
            width,
            height,
            photo_path=photo_path,
            language=language,
        )
        image_paths.append(image_path)

    # Loop each still image as a 15-second, 30-fps stream and concatenate the
    # streams. This avoids concat-demuxer timestamps freezing a scene early.
    args = [ffmpeg, "-y"]
    for image_path in image_paths:
        args.extend(["-loop", "1", "-framerate", "30", "-t", "15", "-i", str(image_path)])
    args.extend(["-i", str(audio_path)])

    filters = []
    for index in range(4):
        filters.append(
            f"[{index}:v]scale={width}:{height},fps=30,format=yuv420p,"
            f"setsar=1,setpts=PTS-STARTPTS[v{index}]"
        )
    filters.append("[v0][v1][v2][v3]concat=n=4:v=1:a=0,trim=duration=60,setpts=PTS-STARTPTS[v]")

    audio_duration = ffprobe_duration(audio_path)
    # Keep the complete voice-over inside 60 seconds; pad silence only if it is shorter.
    atempo = min(2.0, max(0.5, audio_duration / 59.5))
    filters.append(f"[4:a]atempo={atempo:.5f},apad,atrim=duration=60,asetpts=PTS-STARTPTS[a]")
    args.extend([
        "-filter_complex", ";".join(filters),
        "-map", "[v]", "-map", "[a]",
        "-t", "60",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(video_path),
    ])
    run_ffmpeg(args)
    actual_duration = ffprobe_duration(video_path)
    if abs(actual_duration - 60.0) > 0.25:
        raise RuntimeError(f"Final MP4 is {actual_duration:.3f}s; expected exactly 60 seconds.")
    print(f"[INFO] Verified final MP4 duration: {actual_duration:.3f} seconds")

def main() -> None:
    output = Path(os.getenv("OUTPUT_DIR", "output"))
    output.mkdir(parents=True, exist_ok=True)
    print("[1/4] Collecting news...")
    language = os.getenv("LANGUAGE", "te").strip().lower()
    if language not in ("te", "en"):
        raise ValueError("LANGUAGE must be 'te' (Telugu) or 'en' (English).")
    story = get_story()
    story = localize_story(story, language)
    print("Selected:", story["title"], "|", story["source"], "| language:", language)

    script = make_script(story, language)
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
    asyncio.run(tts(narration, audio_path, language))

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
        language=language,
        duration=60,
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
