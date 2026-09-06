from talkback_validator import runtime


def test_a_platform_without_a_build_is_reported_not_guessed(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Plan9")
    monkeypatch.setattr("platform.machine", lambda: "risc")
    assert runtime.asset_name() is None


def test_this_platform_has_a_runtime_build():
    assert runtime.asset_name(), "no Ollama build mapped for the test machine"


def test_install_refuses_an_unsupported_platform(monkeypatch):
    import pytest

    monkeypatch.setattr("platform.system", lambda: "Plan9")
    monkeypatch.setattr("platform.machine", lambda: "risc")
    with pytest.raises(runtime.RuntimeUnavailable):
        runtime.install_runtime(log=lambda *_: None)


def test_the_server_address_is_always_loopback(monkeypatch):
    monkeypatch.setattr(runtime, "_port_answers", lambda port, timeout=0.4: True)
    assert runtime.endpoint().startswith("http://127.0.0.1:")


def test_no_endpoint_when_nothing_is_listening(monkeypatch):
    monkeypatch.setattr(runtime, "_port_answers", lambda port, timeout=0.4: False)
    assert runtime.endpoint() is None
