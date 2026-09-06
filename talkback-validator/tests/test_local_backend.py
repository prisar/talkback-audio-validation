import sys
import types

import pytest

from talkback_validator.transcription.local import LocalWhisperBackend


class _Segment:
    def __init__(self, text):
        self.text = text


def _fake_faster_whisper(monkeypatch, segments, info_language="en", fail=None):
    calls = {}

    class FakeModel:
        def __init__(self, model, device, compute_type):
            calls["init"] = (model, device, compute_type)

        def transcribe(self, path, **kwargs):
            calls["transcribe"] = (path, kwargs)
            if fail:
                raise fail
            info = types.SimpleNamespace(language=info_language)
            return (_Segment(s) for s in segments), info

    module = types.ModuleType("faster_whisper")
    module.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    return calls


def test_transcribe_joins_segments(monkeypatch):
    _fake_faster_whisper(monkeypatch, [" Left battery, ", " 85 percent. "])
    result = LocalWhisperBackend().transcribe("clip.wav")
    assert result.text == "Left battery, 85 percent."
    assert result.error is None
    assert result.backend == "whisper-local"


def test_transcribe_runs_offline_with_vad(monkeypatch):
    calls = _fake_faster_whisper(monkeypatch, ["ok"])
    LocalWhisperBackend().transcribe("clip.wav")
    _path, kwargs = calls["transcribe"]
    assert kwargs["vad_filter"] is True
    assert kwargs["temperature"] == 0.0
    assert calls["init"][1] == "cpu"


def test_model_is_configurable(monkeypatch):
    calls = _fake_faster_whisper(monkeypatch, ["ok"])
    LocalWhisperBackend(model="tiny.en").transcribe("clip.wav")
    assert calls["init"][0] == "tiny.en"


def test_model_loads_once_across_calls(monkeypatch):
    loads = []

    class FakeModel:
        def __init__(self, *args, **kwargs):
            loads.append(args)

        def transcribe(self, path, **kwargs):
            return iter([_Segment("x")]), types.SimpleNamespace(language="en")

    module = types.ModuleType("faster_whisper")
    module.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    backend = LocalWhisperBackend()
    backend.transcribe("a.wav")
    backend.transcribe("b.wav")
    assert len(loads) == 1


def test_failure_is_reported_not_raised(monkeypatch):
    _fake_faster_whisper(monkeypatch, [], fail=RuntimeError("decode failed"))
    result = LocalWhisperBackend().transcribe("clip.wav")
    assert result.text == ""
    assert "decode failed" in result.error


def test_missing_dependency_is_reported(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    result = LocalWhisperBackend().transcribe("clip.wav")
    assert result.error is not None


def test_backend_exposes_no_screen_reader():
    """The visual channel must not fall back to the audio model here: a
    speech model cannot read a screenshot, and silently returning nothing
    would look like agreement rather than an unavailable channel."""
    assert not hasattr(LocalWhisperBackend(), "read_screen_value")
