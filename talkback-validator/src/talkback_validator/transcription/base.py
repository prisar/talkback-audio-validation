from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class TranscriptResult:
    text: str = ""
    raw_response: str = ""
    backend: str = ""
    model: str = ""
    prompt_version: str = ""
    latency_s: float = 0.0
    error: str | None = None
    settings: dict = field(default_factory=dict)


class TranscriptionBackend(Protocol):
    """Receives audio and nothing else. Never the screenshot, the expected
    value, the intent extras, or a prior result."""

    name: str

    def transcribe(self, audio_path) -> TranscriptResult: ...
