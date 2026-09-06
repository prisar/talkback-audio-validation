from __future__ import annotations

import argparse
import json
import shutil
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import reporting
from .capture import CaptureConfig, MicUnavailable, list_input_devices, record, wav_summary
from .comparison import CaptureValidity, Reason, Verdict, compare
from .parsing import FieldType, parse
from .scenarios import aidsim
from .visual import OcrUnavailable, build_visual_result, crop_and_ocr, crop_region, parse_displayed

ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts"
DEFAULT_OUT = Path("runs")


def _driver(serial: str | None = None):
    from .drivers.adb import AdbDriver

    return AdbDriver(serial)


def _backend(offline: bool, choice: str | None = None):
    from .transcription.gemini import FixtureBackend, GeminiBackend
    from .transcription.local import LocalWhisperBackend

    if offline:
        return FixtureBackend()
    choice = choice or os.environ.get("TBV_BACKEND", "gemini")
    if choice == "whisper":
        backend = LocalWhisperBackend()
        if not backend.available():
            raise SystemExit(
                "whisper backend requested but faster-whisper is not installed: "
                "uv sync --extra local"
            )
        return backend
    backend = GeminiBackend(model=os.environ.get("TBV_MODEL", "gemini-flash-latest"))
    if not backend.available():
        return FixtureBackend()
    return backend


def _screen_reader(backend):
    """The channel that reads the screen is chosen independently of the one
    that reads the audio. A local speech model cannot read a screenshot, and
    tesseract misreads the rendered digits often enough to stall a run on
    VISUAL_CHANNELS_DISAGREE, so a local audio run still prefers the cloud
    model here when it is configured. It is a separate call with its own
    prompt and never sees the transcript, so the channels stay independent."""
    if hasattr(backend, "read_screen_value"):
        return backend
    from .transcription.gemini import GeminiBackend

    reader = GeminiBackend(model=os.environ.get("TBV_MODEL", "gemini-flash-latest"))
    return reader if reader.available() else None


def cmd_audio_devices(_args) -> int:
    try:
        for device in list_input_devices():
            print(f"[{device['index']:>2}] {device['name']}  ({device['channels']} ch)")
    except MicUnavailable as exc:
        print(f"microphone support unavailable: {exc}")
        return 1
    return 0


def cmd_doctor(args) -> int:
    checks: list[tuple[str, bool, str]] = []

    apk = Path(args.apk or ARTIFACTS / "aidsim.apk")
    checks.append(("APK present", apk.exists(), str(apk)))

    helper_present = (ARTIFACTS / "focus-helper.apk").exists() and (
        ARTIFACTS / "focus-helper-test.apk"
    ).exists()
    checks.append(
        (
            "Focus helper present",
            helper_present,
            "accessibility-focus targeting" if helper_present else "falls back to raw taps",
        )
    )

    try:
        from .drivers.adb import apk_identity, list_devices

        devices = list_devices()
        checks.append(("ADB device authorized", bool(devices), ", ".join(devices) or "none"))
        if apk.exists():
            package, activity = apk_identity(apk)
            checks.append(("APK identity readable", True, f"{package} / {activity}"))
    except Exception as exc:
        checks.append(("ADB available", False, str(exc)))
        devices = []

    if devices:
        try:
            driver = _driver(args.serial)
            info = driver.device_info()
            checks.append(("Device info", True, json.dumps(info)))
            settings = driver.accessibility_settings()
            checks.append(("TalkBack installed", driver.talkback_installed(), ""))
            checks.append(
                ("TalkBack enabled", settings.enabled, settings.services or "no services")
            )
            battery = driver.battery_state()
            checks.append(("dumpsys battery", battery.level is not None, str(battery)))
            snapshot = driver.dump_hierarchy()
            checks.append(("Hierarchy dump", bool(snapshot.nodes), f"{len(snapshot.nodes)} nodes"))
        except Exception as exc:
            checks.append(("Device queries", False, str(exc)))

    try:
        devices_in = list_input_devices()
        checks.append(("Microphone", bool(devices_in), f"{len(devices_in)} input devices"))
    except MicUnavailable as exc:
        checks.append(("Microphone", False, str(exc)))

    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        checks.append(("OCR (tesseract)", True, ""))
    except Exception as exc:
        checks.append(("OCR (tesseract)", False, str(exc)))

    from .transcription.gemini import GeminiBackend

    checks.append(("Cloud model", GeminiBackend().available(), "GEMINI_API_KEY + google-genai"))

    from .transcription.local import LocalWhisperBackend

    local_backend = LocalWhisperBackend()
    checks.append(
        ("Local model", local_backend.available(), f"faster-whisper ({local_backend.model})")
    )

    out = Path(args.out or DEFAULT_OUT)
    try:
        out.mkdir(parents=True, exist_ok=True)
        checks.append(("Output writable", True, str(out)))
    except Exception as exc:
        checks.append(("Output writable", False, str(exc)))

    width = max(len(name) for name, _, _ in checks)
    failed = 0
    for name, ok, detail in checks:
        mark = "ok  " if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{mark}] {name.ljust(width)}  {detail}")
    print()
    print(f"{len(checks) - failed}/{len(checks)} checks passed")
    return 0 if failed == 0 else 1


