"""The visual value can come from tesseract OCR or from asking the model to
read the same cropped screenshot -- cli._capture_field-adjacent code picks
one based on what the backend supports. Both paths must stay independent
enough that a scoring bug in one cannot be mistaken for the other.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from talkback_validator.transcription import gemini as gemini_module
from talkback_validator.transcription.gemini import GeminiBackend
from talkback_validator.visual import crop_region


def _make_screenshot(path: Path) -> None:
    Image.new("RGB", (200, 100), color="white").save(path)


def test_crop_region_saves_a_cropped_upscaled_image(tmp_path):
    shot = tmp_path / "shot.png"
    _make_screenshot(shot)
    out = tmp_path / "crop.png"
    result = crop_region(shot, (10, 10, 60, 40), out)
    assert result == out
    assert out.exists()
    cropped = Image.open(out)
    # padded by 6px each side then upscaled 3x: (60-10+12)*3, (40-10+12)*3
    assert cropped.size == (186, 126)


def test_read_screen_value_uses_the_screen_prompt_and_png_mime(monkeypatch, tmp_path):
    shot = tmp_path / "crop.png"
    _make_screenshot(shot)

    captured = {}

    class _FakePart:
        @staticmethod
        def from_bytes(data, mime_type):
            captured["mime_type"] = mime_type
            return SimpleNamespace()

    class _FakeTypes:
        Part = _FakePart
        GenerateContentConfig = lambda **kw: SimpleNamespace(**kw)

    class _FakeModels:
        def generate_content(self, model, contents, config):
            captured["prompt"] = contents[0]
            return SimpleNamespace(text="42%")

    class _FakeClient:
        def __init__(self, api_key):
            self.models = _FakeModels()

    fake_genai = SimpleNamespace(Client=_FakeClient)
    monkeypatch.setattr(gemini_module, "genai", fake_genai, raising=False)
    monkeypatch.setitem(
        __import__("sys").modules, "google.genai", SimpleNamespace(types=_FakeTypes)
    )
    monkeypatch.setitem(__import__("sys").modules, "google", SimpleNamespace(genai=fake_genai))

    backend = GeminiBackend(api_key="fake-key")
    result = backend.read_screen_value(shot)

    assert result.text == "42%"
    assert captured["mime_type"] == "image/png"
    assert captured["prompt"] == gemini_module.SCREEN_PROMPT
    assert captured["prompt"] != gemini_module.PROMPT


def test_read_screen_value_reports_missing_api_key():
    backend = GeminiBackend(api_key=None)
    backend._api_key = None
    result = backend.read_screen_value("does-not-matter.png")
    assert result.error == "GEMINI_API_KEY is not set"


def test_transcribe_and_read_screen_value_are_independent_prompts():
    # Guards the design invariant directly: whatever _ask sends for audio
    # must not be the same prompt used for reading the screen, so a screen
    # read can never be mistaken for corroborating its own transcript.
    assert gemini_module.PROMPT != gemini_module.SCREEN_PROMPT


def test_cloud_backend_reads_its_own_screenshots():
    from talkback_validator.cli import _screen_reader
    from talkback_validator.transcription.gemini import GeminiBackend

    backend = GeminiBackend(api_key="unused")
    assert _screen_reader(backend) is backend


def test_local_audio_backend_delegates_screen_reading_to_the_cloud(monkeypatch):
    """A speech model cannot read a screenshot, so the visual channel must be
    served by something else rather than silently going unread."""
    from talkback_validator.cli import _screen_reader
    from talkback_validator.transcription.local import LocalWhisperBackend

    monkeypatch.setenv("GEMINI_API_KEY", "unused")
    reader = _screen_reader(LocalWhisperBackend())
    assert reader is not None
    assert reader.name == "gemini"


def test_screen_reading_falls_back_to_ocr_when_no_cloud_key(monkeypatch):
    from talkback_validator.cli import _screen_reader
    from talkback_validator.transcription.local import LocalWhisperBackend

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert _screen_reader(LocalWhisperBackend()) is None
