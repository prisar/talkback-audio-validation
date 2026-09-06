

def test_quota_exhaustion_is_not_reported_as_a_key_problem():
    """The 429 payload names no key, but it is what a tester sees when a run
    stops working, and it must not send them hunting for a broken credential."""
    from talkback_validator.transcription.gemini import explain

    raw = (
        '429 RESOURCE_EXHAUSTED. {"error": {"message": "You exceeded your current '
        'quota. Quota exceeded for metric: generate_content_free_tier_requests, '
        'limit: 20, model: gemini-3.8-flash", "details": [{"quotaValue": "20"}]}}'
    )
    message = explain(Exception(raw))
    assert "quota exhausted" in message
    assert "gemini-3.8-flash" in message
    assert "20 requests/day" in message
    assert "the key is valid" in message
    assert len(message) < 140


def test_other_errors_are_passed_through_unchanged():
    from talkback_validator.transcription.gemini import explain

    assert explain(Exception("connection reset by peer")) == "connection reset by peer"


def test_silent_audio_is_never_sent_to_the_model():
    """A generative model asked to transcribe silence invents speech rather
    than returning nothing, so the waveform measurement has to win."""
    import inspect

    from talkback_validator import cli

    source = inspect.getsource(cli._run_scenario)
    gate = source.index("if capture.silent:")
    call = source.index("backend.transcribe(capture.wav_path)")
    assert gate < call, "the silence check must guard the transcription call"