def cmd_audit(args) -> int:
    """Walk the live accessibility tree and flag defects no configured field
    catches: clickable controls with no accessible name, or a name generic
    enough to name nothing. This does not know what a label should say, only
    whether one exists and means something. See semantics_audit.py."""
    from .semantics_audit import audit

    apk = Path(args.apk or ARTIFACTS / "aidsim.apk")
    if not apk.exists():
        print(f"APK not found: {apk}")
        return 1

    driver = _driver(args.serial)
    package, activity = driver.install(apk)
    extras: dict = {"defect": args.defect}
    for pair in args.extra or []:
        key, _, value = pair.partition("=")
        extras[key] = value
    driver.launch(package, activity, extras)
    driver.wait_for_focus(package)

    from .drivers.base import HierarchySnapshot

    snapshot = driver.dump_hierarchy()
    # `uiautomator dump` captures every window on screen, not just the app's:
    # status bar, nav bar, and OEM overlay icons all show up alongside it, and
    # their shape varies by device in ways no class-name heuristic reliably
    # covers. Scoping to the app's own package is what actually holds across
    # devices, since every node still carries which app's window it belongs to.
    own_nodes = [n for n in snapshot.nodes if n.package == package]
    own_snapshot = HierarchySnapshot(nodes=own_nodes, captured_at=snapshot.captured_at)
    findings = audit(own_snapshot)

    print(f"{package} / {activity}, defect={args.defect}: {len(own_nodes)} nodes scanned")
    if not findings:
        print("no findings")
        return 0
    for finding in findings:
        print(f"[{finding.rule.value}] {finding.resource_id}  text={finding.text!r}  content-desc={finding.content_desc!r}")
    return 1


def _capture_field(driver, spec, config, focus_first: bool, package: str | None = None,
                    use_focus_helper: bool = False):
    """Capture one announcement. Hierarchy reads happen strictly outside the
    audio window because UiAutomation suppresses TalkBack.

    The suppression does not lift the instant the dump's UiAutomation
    connection closes. A tap fired too soon after is delivered as a real
    click, not touch-exploration -- indistinguishable from a normal tap
    except that, on a node that is itself a navigation control (the battery
    chips open the Status panel), it silently navigates instead of merely
    focusing. The capture then hears whatever the new screen announces
    first, not the field this call actually asked for.

    When use_focus_helper is set, focus_action moves accessibility focus
    with ACTION_ACCESSIBILITY_FOCUS via the focus-helper instrumentation
    instead of a raw tap. A tap only approximates touch-exploration; on
    some OEM builds it can land accessibility focus on the wrong sibling
    node, which a real accessibility action does not do.
    """
    before = driver.accessibility_settings()
    snapshot = driver.dump_hierarchy()
    node = snapshot.by_id(spec.node_id)
    if node is None:
        return None, None, before, None, f"node {spec.node_id} not on screen"
    time.sleep(0.8)

    def focus_action():
        if not focus_first:
            return
        if use_focus_helper and package:
            driver.focus_by_id(package, spec.node_id)
        else:
            driver.tap(*node.center)

    wav = Path(config["out"]) / f"{spec.name}.wav"
    result = record(wav, config["capture"], on_start=focus_action)
    after = driver.accessibility_settings()
    return node, result, before, after, None


