from __future__ import annotations

import base64
import re
import time
from pathlib import Path

from .base import TranscriptResult

PROMPT_VERSION = "vision-local-v1"

SCREEN_PROMPT = (
    "Read only the value shown in this image. "
    "Reply with that value exactly as rendered and nothing else: "
    "no explanation, no units you cannot see, no sentence. "
    "Reply with nothing at all if no value is legible."
)


def tidy(text: str) -> str:
    """Small local models narrate even when told not to. The first line is
    kept and any framing around it dropped, so a chatty answer still yields a
    comparable value instead of failing the case for style."""
    line = text.strip().splitlines()[0].strip() if text.strip() else ""
    line = re.sub(r"^(the\s+)?(value\s+)?(is|shown|reads)\s*[:\-]?\s*", "", line, flags=re.I)
    return line.strip().strip("\"'`*").rstrip(".").strip()


class LocalVisionBackend:
    """Offline screen reader: a vision model running on this machine.

    It is deliberately audio-blind. Pairing it with a local speech model keeps
    the two channels genuinely independent -- neither can see what the other
    observed -- which is the property the comparator depends on, and the
    reason a single omni model reading both would be a weaker design even
    where one is available.
    """

    name = "ollama-vision"

    def __init__(self, model: str = "gemma3:4b"):
        self.model = model

    def available(self) -> bool:
        """A server already answering on loopback counts even when no binary
        is found where we install one: reporting unavailable while the calls
        actually succeed is worse than either answer on its own.
        """
        from .. import runtime

        if runtime.binary() is None and runtime.endpoint() is None:
            return False
        names = runtime.installed_models()
        return any(n == self.model or n.startswith(self.model + "-") for n in names)

    def read_screen_value(self, image_path: str | Path) -> TranscriptResult:
        from .. import runtime

        started = time.time()
        try:
            runtime.serve(log=lambda *_: None)
            image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
            raw = runtime.generate(self.model, SCREEN_PROMPT, image_b64)
        except Exception as exc:
            return TranscriptResult(
                backend=self.name,
                model=self.model,
                prompt_version=PROMPT_VERSION,
                latency_s=time.time() - started,
                error=str(exc),
            )
        return TranscriptResult(
            text=tidy(raw),
            raw_response=raw,
            backend=self.name,
            model=self.model,
            prompt_version=PROMPT_VERSION,
            latency_s=time.time() - started,
            settings={"temperature": 0.0, "runs_locally": True},
        )
