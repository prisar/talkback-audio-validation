from __future__ import annotations

import argparse
import json
import shutil
import os
import sys
import time
import webbrowser
from pathlib import Path

from . import reporting
from .capture import CaptureConfig, MicUnavailable, list_input_devices, record, wav_summary
from .comparison import CaptureValidity, Verdict, compare
from .parsing import FieldType, parse
from .scenarios import aidsim
from .visual import OcrUnavailable, build_visual_result, crop_and_ocr, parse_displayed

ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts"
DEFAULT_OUT = Path("runs")


def _driver(serial: str | None = None):
    from .drivers.adb import AdbDriver

    return AdbDriver(serial)


def _backend(offline: bool):
    from .transcription.gemini import FixtureBackend, GeminiBackend

    if offline:
        return FixtureBackend()
    backend = GeminiBackend(model=os.environ.get("TBV_MODEL", "gemini-2.5-flash"))
    if not backend.available():
        return FixtureBackend()
    return backend


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


def _capture_field(driver, spec, config, focus_first: bool):
    """Capture one announcement. Hierarchy reads happen strictly outside the
    audio window because UiAutomation suppresses TalkBack."""
    before = driver.accessibility_settings()
    snapshot = driver.dump_hierarchy()
    node = snapshot.by_id(spec.node_id)
    if node is None:
        return None, None, before, None, f"node {spec.node_id} not on screen"

    def focus_action():
        if focus_first:
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
    backend = _backend(args.offline)
    out_dir = Path(args.out or DEFAULT_OUT / f"run-{int(time.time())}")
    out_dir.mkdir(parents=True, exist_ok=True)

    apk = Path(args.apk or ARTIFACTS / "aidsim.apk")
    package, activity = driver.install(apk)

    state = aidsim.default_state()
    state["defect"] = args.defect
    driver.force_stop(package)
    driver.launch(package, activity, state)
    if not driver.wait_for_focus(package):
        print("app did not reach the foreground")
        return 1
    time.sleep(1.5)

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

    selected = [aidsim.BY_NAME[n] for n in args.fields] if args.fields else aidsim.FIELDS
    for spec in selected:
        try:
            aidsim.open_panel(driver, spec.panel)
            time.sleep(1.0)
        except Exception as exc:
            print(f"skipping {spec.name}: {exc}")
            continue

        node, capture, before, after, error = _capture_field(
            driver, spec, {"out": out_dir, "capture": capture_config}, focus_first=True
        )
        if error:
            print(f"skipping {spec.name}: {error}")
            continue

        transcript = backend.transcribe(capture.wav_path)
        spoken = parse(transcript.text, spec.field_type, **spec.parse_kwargs)

        shot = out_dir / f"{spec.name}.png"
        crop = out_dir / f"{spec.name}-crop.png"
        driver.screenshot(shot)
        ocr_text, ocr_error = None, None
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


def cmd_serve_report(args) -> int:
    import http.server
    import socketserver

    root = Path(args.path) if args.path else _latest_run()
    if root is None or not root.exists():
        print("no report found; run the pipeline first")
        return 1

    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *a, directory=str(root), **k
    )
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
    run.add_argument("--control", action="store_true")
    run.set_defaults(func=cmd_run)

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