def cmd_replay(args) -> int:
    """Run the full pipeline over committed fixtures. No phone, no API key."""
    fixtures_dir = Path(args.fixtures)
    manifest_path = fixtures_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"no fixture manifest at {manifest_path}")
        return 1
    manifest = json.loads(manifest_path.read_text())

    from .transcription.gemini import FixtureBackend

    backend = FixtureBackend()
    out_dir = Path(args.out or DEFAULT_OUT / f"replay-{int(time.time())}")

    run = reporting.new_run(
        {
            "mode": "replay (fixtures)",
            "driver": "none",
            "backend": backend.name,
            "device": manifest.get("device", "recorded fixture"),
            "fixture source": manifest.get("source", "unspecified"),
        }
    )

    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    for case in manifest["cases"]:
        wav = fixtures_dir / case["audio"]
        if wav.exists():
            shutil.copy2(wav, audio_dir / wav.name)
        transcript = backend.transcribe(wav)
        field_type = FieldType(case["field_type"])
        spoken = parse(transcript.text, field_type, **case.get("parse_kwargs", {}))

        visual = build_visual_result(
            field_type,
            text_node=case.get("text_node"),
            ocr_text=case.get("ocr_text"),
            dumpsys_value=case.get("dumpsys"),
        )
        validity = CaptureValidity(
            silent=case.get("silent", False),
            truncated=case.get("truncated", False),
            duration_s=wav_summary(wav)["duration_s"] if wav.exists() else 0.0,
        )
        result = compare(spoken, visual, validity, field_type=field_type)

        run["cases"].append(
            {
                "id": case["id"],
                "title": case.get("title", case["id"]),
                "scenario": case.get("scenario", "fixture"),
                "field": case.get("field", ""),
                "field_type": field_type.value,
                "status": result.verdict.value,
                "reason": result.reason.value,
                "detail": result.detail,
                "spoken_value": result.spoken_value,
                "visual_value": result.visual_value,
                "transcript": transcript.text,
                "channels": visual.channels,
                "audio_path": str(audio_dir / wav.name),
                "backend": transcript.backend,
                "model": transcript.model,
                "prompt_version": transcript.prompt_version,
                "driver": "none (replay)",
                "injected_defect": case.get("injected_defect"),
            }
        )

    control = manifest.get("control")
    if control:
        wav = fixtures_dir / control["audio"]
        if wav.exists():
            shutil.copy2(wav, audio_dir / wav.name)
        summary = wav_summary(wav) if wav.exists() else {"duration_s": 0.0}
        run["control"] = {
            "silent": control.get("silent", True),
            "peak_level": control.get("peak_level", 0.0),
            "duration_s": summary["duration_s"],
        }

    path = reporting.render(run, out_dir)
    _summarize(run, path)
    return 0


