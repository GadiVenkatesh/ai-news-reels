from app.main import fallback_script, plain


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
