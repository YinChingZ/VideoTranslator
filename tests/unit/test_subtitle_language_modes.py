import pytest

from app.core.subtitle import SubtitleProcessor, SubtitleSegment


@pytest.fixture
def processor(monkeypatch):
    monkeypatch.setattr(SubtitleProcessor, "_validate_dependencies", lambda self: None)
    instance = SubtitleProcessor()
    instance.segments = [
        SubtitleSegment(0.0, 1.5, "Hello", "你好", index=1),
        SubtitleSegment(2.0, 3.0, "World", "世界", index=2),
    ]
    return instance


@pytest.mark.parametrize(
    ("format_name", "mode", "included", "excluded"),
    [
        (format_name, mode, included, excluded)
        for format_name in ("srt", "vtt", "ass")
        for mode, included, excluded in (
            ("original_only", ["Hello", "World"], ["你好", "世界"]),
            ("translation_only", ["你好", "世界"], ["Hello", "World"]),
            ("bilingual", ["Hello", "World", "你好", "世界"], []),
        )
    ],
)
def test_text_export_honors_language_mode(
    processor, tmp_path, format_name, mode, included, excluded
):
    output = tmp_path / f"subtitles-{mode}.{format_name}"

    saved = processor.save_to_file(str(output), format_name, language_mode=mode)

    assert saved == str(output)
    content = output.read_text(encoding="utf-8-sig")
    for text in included:
        assert text in content
    for text in excluded:
        assert text not in content


def test_translation_only_falls_back_to_original_when_translation_is_empty(
    processor, tmp_path
):
    processor.segments[0].translated_text = ""
    output = tmp_path / "fallback.vtt"

    processor.save_to_file(str(output), "vtt", language_mode="translation_only")

    assert "Hello" in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("mode", ["original_only", "translation_only", "bilingual"])
def test_sbv_export_and_round_trip(processor, tmp_path, mode):
    output = tmp_path / f"subtitle-{mode}.sbv"

    processor.save_to_file(str(output), language_mode=mode)
    loaded = SubtitleProcessor().load_from_file(str(output))

    assert len(loaded) == 2
    assert loaded[0].start_time == pytest.approx(0.0)
    assert loaded[0].end_time == pytest.approx(1.5)
    content = output.read_text(encoding="utf-8")
    assert "0:00:00.000,0:00:01.500" in content
    if mode == "original_only":
        assert "Hello" in content and "你好" not in content
    elif mode == "translation_only":
        assert "你好" in content and "Hello" not in content
    else:
        assert "Hello\n你好" in content


def test_invalid_language_mode_is_rejected(processor, tmp_path):
    with pytest.raises(ValueError, match="language mode"):
        processor.save_to_file(
            str(tmp_path / "bad.srt"),
            "srt",
            language_mode="invented",
        )
