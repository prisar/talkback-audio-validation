from __future__ import annotations

import os
import time
from pathlib import Path

from .base import TranscriptResult

PROMPT_VERSION = "whisper-v1"

DEFAULT_MODEL = "small.en"


class LocalWhisperBackend:
    """Offline audio backend: Whisper running on this machine, no network.

    Same contract as the cloud backend -- it is handed the waveform and
    nothing else. Whisper takes no prompt, so the "cannot be told the
    answer" property holds by construction here rather than by wording.
    """

    name = "whisper-local"

    def __init__(self, model: str | None = None, compute_type: str = "int8"):
        self.model = model or os.environ.get("TBV_WHISPER_MODEL", DEFAULT_MODEL)
        self.compute_type = compute_type
        self._loaded = None

    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True

    def _model(self):
        if self._loaded is None:
            from faster_whisper import WhisperModel

            self._loaded = WhisperModel(
                self.model, device="cpu", compute_type=self.compute_type
            )
        return self._loaded

    def transcribe(self, audio_path: str | Path) -> TranscriptResult:
        started = time.time()
        try:
            from faster_whisper import WhisperModel  # noqa: F401
        except ImportError as exc:
            return TranscriptResult(
                backend=self.name,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                error=f"faster-whisper not installed: {exc}",
            )
        try:
            segments, info = self._model().transcribe(
                str(audio_path),
                beam_size=5,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=True,
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            return TranscriptResult(
                text=text,
                raw_response=text,
                backend=self.name,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                latency_s=time.time() - started,
                settings={
                    "compute_type": self.compute_type,
                    "beam_size": 5,
                    "temperature": 0.0,
                    "vad_filter": True,
                    "language": getattr(info, "language", ""),
                },
            )
        except Exception as exc:
            return TranscriptResult(
                backend=self.name,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                latency_s=time.time() - started,
                error=str(exc),
            )
