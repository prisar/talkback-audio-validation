from __future__ import annotations

import time
import wave
from dataclasses import dataclass, field
from pathlib import Path


class MicUnavailable(RuntimeError):
    pass


@dataclass
class CaptureConfig:
    sample_rate: int = 16000
    channels: int = 1
    pre_roll_s: float = 1.0
    silence_tail_s: float = 1.2
    max_window_s: float = 12.0
    speech_threshold: float = 0.02
    device: int | None = None


@dataclass
class CaptureResult:
    wav_path: Path
    duration_s: float = 0.0
    peak_level: float = 0.0
    silent: bool = True
    clipped: bool = False
    truncated: bool = False
    overflows: int = 0
    device_name: str = ""
    events: list = field(default_factory=list)


def list_input_devices() -> list[dict]:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise MicUnavailable(str(exc)) from exc
    return [
        {"index": i, "name": d["name"], "channels": d["max_input_channels"]}
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


def record(
    wav_path: str | Path,
    config: CaptureConfig,
    on_start=None,
) -> CaptureResult:
    """Record the phone speaker through the laptop microphone.

    Keeps pre-roll because the start of a TalkBack announcement clips easily,
    stops on sustained silence after speech, and always honours a hard timeout.
    The raw stream is written unmodified; no denoising touches the evidence.
    """
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise MicUnavailable(str(exc)) from exc

    wav_path = Path(wav_path)
    block = int(config.sample_rate * 0.05)
    frames: list = []
    events: list = []
    overflows = 0
    speech_started = False
    last_speech = None
    truncated = False

    device_name = ""
    try:
        info = sd.query_devices(config.device, "input")
        device_name = info["name"]
    except Exception:
        device_name = "unknown"

    started = time.time()
    events.append({"event": "stream_open", "at": started})

    try:
        stream = sd.InputStream(
            samplerate=config.sample_rate,
            channels=config.channels,
            blocksize=block,
            device=config.device,
            dtype="float32",
        )
    except Exception as exc:
        raise MicUnavailable(str(exc)) from exc

    with stream:
        pre_roll_end = time.time() + config.pre_roll_s
        while time.time() < pre_roll_end:
            data, overflowed = stream.read(block)
            overflows += int(bool(overflowed))
            frames.append(data.copy())
        events.append({"event": "pre_roll_done", "at": time.time()})

        if on_start:
            on_start()
            events.append({"event": "focus_action", "at": time.time()})

        deadline = time.time() + config.max_window_s
        while time.time() < deadline:
            data, overflowed = stream.read(block)
            overflows += int(bool(overflowed))
            frames.append(data.copy())
            level = float(np.abs(data).max())
            now = time.time()
            if level >= config.speech_threshold:
                if not speech_started:
                    speech_started = True
                    events.append({"event": "speech_start", "at": now})
                last_speech = now
            elif speech_started and last_speech and now - last_speech >= config.silence_tail_s:
                events.append({"event": "speech_end", "at": now})
                break
        else:
            truncated = speech_started
            events.append({"event": "timeout", "at": time.time()})

    audio = np.concatenate(frames) if frames else np.zeros((0, config.channels), dtype="float32")
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    clipped = bool(peak >= 0.999)

    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as handle:
        handle.setnchannels(config.channels)
        handle.setsampwidth(2)
        handle.setframerate(config.sample_rate)
        handle.writeframes(pcm.tobytes())

    return CaptureResult(
        wav_path=wav_path,
        duration_s=len(audio) / config.sample_rate if audio.size else 0.0,
        peak_level=peak,
        silent=not speech_started,
        clipped=clipped,
        truncated=truncated,
        overflows=overflows,
        device_name=device_name,
        events=events,
    )


def wav_summary(wav_path: str | Path) -> dict:
    with wave.open(str(wav_path), "rb") as handle:
        frames = handle.getnframes()
        rate = handle.getframerate()
        return {
            "duration_s": frames / rate if rate else 0.0,
            "sample_rate": rate,
            "channels": handle.getnchannels(),
            "frames": frames,
        }
