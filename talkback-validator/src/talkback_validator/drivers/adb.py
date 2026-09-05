from __future__ import annotations

import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from .base import (
    AccessibilitySettings,
    BatteryState,
    FocusEvent,
    HierarchySnapshot,
    Node,
)

TALKBACK_SERVICE = (
    "com.google.android.marvin.talkback/"
    "com.google.android.marvin.talkback.TalkBackService"
)


class AdbError(RuntimeError):
    pass


def _sdk_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    root = Path.home() / "Library" / "Android" / "sdk"
    for candidate in sorted((root / "build-tools").glob("*/" + name), reverse=True):
        return str(candidate)
    candidate = root / "platform-tools" / name
    return str(candidate) if candidate.exists() else None


def list_devices() -> list[str]:
    adb = _sdk_tool("adb")
    if not adb:
        raise AdbError("adb not found on PATH or in the Android SDK")
    out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=30).stdout
    return [
        line.split("\t")[0]
        for line in out.splitlines()[1:]
        if line.strip() and line.endswith("device")
    ]


def apk_identity(apk_path: str | Path) -> tuple[str, str]:
    """Discover package and activity from the APK. Never hardcode them from source."""
    aapt2 = _sdk_tool("aapt2")
    if not aapt2:
        raise AdbError("aapt2 not found; cannot inspect the APK")
    out = subprocess.run(
        [aapt2, "dump", "badging", str(apk_path)], capture_output=True, text=True, timeout=60
    ).stdout
    package = re.search(r"package: name='([^']+)'", out)
    activity = re.search(r"launchable-activity: name='([^']+)'", out)
    if not package or not activity:
        raise AdbError(f"could not read package identity from {apk_path}")
    return package.group(1), activity.group(1)


class AdbDriver:
    name = "adb"

    def __init__(self, serial: str | None = None):
        adb = _sdk_tool("adb")
        if not adb:
            raise AdbError("adb not found on PATH or in the Android SDK")
        self._adb = adb
        if serial is None:
            devices = list_devices()
            if not devices:
                raise AdbError("no authorized adb device is connected")
            if len(devices) > 1:
                raise AdbError(
                    f"{len(devices)} devices connected; pass an explicit serial: {devices}"
                )
            serial = devices[0]
        self._serial = serial

    def serial(self) -> str:
        return self._serial

    def _run(self, *args: str, timeout: int = 60) -> str:
        result = subprocess.run(
            [self._adb, "-s", self._serial, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise AdbError(f"adb {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout

    def shell(self, command: str, timeout: int = 60) -> str:
        return self._run("shell", command, timeout=timeout)

    def install(self, apk_path: str | Path) -> tuple[str, str]:
        package, activity = apk_identity(apk_path)
        self._run("install", "-r", str(apk_path), timeout=300)
        return package, activity

    def launch(self, package: str, activity: str, extras: dict | None = None) -> None:
        component = activity if activity.startswith(package) else f"{package}/{activity}"
        if "/" not in component:
            component = f"{package}/{activity}"
        args = ["am", "start", "-W", "-n", component]
        for key, value in (extras or {}).items():
            if isinstance(value, bool):
                args += ["--ez", key, "true" if value else "false"]
            else:
                # Always string form: `am` parses a leading '-' as a flag and
                # then silently discards every extra that follows it.
                args += ["--es", key, f"'{value}'"]
        self.shell(" ".join(args), timeout=120)

    def force_stop(self, package: str) -> None:
        self.shell(f"am force-stop {package}")

    def wait_for_focus(self, package: str, timeout_s: float = 15.0) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                out = self.shell("dumpsys window | grep -m1 mCurrentFocus")
            except AdbError:
                out = ""
            if package in out:
                return True
            time.sleep(0.5)
        return False

    def screenshot(self, path: str | Path) -> None:
        result = subprocess.run(
            [self._adb, "-s", self._serial, "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0 or not result.stdout:
            raise AdbError("screencap failed")
        Path(path).write_bytes(result.stdout)

    def dump_hierarchy(self) -> HierarchySnapshot:
        """Opens a UiAutomation connection, which suppresses TalkBack.
        Never call this inside an audio capture window."""
        self.shell("rm -f /sdcard/tbv_dump.xml")
        self.shell("uiautomator dump /sdcard/tbv_dump.xml", timeout=120)
        xml = self.shell("cat /sdcard/tbv_dump.xml", timeout=60)
        return _parse_hierarchy(xml)

    def battery_state(self) -> BatteryState:
        out = self.shell("dumpsys battery")
        level = re.search(r"level:\s*(\d+)", out)
        status = re.search(r"status:\s*(\d+)", out)
        return BatteryState(
            level=int(level.group(1)) if level else None,
            charging=bool(status and status.group(1) in {"2", "5"}),
        )

    def accessibility_settings(self) -> AccessibilitySettings:
        enabled = self.shell("settings get secure accessibility_enabled").strip()
        services = self.shell("settings get secure enabled_accessibility_services").strip()
        return AccessibilitySettings(
            enabled=enabled == "1",
            services="" if services in {"null", ""} else services,
        )

    def set_talkback(self, enabled: bool) -> None:
        if enabled:
            self.shell(f"settings put secure enabled_accessibility_services {TALKBACK_SERVICE}")
            self.shell("settings put secure accessibility_enabled 1")
        else:
            self.shell("settings put secure accessibility_enabled 0")
            self.shell("settings put secure enabled_accessibility_services ''")

    def talkback_installed(self) -> bool:
        out = self.shell("pm list packages com.google.android.marvin.talkback")
        return "marvin.talkback" in out

    def move_accessibility_focus(self, keycode: str = "KEYCODE_DPAD_DOWN") -> FocusEvent:
        self.shell(f"input keyevent {keycode}")
        return FocusEvent(method=f"keyevent {keycode}", at=time.time())

    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {x} {y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> None:
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {ms}")

    def device_info(self) -> dict:
        def prop(name: str) -> str:
            try:
                return self.shell(f"getprop {name}").strip()
            except AdbError:
                return ""

        return {
            "serial": self._serial,
            "model": prop("ro.product.model"),
            "android_version": prop("ro.build.version.release"),
            "sdk": prop("ro.build.version.sdk"),
            "locale": prop("persist.sys.locale") or prop("ro.product.locale"),
        }


def _parse_hierarchy(xml: str) -> HierarchySnapshot:
    start = xml.find("<?xml")
    if start > 0:
        xml = xml[start:]
    nodes: list[Node] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return HierarchySnapshot(nodes=[], captured_at=time.time())
    for element in root.iter("node"):
        bounds = (0, 0, 0, 0)
        raw = element.get("bounds") or ""
        numbers = re.findall(r"-?\d+", raw)
        if len(numbers) == 4:
            bounds = tuple(int(n) for n in numbers)
        nodes.append(
            Node(
                resource_id=element.get("resource-id") or "",
                text=element.get("text") or "",
                content_desc=element.get("content-desc") or "",
                bounds=bounds,
                focused=(element.get("focused") == "true"),
            )
        )
    return HierarchySnapshot(nodes=nodes, captured_at=time.time())
