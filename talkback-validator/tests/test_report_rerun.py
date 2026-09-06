import json

import pytest

from talkback_validator import reporting
from talkback_validator.cli import _RunController


def _run_with(cases, **extra):
    run = reporting.new_run({"backend": "gemini"})
    run["cases"] = cases
    run.update(extra)
    return run


def test_panel_offers_every_scenario_field_not_just_captured_ones():
    run = _run_with(
        [{"field": "left_battery", "status": "PASS"}],
        available_fields=["left_battery", "right_battery", "program"],
    )
    panel = reporting._rerun_panel(run)
    for name in ("left_battery", "right_battery", "program"):
        assert f"value='{name}'" in panel


def test_panel_preselects_the_fields_this_run_captured():
    run = _run_with(
        [{"field": "program", "status": "PASS"}],
        available_fields=["program", "left_volume"],
    )
    panel = reporting._rerun_panel(run)
    assert "value='program' checked" in panel
    assert "value='left_volume' checked" not in panel


def test_panel_reflects_the_backend_that_produced_the_run():
    run = _run_with([{"field": "program"}], available_fields=["program"])
    run["environment"]["backend"] = "whisper-local"
    assert "value='whisper' checked" in reporting._rerun_panel(run)


def test_panel_absent_when_there_is_nothing_to_rerun():
    assert reporting._rerun_panel(_run_with([])) == ""


def test_report_embeds_the_panel_and_its_script(tmp_path):
    run = _run_with(
        [{"field": "program", "status": "PASS", "id": "program-none"}],
        available_fields=["program"],
    )
    html = reporting.render(run, tmp_path).read_text()
    assert 'id="rerun-go"' in html
    assert "fetch('rerun'" in html
    assert "Run selected" in html


def test_panel_recovers_the_button_when_the_server_is_gone(tmp_path):
    """A dead server made fetch throw, leaving the button disabled forever
    with no explanation -- indistinguishable from a run that never ends."""
    run = _run_with([{"field": "program"}], available_fields=["program"])
    html = reporting.render(run, tmp_path).read_text()
    assert "catch (err)" in html
    assert "res.status === 409" in html


def test_controller_rejects_a_request_with_no_fields(tmp_path):
    assert _RunController(tmp_path).start({"fields": []}) is False


def test_controller_builds_the_command_from_the_selection(tmp_path, monkeypatch):
    seen = {}

    class FakeProcess:
        stdout = None
        returncode = 0

        def poll(self):
            return 0

        def wait(self):
            return 0

    def fake_popen(command, **kwargs):
        seen["command"] = command
        return FakeProcess()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    controller = _RunController(tmp_path)
    assert controller.start(
        {"fields": ["program", "left_volume"], "backend": "whisper",
         "defect": "swap_sides", "control": True}
    )
    command = seen["command"]
    assert "--backend" in command and "whisper" in command
    assert command[command.index("--defect") + 1] == "swap_sides"
    assert "--control" in command
    assert command[command.index("--fields") + 1:command.index("--fields") + 3] == [
        "program", "left_volume"
    ]
    assert str(tmp_path) in command


def test_controller_refuses_a_second_run_while_one_is_in_flight(tmp_path, monkeypatch):
    class Busy:
        stdout = None
        returncode = None

        def poll(self):
            return None

        def wait(self):
            return None

    monkeypatch.setattr("subprocess.Popen", lambda command, **kwargs: Busy())
    controller = _RunController(tmp_path)
    assert controller.start({"fields": ["program"]}) is True
    assert controller.start({"fields": ["program"]}) is False


def test_controller_ignores_an_unknown_backend(tmp_path, monkeypatch):
    seen = {}

    class FakeProcess:
        stdout = None
        returncode = 0

        def poll(self):
            return 0

        def wait(self):
            return 0

    monkeypatch.setattr(
        "subprocess.Popen",
        lambda command, **kwargs: (seen.__setitem__("command", command), FakeProcess())[1],
    )
    _RunController(tmp_path).start({"fields": ["program"], "backend": "rm -rf"})
    assert "--backend" not in seen["command"]


def test_log_stays_valid_json_while_the_run_writes_to_it(tmp_path):
    """The drain thread appends while the browser polls; an unguarded join
    can return a torn string that no longer decodes as JSON."""
    import threading
    import time

    controller = _RunController(tmp_path)
    stop = threading.Event()

    def writer():
        while not stop.is_set():
            with controller._lock:
                controller._log.append("battery announced 85 percent\n")
            time.sleep(0)

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        for _ in range(300):
            json.loads(json.dumps({"log": controller.log()}))
    finally:
        stop.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
