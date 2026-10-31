from app.main import extract_image_url, fallback_script, plain


def test_fallback_script_structure():
    story = {
        "title": "A new AI tool",
        "summary": "It helps developers.",
        "source": "Example News",
        "url": "https://example.com",
    }
    result = fallback_script(story)
    assert "A new AI tool" in result["narration"]
    assert len(result["scenes"]) == 4
    assert all("heading" in scene and "caption" in scene for scene in result["scenes"])


def test_plain_removes_html_and_normalizes_whitespace():
    assert plain("<p>Hello</p>   <b>AI</b>") == "Hello AI"


def test_extract_image_from_rss_media_thumbnail():
    entry = {"media_thumbnail": [{"url": "https://example.com/thumb.jpg"}]}
    assert extract_image_url(entry) == "https://example.com/thumb.jpg"


def test_extract_image_from_summary_html():
    entry = {"summary": '<p>News</p><img src="https://example.com/news.png">'}
    assert extract_image_url(entry) == "https://example.com/news.png"