def cmd_run(args) -> int:
    driver = _driver(args.serial)
    backend = _backend(args.offline, getattr(args, "backend", None))
    out_dir = Path(args.out or DEFAULT_OUT / f"run-{int(time.time())}")
    out_dir.mkdir(parents=True, exist_ok=True)

    apk = Path(args.apk or ARTIFACTS / "aidsim.apk")
    package, activity = driver.install(apk)

    # Best-effort: the focus helper is a separate optional artifact. Its
    # absence degrades to the old raw-tap targeting, not to a hard failure.
    use_focus_helper = False
    helper_app = ARTIFACTS / "focus-helper.apk"
    helper_test = ARTIFACTS / "focus-helper-test.apk"
    if helper_app.exists() and helper_test.exists() and hasattr(driver, "install_focus_helper"):
        try:
            driver.install_focus_helper(helper_app, helper_test)
            use_focus_helper = True
        except Exception as exc:
            print(f"focus helper unavailable, falling back to raw taps: {exc}")

    # This is a TalkBack validator: a live run with TalkBack off would record
    # silence for every field and call it INCONCLUSIVE, which looks like a
    # legitimate abstention but is really "the thing under test never ran."
    # Turning it on here, once, up front, is the precondition the rest of the
    # pipeline assumes doctor already warned about.
    if not driver.accessibility_settings().enabled:
        print("TalkBack is off on this device; enabling it for the run")
        driver.set_talkback(True)
        time.sleep(3.0)
        # First-time enable can pop TalkBack's own tutorial over whatever was
        # on screen; going Home first keeps the tutorial from ever competing
        # with the app for foreground once launch() below runs.
        driver.shell("input keyevent KEYCODE_HOME")
        time.sleep(1.0)

    state = aidsim.default_state()
    state["defect"] = args.defect

    def reset_to_home() -> bool:
        driver.force_stop(package)
        driver.launch(package, activity, state)
        if not driver.wait_for_focus(package):
            return False
        # With TalkBack on, resuming the activity triggers its own window-entry
        # announcement ("AidSim..."). A short settle risks the deliberate
        # focus tap landing while that is still being spoken, so the capture
        # gets both utterances talked over each other instead of the one
        # field it asked for.
        settle = 5.0 if driver.accessibility_settings().enabled else 1.5
        time.sleep(settle)
        return True

    if not reset_to_home():
        print("app did not reach the foreground")
        return 1

    capture_config = CaptureConfig(
        pre_roll_s=args.pre_roll,
        max_window_s=args.max_window,
        device=args.audio_device,
    )
    run = reporting.new_run(
        {
            "mode": "live device",
            "driver": driver.name,
            "device": json.dumps(driver.device_info()),
            "backend": backend.name,
            "model": getattr(backend, "model", ""),
            "injected defect": args.defect,
        }
    )
    # Carried so the report's re-run panel can offer every field the scenario
    # has, not just the subset this run happened to capture.
    screen_reader = _screen_reader(backend)
    run["environment"]["screen reader"] = (
        getattr(screen_reader, "name", "") or "tesseract"
    )
    run["available_fields"] = [spec.name for spec in aidsim.FIELDS]
    run["defect"] = args.defect

    selected = [aidsim.BY_NAME[n] for n in args.fields] if args.fields else aidsim.FIELDS
    for spec in selected:
        # Every field starts from a fresh Home screen. Some fields (the battery
        # chips) are themselves navigation controls, so an earlier field's own
        # focus tap can leave the app on a different screen than the one this
        # field's node lives on; relaunching removes that ordering dependency
        # instead of letting one broken field cascade into every field after it.
        if not reset_to_home():
            print(f"{spec.name}: app did not reach the foreground")
            run["cases"].append(
                {
                    "id": f"{spec.name}-{args.defect}",
                    "title": f"{spec.name}: app did not relaunch to a stable state",
                    "scenario": "aidsim",
                    "field": spec.name,
                    "field_type": spec.field_type.value,
                    "status": Verdict.ERROR.value,
                    "reason": Reason.NAVIGATION_FAILED.value,
                    "detail": "app did not reach the foreground after relaunch",
                    "driver": driver.name,
                    "injected_defect": args.defect,
                }
            )
            continue
        try:
            aidsim.open_panel(driver, spec.panel)
            time.sleep(1.0)
        except Exception as exc:
            print(f"{spec.name}: {exc}")
            run["cases"].append(
                {
                    "id": f"{spec.name}-{args.defect}",
                    "title": f"{spec.name}: could not reach its panel",
                    "scenario": "aidsim",
                    "field": spec.name,
                    "field_type": spec.field_type.value,
                    "status": Verdict.ERROR.value,
                    "reason": Reason.NAVIGATION_FAILED.value,
                    "detail": str(exc),
                    "driver": driver.name,
                    "injected_defect": args.defect,
                }
            )
            continue

        node, capture, before, after, error = _capture_field(
            driver, spec, {"out": out_dir, "capture": capture_config}, focus_first=True,
            package=package, use_focus_helper=use_focus_helper
        )
        if error:
            # An element that is visible but absent from the semantics tree is itself a
            # finding. Skipping it silently would hide exactly the defect class this
            # tool exists to surface.
            print(f"{spec.name}: {error}")
            run["cases"].append(
                {
                    "id": f"{spec.name}-{args.defect}",
                    "title": f"{spec.name} is not present in the accessibility tree",
                    "scenario": "aidsim",
                    "field": spec.name,
                    "field_type": spec.field_type.value,
                    "status": Verdict.INCONCLUSIVE.value,
                    "reason": Reason.ELEMENT_NOT_IN_A11Y_TREE.value,
                    "detail": error,
                    "driver": driver.name,
                    "injected_defect": args.defect,
                }
            )
            continue

        transcript = backend.transcribe(capture.wav_path)
        if transcript.error:
            # A backend failure (bad model name, auth, quota, network) is not
            # evidence about TalkBack; conflating it with "no speech heard"
            # would misreport a broken pipeline as an honest abstention.
            print(f"{spec.name}: transcription failed: {transcript.error}")
            run["cases"].append(
                {
                    "id": f"{spec.name}-{args.defect}",
                    "title": f"{spec.name}: transcription backend failed",
                    "scenario": "aidsim",
                    "field": spec.name,
                    "field_type": spec.field_type.value,
                    "status": Verdict.ERROR.value,
                    "reason": Reason.MODEL_UNAVAILABLE.value,
                    "detail": transcript.error,
                    "audio_path": str(capture.wav_path),
                    "backend": transcript.backend,
                    "model": transcript.model,
                    "driver": driver.name,
                    "injected_defect": args.defect,
                }
            )
            continue
        spoken = parse(transcript.text, spec.field_type, **spec.parse_kwargs)

        shot = out_dir / f"{spec.name}.png"
        crop = out_dir / f"{spec.name}-crop.png"
        driver.screenshot(shot)
        ocr_text, ocr_error = None, None
        if screen_reader is not None:
            # Reads the same cropped region a human would look at, with the
            # model that already reads audio for this run -- one fewer
            # native dependency (tesseract) and no separate OCR failure mode.
            crop_region(shot, node.bounds, crop)
            screen_read = screen_reader.read_screen_value(crop)
            if screen_read.error:
                ocr_error = screen_read.error
            else:
                ocr_text = screen_read.text
        else:
            try:
                ocr_text = crop_and_ocr(shot, node.bounds, crop)
            except OcrUnavailable as exc:
                ocr_error = str(exc)

        dumpsys_value = None
        if spec.field_type is FieldType.PERCENTAGE and "battery" in spec.name:
            dumpsys_value = None

        visual = build_visual_result(
            spec.field_type,
            text_node=node.text,
            ocr_text=ocr_text,
            ocr_error=ocr_error,
            dumpsys_value=dumpsys_value,
        )
        validity = CaptureValidity(
            silent=capture.silent,
            truncated=capture.truncated,
            clipped=capture.clipped,
            accessibility_suppressed=(before != after),
            duration_s=capture.duration_s,
            peak_level=capture.peak_level,
        )
        result = compare(spoken, visual, validity, field_type=spec.field_type)

        run["cases"].append(
            {
                "id": f"{spec.name}-{args.defect}",
                "title": f"{spec.name} announced by TalkBack",
                "scenario": "aidsim",
                "field": spec.name,
                "field_type": spec.field_type.value,
                "status": result.verdict.value,
                "reason": result.reason.value,
                "detail": result.detail,
                "spoken_value": result.spoken_value,
                "visual_value": result.visual_value,
                "transcript": transcript.text,
                "channels": visual.channels,
                "audio_path": str(capture.wav_path),
                "screenshot": str(shot),
                "crop": str(crop) if crop.exists() else "",
                "events": capture.events,
                "accessibility": {"before": before, "after": after},
                "backend": transcript.backend,
                "model": transcript.model,
                "prompt_version": transcript.prompt_version,
                "driver": driver.name,
                "injected_defect": args.defect,
                "focus_method": "accessibility_focus_action" if use_focus_helper else "tap",
            }
        )

    if args.control:
        driver.set_talkback(False)
        time.sleep(1.5)
        control = record(out_dir / "control.wav", capture_config)
        run["control"] = {
            "silent": control.silent,
            "peak_level": control.peak_level,
            "duration_s": control.duration_s,
        }
        driver.set_talkback(True)

    path = reporting.render(run, out_dir)
    _summarize(run, path)
    return 0


