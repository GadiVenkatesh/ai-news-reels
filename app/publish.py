"""Prepare and publish generated AI news reels to YouTube Shorts and Instagram Reels."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(os.getenv("OUTPUT_DIR", "output"))
GRAPH_VERSION = os.getenv("META_GRAPH_API_VERSION", "vXX.X")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
REPORT = ROOT / "publishing-report.json"
TIMEOUT = (20, 180)


def require_env(*names: str) -> None:
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))


def load_generated() -> tuple[Path, dict[str, Any]]:
    videos = sorted(ROOT.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        raise FileNotFoundError("No generated MP4 found in output/")
    video = videos[0]
    metadata_path = video.with_suffix(".json")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata JSON not found next to {video.name}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = metadata.get("source") or {}
    if not source.get("url") or not source.get("source"):
        raise ValueError("Generated metadata must contain source.url and source.source")
    return video, metadata


def make_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    lang = os.getenv("LANGUAGE", "te").lower()
    title = re.sub(r"\s+", " ", str(metadata.get("title") or "AI News Update")).strip()
    title = title[:95]
    source = metadata["source"]
    publisher = str(source.get("source", "Original source"))
    source_url = str(source.get("url", ""))
    tags = [
        "AI", "ArtificialIntelligence", "Technology", "TechNews",
        "AIUpdates", "MachineLearning", "Shorts", "Reels",
    ]
    if lang == "te":
        caption = (
            f"🚀 తాజా AI & టెక్నాలజీ అప్‌డేట్!\n\n"
            f"{title}\n\n"
            f"ఈ వార్త ఎందుకు ముఖ్యమో 60 సెకన్లలో తెలుసుకోండి.\n"
            f"మూలం: {publisher}\n"
            f"పూర్తి కథనం: {source_url}\n\n"
            "#TeluguTech #AITelugu #TechNews #AIUpdates #ArtificialIntelligence "
            "#Technology #MachineLearning #TeluguReels #TeluguShorts #DailyTech"
        )
    else:
        caption = (
            f"🚀 Your 60-second AI & technology briefing.\n\n"
            f"{title}\n\n"
            f"Why it matters, explained simply.\n"
            f"Source: {publisher}\n"
            f"Read the full report: {source_url}\n\n"
            "#AI #TechNews #ArtificialIntelligence #AIUpdates #Technology "
            "#MachineLearning #TechReels #YouTubeShorts #DailyTech"
        )
    description = (
        caption + "\n\n"
        "News summary for education and information. Details may evolve; "
        "please read the original source linked above. "
        "All trademarks and article rights belong to their respective owners."
    )
    return {
        "title": title + (" | AI News #Shorts" if len(title) < 75 else ""),
        "caption": caption[:2200],
        "description": description[:4900],
        "tags": tags,
        "language": lang,
        "source_url": source_url,
        "publisher": publisher,
    }


def write_report(report: dict[str, Any]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare() -> None:
    video, data = load_generated()
    meta = make_metadata(data)
    (ROOT / "social-metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = {
        "video": video.name,
        "video_bytes": video.stat().st_size,
        "metadata_file": "social-metadata.json",
        "youtube": {"status": "pending"},
        "instagram": {"status": "pending"},
    }
    write_report(report)
    print(f"Prepared publishing metadata for {video.name}")


def youtube_upload() -> None:
    require_env("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    video, _ = load_generated()
    meta = json.loads((ROOT / "social-metadata.json").read_text(encoding="utf-8"))
    credentials = Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    credentials.refresh(Request())
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": os.getenv("YOUTUBE_CATEGORY_ID", "28"),
            "defaultLanguage": "te" if meta["language"] == "te" else "en",
        },
        "status": {
            "privacyStatus": os.getenv("YOUTUBE_PRIVACY_STATUS", "private"),
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk(num_retries=5)
        if status:
            print(f"YouTube upload: {int(status.progress() * 100)}%")
    video_id = response["id"]
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    report["youtube"] = {
        "status": "uploaded",
        "video_id": video_id,
        "url": f"https://www.youtube.com/shorts/{video_id}",
        "privacy_status": body["status"]["privacyStatus"],
    }
    write_report(report)
    print(f"YouTube upload complete: https://www.youtube.com/shorts/{video_id}")


def s3_client():
    import boto3
    return boto3.client("s3", region_name=os.getenv("AWS_REGION"))


def host_video() -> None:
    require_env("S3_BUCKET", "AWS_REGION")
    video, _ = load_generated()
    key = f"ai-news-reels/{video.name}"
    s3 = s3_client()
    s3.upload_file(
        str(video),
        os.environ["S3_BUCKET"],
        key,
        ExtraArgs={"ContentType": "video/mp4", "CacheControl": "public, max-age=3600"},
    )
    # A short-lived signed URL is publicly fetchable by Meta during processing.
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": os.environ["S3_BUCKET"], "Key": key},
        ExpiresIn=6 * 60 * 60,
    )
    (ROOT / "instagram-video-url.txt").write_text(url, encoding="utf-8")
    (ROOT / "s3-object-key.txt").write_text(key, encoding="utf-8")
    print("Uploaded video to temporary S3 object and generated a 6-hour URL.")


def graph_request(method: str, path: str, **kwargs) -> dict[str, Any]:
    response = requests.request(method, f"{GRAPH_BASE}/{path.lstrip('/')}", timeout=TIMEOUT, **kwargs)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text[:1000]}
    if not response.ok or "error" in payload:
        raise RuntimeError(f"Instagram Graph API error ({response.status_code}): {payload}")
    return payload


def instagram_publish() -> None:
    require_env("INSTAGRAM_USER_ID", "INSTAGRAM_ACCESS_TOKEN")
    if GRAPH_VERSION == "vXX.X":
        raise RuntimeError("Set META_GRAPH_API_VERSION to a currently supported Meta Graph API version.")
    video, _ = load_generated()
    url_file = ROOT / "instagram-video-url.txt"
    if not url_file.exists():
        raise FileNotFoundError("Run --host-video before --instagram")
    video_url = url_file.read_text(encoding="utf-8").strip()
    meta = json.loads((ROOT / "social-metadata.json").read_text(encoding="utf-8"))
    token = os.environ["INSTAGRAM_ACCESS_TOKEN"]
    # Instagram media must meet Meta's documented Reels specifications.
    if video.stat().st_size > 1_000_000_000:
        raise ValueError("Instagram Reels publishing supports a maximum 1 GB video file.")
    create = graph_request(
        "POST",
        f"{os.environ['INSTAGRAM_USER_ID']}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": meta["caption"],
            "share_to_feed": "true",
            "access_token": token,
        },
    )
    container_id = create["id"]
    status = ""
    for attempt in range(30):
        state = graph_request(
            "GET", container_id,
            params={"fields": "status_code,status", "access_token": token},
        )
        status = state.get("status_code", "")
        print(f"Instagram media container: {status}")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram media processing failed: {state}")
        time.sleep(10 if attempt < 6 else 20)
    else:
        raise TimeoutError("Instagram media container did not finish processing within 10 minutes.")
    published = graph_request(
        "POST",
        f"{os.environ['INSTAGRAM_USER_ID']}/media_publish",
        data={"creation_id": container_id, "access_token": token},
    )
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    report["instagram"] = {
        "status": "published",
        "container_id": container_id,
        "media_id": published.get("id"),
        "caption": meta["caption"],
    }
    write_report(report)
    print(f"Instagram Reel published. Media ID: {published.get('id')}")


def cleanup() -> None:
    key_file = ROOT / "s3-object-key.txt"
    if not key_file.exists() or not os.getenv("S3_BUCKET"):
        print("No temporary S3 object key found; skipping cleanup.")
        return
    s3_client().delete_object(
        Bucket=os.environ["S3_BUCKET"],
        Key=key_file.read_text(encoding="utf-8").strip(),
    )
    print("Deleted temporary S3 object.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--youtube", action="store_true")
    parser.add_argument("--host-video", action="store_true")
    parser.add_argument("--instagram", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.youtube:
        youtube_upload()
    elif args.host_video:
        host_video()
    elif args.instagram:
        instagram_publish()
    elif args.cleanup:
        cleanup()
    else:
        parser.error("Select one publishing action")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
