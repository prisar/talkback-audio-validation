from __future__ import annotations

import platform
from dataclasses import dataclass, field

from . import runtime

AUDIO = "audio"
VISION = "vision"


@dataclass(frozen=True)
class ModelSpec:
    """One selectable model, and what it is able to observe.

    The two channels are separate: a model that reads waveforms cannot read a
    screenshot, and most that read screenshots cannot hear. Keeping the role
    explicit is what lets a run pair a local speech model with a local vision
    model and still treat the two observations as independent.
    """

    id: str
    label: str
    roles: tuple[str, ...]
    engine: str
    size_gb: float
    note: str = ""
    blocked: str = field(default="")


def cpu_only() -> bool:
    """No Metal and no CUDA means every vision read runs on the CPU."""
    return platform.system() == "Darwin" and platform.machine() == "x86_64"


def speed_warning(spec: ModelSpec) -> str:
    """Measured, not estimated: gemma3:4b took 263-306s per screenshot on this
    Intel Mac and misread a volume of 4 as 44 before the runtime ran out of
    memory. A tester deserves that number before spending gigabytes on it."""
    if VISION in spec.roles and spec.engine == "ollama" and cpu_only():
        return "4-5 minutes per screenshot on this CPU, and accuracy was not reliable"
    return ""


def _omni_block() -> str:
    """Qwen2.5-Omni is the only entry that fails for a platform reason rather
    than a size one, so the reason is computed rather than asserted."""
    if platform.system() == "Darwin" and platform.machine() == "x86_64":
        return (
            "no llama.cpp support for its audio path, and the transformers route "
            "needs a newer torch than the last macOS x86_64 wheel (2.2.2)"
        )
    return ""


CATALOGUE: tuple[ModelSpec, ...] = (
    ModelSpec("tiny.en", "Whisper tiny", (AUDIO,), "whisper", 0.08,
              "fastest; misread 85% as 25% on the reference run"),
    ModelSpec("base.en", "Whisper base", (AUDIO,), "whisper", 0.15,
              "middle ground, not measured here"),
    ModelSpec("small.en", "Whisper small", (AUDIO,), "whisper", 0.46,
              "default; read every field correctly on the reference run"),
    ModelSpec("gemma3:4b", "Gemma 3 4B", (VISION,), "ollama", 3.3,
              "reads the screenshot on-device instead of tesseract"),
    ModelSpec("gemma3:12b", "Gemma 3 12B", (VISION,), "ollama", 8.1,
              "more accurate, needs roughly 12 GB free"),
    ModelSpec("qwen2.5vl:3b", "Qwen2.5-VL 3B", (VISION,), "ollama", 3.2,
              "smallest vision option"),
    ModelSpec("qwen2.5vl:7b", "Qwen2.5-VL 7B", (VISION,), "ollama", 6.0,
              "stronger on small rendered digits"),
    ModelSpec("qwen2.5-omni:7b", "Qwen2.5-Omni 7B", (AUDIO, VISION), "transformers", 12.0,
              "hears and sees in one model", blocked=_omni_block()),
    ModelSpec("gpt-oss:20b", "gpt-oss 20B", (), "ollama", 13.0,
              "text only", blocked="reads neither audio nor screenshots"),
)

BY_ID = {spec.id: spec for spec in CATALOGUE}


def for_role(role: str) -> list[ModelSpec]:
    return [spec for spec in CATALOGUE if role in spec.roles]


def whisper_installed(name: str) -> bool:
    """faster-whisper keeps its weights in the HuggingFace cache; presence of
    the snapshot directory is what distinguishes downloaded from not."""
    from pathlib import Path

    cache = Path.home() / ".cache" / "huggingface" / "hub"
    return any(cache.glob(f"models--*faster-whisper-{name}/snapshots/*"))


def is_installed(spec: ModelSpec) -> bool:
    if spec.blocked:
        return False
    if spec.engine == "whisper":
        return whisper_installed(spec.id)
    if spec.engine == "ollama":
        names = runtime.installed_models()
        return any(name == spec.id or name.startswith(spec.id + "-") for name in names)
    return False


def install(spec: ModelSpec, log=print) -> None:
    if spec.blocked:
        raise RuntimeError(f"{spec.label} cannot run on this machine: {spec.blocked}")
    if spec.engine == "whisper":
        log(f"fetching Whisper {spec.id}")
        from faster_whisper import WhisperModel

        WhisperModel(spec.id, device="cpu", compute_type="int8")
        log("done")
        return
    if spec.engine == "ollama":
        if runtime.binary() is None:
            log("the local model runtime is not present yet")
            runtime.install_runtime(log=log)
        runtime.pull(spec.id, log=log)
        return
    raise RuntimeError(f"no installer for engine {spec.engine}")


def whisper_dirs(name: str) -> list:
    from pathlib import Path

    cache = Path.home() / ".cache" / "huggingface" / "hub"
    return [p for p in cache.glob(f"models--*faster-whisper-{name}") if p.is_dir()]


def remove(spec: ModelSpec, log=print) -> bool:
    """Whisper weights live in the HuggingFace cache, Ollama weights in the
    Ollama store. Both are removable here, because a command that reports a
    model removed while its gigabytes remain on disk is worse than no command."""
    import shutil

    if spec.engine == "ollama":
        return runtime.remove(spec.id, log=log)
    if spec.engine == "whisper":
        found = whisper_dirs(spec.id)
        if not found:
            log(f"{spec.id} is not in the cache")
            return False
        for path in found:
            shutil.rmtree(path, ignore_errors=True)
            log(f"deleted {path}")
        return True
    log(f"no removal path for engine {spec.engine}")
    return False


def status() -> list[dict]:
    installed_ollama = set(runtime.installed_models())

    def installed(spec: ModelSpec) -> bool:
        if spec.blocked:
            return False
        if spec.engine == "ollama":
            return any(
                name == spec.id or name.startswith(spec.id + "-")
                for name in installed_ollama
            )
        return is_installed(spec)

    return [
        {
            "id": spec.id,
            "label": spec.label,
            "roles": list(spec.roles),
            "engine": spec.engine,
            "size_gb": spec.size_gb,
            "note": ", ".join(part for part in (spec.note, speed_warning(spec)) if part),
            "blocked": spec.blocked,
            "installed": installed(spec),
        }
        for spec in CATALOGUE
    ]