def _summarize(run: dict, path: Path) -> None:
    counts: dict[str, int] = {}
    for case in run["cases"]:
        counts[case["status"]] = counts.get(case["status"], 0) + 1
    print()
    for status in ("PASS", "FAIL", "INCONCLUSIVE", "ERROR"):
        if counts.get(status):
            print(f"  {status:<14} {counts[status]}")
    print(f"\nreport: {path}")


LOG_LINES = 400


class _RunController:
    """Serialises re-runs: one capture at a time, since they share the phone
    and the microphone. A second request while a run is in flight is refused
    rather than queued, so the report can never show two interleaved runs."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self._process: subprocess.Popen | None = None
        self._log: list[str] = []
        self._lock = threading.Lock()

    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def exit_code(self):
        if self._process is None or self.running():
            return None
        return self._process.returncode

    def log(self) -> str:
        # Joined under the lock: the drain thread appends concurrently, and
        # joining a list while it grows can return a torn string that is no
        # longer valid JSON by the time it reaches the browser.
        with self._lock:
            return "".join(self._log)

    def start(self, request: dict) -> bool:
        with self._lock:
            if self.running():
                return False
            fields = [str(f) for f in request.get("fields") or []]
            if not fields:
                return False
            command = [
                sys.executable, "-m", "talkback_validator.cli", "run", "aidsim",
                "--out", str(self.out_dir),
                "--defect", str(request.get("defect") or "none"),
                "--fields", *fields,
            ]
            backend = request.get("backend")
            if backend in {"gemini", "whisper"}:
                command += ["--backend", backend]
            if request.get("control"):
                command.append("--control")
            self._log = [" ".join(command) + "\n\n"]
            self._process = subprocess.Popen(
                command,
                cwd=Path.cwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            threading.Thread(target=self._drain, daemon=True).start()
            return True

    def _drain(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            with self._lock:
                self._log.append(line)
                del self._log[:-LOG_LINES]
        process.wait()


def _report_handler(root: Path, controller: _RunController):
    import http.server

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.rstrip("/").endswith("/status") or self.path == "/status":
                self._json(200, {
                    "running": controller.running(),
                    "exit_code": controller.exit_code(),
                    "log": controller.log(),
                })
                return
            super().do_GET()

        def do_POST(self):
            if not (self.path == "/rerun" or self.path.rstrip("/").endswith("/rerun")):
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                request = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json(400, {"error": "malformed request"})
                return
            if not controller.start(request):
                self._json(409, {"error": "a run is already in progress"})
                return
            self._json(202, {"started": True})

        def log_message(self, *args):
            pass

    return Handler


def cmd_serve_report(args) -> int:
    import socketserver

    root = Path(args.path) if args.path else _latest_run()
    if root is None or not root.exists():
        print("no report found; run the pipeline first")
        return 1

    controller = _RunController(root)
    handler = _report_handler(root, controller)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        url = f"http://127.0.0.1:{args.port}/index.html"
        print(f"serving {root} at {url}")
        if not args.no_open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def _latest_run() -> Path | None:
    if not DEFAULT_OUT.exists():
        return None
    runs = sorted(
        (p for p in DEFAULT_OUT.iterdir() if (p / "index.html").exists()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return runs[0] if runs else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="talkback-validator")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check every prerequisite")
    doctor.add_argument("--serial")
    doctor.add_argument("--apk")
    doctor.add_argument("--out")
    doctor.set_defaults(func=cmd_doctor)

    devices = sub.add_parser("audio-devices", help="list microphone inputs")
    devices.set_defaults(func=cmd_audio_devices)

    run = sub.add_parser("run", help="live capture against a connected device")
    run.add_argument("scenario", nargs="?", default="aidsim")
    run.add_argument("--serial")
    run.add_argument("--apk")
    run.add_argument("--out")
    run.add_argument("--defect", default="none")
    run.add_argument("--fields", nargs="*")
    run.add_argument("--pre-roll", type=float, default=1.0)
    run.add_argument("--max-window", type=float, default=12.0)
    run.add_argument("--audio-device", type=int)
    run.add_argument("--offline", action="store_true")
    run.add_argument("--backend", choices=["gemini", "whisper"], default=None)
    run.add_argument("--control", action="store_true")
    run.set_defaults(func=cmd_run)

    audit = sub.add_parser("audit", help="scan the live accessibility tree for label defects")
    audit.add_argument("--serial")
    audit.add_argument("--apk")
    audit.add_argument("--defect", default="none")
    audit.add_argument("--extra", nargs="*", help="extra key=value intent extras")
    audit.set_defaults(func=cmd_audit)

    replay = sub.add_parser("replay", help="run over committed fixtures, no device needed")
    replay.add_argument("fixtures", nargs="?", default="fixtures")
    replay.add_argument("--out")
    replay.set_defaults(func=cmd_replay)

    serve = sub.add_parser("serve-report", help="serve a report from 127.0.0.1")
    serve.add_argument("path", nargs="?")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-open", action="store_true")
    serve.set_defaults(func=cmd_serve_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
