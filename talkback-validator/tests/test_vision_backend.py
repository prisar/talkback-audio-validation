from talkback_validator.transcription.vision import LocalVisionBackend, tidy


def test_a_bare_value_survives_untouched():
    assert tidy("42%") == "42%"


def test_narration_is_stripped_to_the_value():
    assert tidy("The value is 42%.") == "42%"
    assert tidy("shown: -3") == "-3"


def test_only_the_first_line_is_kept():
    assert tidy("85%\nThis is a battery indicator.") == "85%"


def test_an_empty_answer_stays_empty():
    assert tidy("   ") == ""


def test_the_vision_backend_cannot_transcribe_audio():
    """A screen reader that silently returned nothing for audio would look
    like a quiet channel rather than an absent one."""
    assert not hasattr(LocalVisionBackend(), "transcribe")


def test_failure_is_reported_not_raised(monkeypatch):
    backend = LocalVisionBackend()
    monkeypatch.setattr(
        "talkback_validator.runtime.serve",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("server down")),
    )
    result = backend.read_screen_value("/nonexistent.png")
    assert result.error and "server down" in result.error
    assert result.text == ""


def test_a_running_server_counts_even_without_a_local_binary(monkeypatch):
    """Observed for real: available() said False while read_screen_value()
    was succeeding against a server started from elsewhere."""
    monkeypatch.setattr("talkback_validator.runtime.binary", lambda: None)
    monkeypatch.setattr(
        "talkback_validator.runtime.endpoint", lambda: "http://127.0.0.1:11435"
    )
    monkeypatch.setattr(
        "talkback_validator.runtime.installed_models", lambda: ["gemma3:4b"]
    )
    assert LocalVisionBackend("gemma3:4b").available() is True


def test_unavailable_when_there_is_no_runtime_at_all(monkeypatch):
    monkeypatch.setattr("talkback_validator.runtime.binary", lambda: None)
    monkeypatch.setattr("talkback_validator.runtime.endpoint", lambda: None)
    assert LocalVisionBackend("gemma3:4b").available() is False
