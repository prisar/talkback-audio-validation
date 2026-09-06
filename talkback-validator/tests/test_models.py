import pytest

from talkback_validator import models
from talkback_validator.cli import _RunController


def test_every_catalogue_entry_declares_what_it_can_observe():
    for spec in models.CATALOGUE:
        assert spec.roles or spec.blocked, f"{spec.id} claims no role and no reason"


def test_roles_are_only_ever_audio_or_vision():
    for spec in models.CATALOGUE:
        assert set(spec.roles) <= {models.AUDIO, models.VISION}


def test_a_blocked_model_never_reports_itself_installed(monkeypatch):
    """Blocked means it cannot run here. Reporting it installed would let a
    tester select something that then fails mid-capture."""
    monkeypatch.setattr(models.runtime, "installed_models", lambda: ["gpt-oss:20b"])
    rows = {row["id"]: row for row in models.status()}
    assert rows["gpt-oss:20b"]["blocked"]
    assert rows["gpt-oss:20b"]["installed"] is False


def test_installing_a_blocked_model_is_refused():
    spec = models.BY_ID["gpt-oss:20b"]
    with pytest.raises(RuntimeError):
        models.install(spec, log=lambda *_: None)


def test_vision_role_lists_only_screen_readers():
    ids = {spec.id for spec in models.for_role(models.VISION)}
    assert "gemma3:4b" in ids
    assert "small.en" not in ids


def test_ollama_tag_suffixes_still_count_as_installed(monkeypatch):
    """Ollama reports names like 'gemma3:4b-it-q4_K_M'; a strict equality
    check would offer to download a model that is already on disk."""
    monkeypatch.setattr(
        models.runtime, "installed_models", lambda: ["gemma3:4b-it-q4_K_M"]
    )
    rows = {row["id"]: row for row in models.status()}
    assert rows["gemma3:4b"]["installed"] is True


def test_install_rejects_a_model_outside_the_catalogue(tmp_path):
    assert _RunController(tmp_path).start_install("rm -rf /") is False


def test_install_launches_the_documented_command(tmp_path, monkeypatch):
    seen = {}

    class Fake:
        stdout = None
        returncode = 0

        def poll(self):
            return 0

        def wait(self):
            return 0

    monkeypatch.setattr(
        "subprocess.Popen",
        lambda command, **kwargs: (seen.__setitem__("c", command), Fake())[1],
    )
    assert _RunController(tmp_path).start_install("gemma3:4b") is True
    assert seen["c"][-3:] == ["models", "install", "gemma3:4b"]


def test_a_run_and_an_install_cannot_overlap(tmp_path, monkeypatch):
    """They share the machine; a 3 GB download during a capture would corrupt
    the recording the run depends on."""

    class Busy:
        stdout = None
        returncode = None

        def poll(self):
            return None

        def wait(self):
            return None

    monkeypatch.setattr("subprocess.Popen", lambda command, **kwargs: Busy())
    controller = _RunController(tmp_path)
    assert controller.start_install("gemma3:4b") is True
    assert controller.start({"fields": ["program"]}) is False


def test_cpu_hosts_are_warned_about_vision_speed(monkeypatch):
    """Measured on this machine: 263-306s per screenshot, one value misread."""
    monkeypatch.setattr(models, "cpu_only", lambda: True)
    rows = {row["id"]: row for row in models.status()}
    assert "4-5 minutes" in rows["gemma3:4b"]["note"]
    assert "4-5 minutes" not in rows["small.en"]["note"]


def test_no_speed_warning_where_the_gpu_does_the_work(monkeypatch):
    monkeypatch.setattr(models, "cpu_only", lambda: False)
    rows = {row["id"]: row for row in models.status()}
    assert "4-5 minutes" not in rows["gemma3:4b"]["note"]


def test_removing_a_whisper_model_deletes_its_cache(tmp_path, monkeypatch):
    """Whisper removal used to be a silent no-op: it reported success and
    left 464 MB on disk."""
    cache = tmp_path / ".cache" / "huggingface" / "hub"
    target = cache / "models--Systran--faster-whisper-small.en"
    target.mkdir(parents=True)
    (target / "model.bin").write_bytes(b"weights")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    assert models.remove(models.BY_ID["small.en"], log=lambda *_: None) is True
    assert not target.exists()


def test_removing_an_absent_whisper_model_reports_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert models.remove(models.BY_ID["tiny.en"], log=lambda *_: None) is False


def test_removal_reports_failure_when_the_server_cannot_start(monkeypatch):
    """A remove that cannot reach the store must not claim the model is gone."""
    def refuse(**kwargs):
        raise models.runtime.RuntimeUnavailable("no runtime")

    monkeypatch.setattr(models.runtime, "serve", refuse)
    assert models.remove(models.BY_ID["gemma3:4b"], log=lambda *_: None) is False
