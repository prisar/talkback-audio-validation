from __future__ import annotations

import os
import time
from pathlib import Path

from .base import TranscriptResult

PROMPT_VERSION = "v1"

PROMPT = (
    "Transcribe only the speech audible in this recording. "
    "Preserve numbers and units exactly as heard. "
    "Do not infer missing speech or complete cut-off phrases. "
    "Mark unintelligible speech as [inaudible]. "
    "Return an empty transcript when no intelligible speech is audible."
)

SCREEN_PROMPT = (
    "Read only the value shown in this screenshot region. "
    "Return it exactly as rendered, with no other words. "
    "Return an empty response if no value is legible."
)


class ModelUnavailable(RuntimeError):
    pass


class GeminiBackend:
    """Audio-only cloud backend.

    The prompt names no expected value, no field, and no application. The model
    is given the waveform and nothing else, so it cannot infer the answer it is
    supposed to be independently reporting.
    """

    name = "gemini"

    def __init__(self, model: str = "gemini-flash-latest", api_key: str | None = None):
        self.model = model
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")

    def available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import google.genai  # noqa: F401
        except ImportError:
            return False
        return True

    def transcribe(self, audio_path: str | Path) -> TranscriptResult:
        return self._ask(PROMPT, audio_path, "audio/wav")

    def read_screen_value(self, image_path: str | Path) -> TranscriptResult:
        """Reads a screenshot region with the model instead of tesseract OCR.

        This is a second, independent query against the same model used for
        transcription -- a separate call, its own prompt, no mention of the
        spoken value -- so it still corroborates rather than assumes it.
        """
        return self._ask(SCREEN_PROMPT, image_path, "image/png")

    def _ask(self, prompt: str, media_path: str | Path, mime_type: str) -> TranscriptResult:
        started = time.time()
        if not self._api_key:
            return TranscriptResult(
                backend=self.name,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                error="GEMINI_API_KEY is not set",
            )
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            return TranscriptResult(
                backend=self.name,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                error=f"google-genai not installed: {exc}",
            )

        media_bytes = Path(media_path).read_bytes()
        try:
            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self.model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=media_bytes, mime_type=mime_type),
                ],
                config=types.GenerateContentConfig(temperature=0.0),
            )
            text = (response.text or "").strip()
            return TranscriptResult(
                text=text,
                raw_response=str(response),
                backend=self.name,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                latency_s=time.time() - started,
                settings={"temperature": 0.0},
            )
        except Exception as exc:
            return TranscriptResult(
                backend=self.name,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                latency_s=time.time() - started,
                error=str(exc),
            )


class FixtureBackend:
    """Replays a transcript recorded next to a fixture WAV.

    This is how the offline replay path works without a network or a key. It is
    labelled in every result so a fixture run can never be presented as a live one.
    """

    name = "fixture"

    def __init__(self, model: str = "recorded"):
        self.model = model

    def available(self) -> bool:
        return True

    def transcribe(self, audio_path: str | Path) -> TranscriptResult:
        sidecar = Path(audio_path).with_suffix(".transcript.txt")
        if not sidecar.exists():
            return TranscriptResult(
                backend=self.name,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                error=f"no recorded transcript beside {audio_path}",
            )
        return TranscriptResult(
            text=sidecar.read_text().strip(),
            raw_response=sidecar.read_text(),
            backend=self.name,
            model=self.model,
            prompt_version=PROMPT_VERSION,
        )
