"""Focus targeting has two layers, each tested independently:

1. cli._capture_field must pick raw-tap vs. the accessibility-focus helper
   based on use_focus_helper, without touching a real device.
2. AdbDriver.focus_by_id / install_focus_helper must build the right adb
   commands and translate am instrument's output into a FocusEvent, without
   a real adb binary or phone.

A raw tap only approximates touch-exploration and, on this project's test
device, was proven to sometimes land accessibility focus on the wrong
sibling node. ACTION_ACCESSIBILITY_FOCUS via the focus-helper instrumentation
does not make that mistake, so which path a run actually took matters enough
to test directly rather than trust by convention.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from talkback_validator import cli
from talkback_validator.drivers import adb as adb_module
from talkback_validator.drivers.adb import AdbDriver


class _Node:
    center = (10, 20)


class _Snapshot:
    def by_id(self, node_id):
        return _Node()


class _EmptySnapshot:
    def by_id(self, node_id):
        return None


class _StubDriver:
    def __init__(self, snapshot=None):
        self.tap_calls = []
        self.focus_calls = []
        self._snapshot = snapshot or _Snapshot()

    def accessibility_settings(self):
        return SimpleNamespace(enabled=True)

    def dump_hierarchy(self):
        return self._snapshot

    def tap(self, x, y):
        self.tap_calls.append((x, y))

    def focus_by_id(self, package, resource_id):
        self.focus_calls.append((package, resource_id))


def _spec():
    return SimpleNamespace(node_id="chip_battery_right", name="right_battery")


def _stub_record(wav, config, on_start):
    on_start()
    return SimpleNamespace()


def test_capture_field_uses_raw_tap_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "record", _stub_record)
    monkeypatch.setattr(cli.time, "sleep", lambda *_: None)
    driver = _StubDriver()
    cli._capture_field(driver, _spec(), {"out": tmp_path, "capture": None}, focus_first=True)
    assert driver.tap_calls == [(10, 20)]
    assert driver.focus_calls == []


def test_capture_field_uses_focus_helper_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "record", _stub_record)
    monkeypatch.setattr(cli.time, "sleep", lambda *_: None)
    driver = _StubDriver()
    cli._capture_field(
        driver,
        _spec(),
        {"out": tmp_path, "capture": None},
        focus_first=True,
        package="com.talkbacklab.aidsim",
        use_focus_helper=True,
    )
    assert driver.focus_calls == [("com.talkbacklab.aidsim", "chip_battery_right")]
    assert driver.tap_calls == []


def test_capture_field_ignores_focus_helper_without_package(monkeypatch, tmp_path):
    # use_focus_helper=True but no package name is a caller bug, not a device
    # error; falling back to tap keeps that bug from crashing a live run.
    monkeypatch.setattr(cli, "record", _stub_record)
    monkeypatch.setattr(cli.time, "sleep", lambda *_: None)
    driver = _StubDriver()
    cli._capture_field(
        driver,
        _spec(),
        {"out": tmp_path, "capture": None},
        focus_first=True,
        package=None,
        use_focus_helper=True,
    )
    assert driver.tap_calls == [(10, 20)]
    assert driver.focus_calls == []


def test_capture_field_skips_focus_when_not_focus_first(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "record", _stub_record)
    monkeypatch.setattr(cli.time, "sleep", lambda *_: None)
    driver = _StubDriver()
    cli._capture_field(driver, _spec(), {"out": tmp_path, "capture": None}, focus_first=False)
    assert driver.tap_calls == []
    assert driver.focus_calls == []


def test_capture_field_missing_node_returns_error(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.time, "sleep", lambda *_: None)
    driver = _StubDriver(snapshot=_EmptySnapshot())
    node, result, before, after, error = cli._capture_field(
        driver, _spec(), {"out": tmp_path, "capture": None}, focus_first=True
    )
    assert node is None
    assert error == "node chip_battery_right not on screen"


def _driver_with_fake_adb() -> AdbDriver:
    driver = AdbDriver.__new__(AdbDriver)
    driver._adb = "adb"
    driver._serial = "test-serial"
    return driver


def _fake_subprocess_run(returncode=0, stdout="", stderr=""):
    def run(cmd, capture_output, text, timeout):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return run


def test_install_focus_helper_installs_both_apks(monkeypatch):
    calls = []

    def run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="Success", stderr="")

    monkeypatch.setattr(adb_module.subprocess, "run", run)
    driver = _driver_with_fake_adb()
    driver.install_focus_helper("focus-helper.apk", "focus-helper-test.apk")
    assert calls[0][-3:] == ["install", "-r", "focus-helper.apk"]
    assert calls[1][-3:] == ["install", "-r", "focus-helper-test.apk"]


def test_focus_by_id_confirms_on_instrumentation_ok(monkeypatch):
    monkeypatch.setattr(
        adb_module.subprocess, "run", _fake_subprocess_run(stdout="\nOK (1 test)\n")
    )
    driver = _driver_with_fake_adb()
    event = driver.focus_by_id("com.talkbacklab.aidsim", "chip_battery_right")
    assert event.confirmed is True
    assert event.method == "accessibility_focus_action"
    assert event.guided is True


def test_focus_by_id_targets_the_right_package_and_resource(monkeypatch):
    captured = {}

    def run(cmd, capture_output, text, timeout):
        captured["shell_command"] = cmd[-1]
        return SimpleNamespace(returncode=0, stdout="OK (1 test)", stderr="")

    monkeypatch.setattr(adb_module.subprocess, "run", run)
    driver = _driver_with_fake_adb()
    driver.focus_by_id("com.talkbacklab.aidsim", "chip_battery_right")
    command = captured["shell_command"]
    assert "target_package com.talkbacklab.aidsim" in command
    assert "resource_id chip_battery_right" in command
    assert "FocusTest#focusByResourceId" in command


def test_focus_by_id_not_confirmed_on_instrumentation_failure(monkeypatch):
    monkeypatch.setattr(
        adb_module.subprocess,
        "run",
        _fake_subprocess_run(stdout="FAILURES!!!\nTests run: 1,  Failures: 1"),
    )
    driver = _driver_with_fake_adb()
    event = driver.focus_by_id("com.talkbacklab.aidsim", "missing_id")
    assert event.confirmed is False


def test_focus_by_id_survives_adb_error_instead_of_raising(monkeypatch):
    monkeypatch.setattr(
        adb_module.subprocess,
        "run",
        _fake_subprocess_run(returncode=1, stderr="INSTRUMENTATION_FAILED"),
    )
    driver = _driver_with_fake_adb()
    event = driver.focus_by_id("com.talkbacklab.aidsim", "chip_battery_right")
    assert event.confirmed is False
    assert event.method == "accessibility_focus_action"
