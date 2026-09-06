from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

RUNTIME_DIR = Path(os.environ.get("TBV_RUNTIME_DIR", ".runtime"))
OLLAMA_DIR = RUNTIME_DIR / "ollama"
DEFAULT_PORT = 11434
OWN_PORT = int(os.environ.get("TBV_OLLAMA_PORT", "11435"))

RELEASE = "https://github.com/ollama/ollama/releases/latest/download"
ASSETS = {
    ("Darwin", "x86_64"): "ollama-darwin.tgz",
    ("Darwin", "arm64"): "ollama-darwin.tgz",
    ("Linux", "x86_64"): "ollama-linux-amd64.tgz",
    ("Linux", "aarch64"): "ollama-linux-arm64.tgz",
}


class RuntimeUnavailable(RuntimeError):
    pass


def asset_name() -> str | None:
    return ASSETS.get((platform.system(), platform.machine()))


def binary() -> Path | None:
    """Prefers a runtime we installed ourselves over one already on PATH,
    so a demo machine behaves the same whether or not the tester happens to
    have Ollama installed."""
    local = OLLAMA_DIR / "ollama"
    if local.exists():
        return local
    found = shutil.which("ollama")
    return Path(found) if found else None


def _port_answers(port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def endpoint() -> str | None:
    """The loopback address of a server that is already answering, if any."""
    for port in (DEFAULT_PORT, OWN_PORT):
        if _port_answers(port):
            return f"http://127.0.0.1:{port}"
    return None


def install_runtime(log=print) -> Path:
    """Downloads the Ollama runtime into the project rather than the system.

    Nothing is installed through a package manager and nothing needs admin
    rights, so a tester can add local inference to a checkout and remove it
    again by deleting one directory.
    """
    name = asset_name()
    if not name:
        raise RuntimeUnavailable(
            f"no Ollama build for {platform.system()} {platform.machine()}"
        )
    OLLAMA_DIR.mkdir(parents=True, exist_ok=True)
    archive = OLLAMA_DIR / name
    url = f"{RELEASE}/{name}"
    log(f"downloading {url}")
    urllib.request.urlretrieve(url, archive)
    log(f"extracting {archive.name}")
    with tarfile.open(archive) as handle:
        handle.extractall(OLLAMA_DIR)
    archive.unlink(missing_ok=True)
    target = OLLAMA_DIR / "ollama"
    if not target.exists():
        raise RuntimeUnavailable("the Ollama archive did not contain a runtime binary")
    target.chmod(0o755)
    log(f"runtime ready at {target}")
    return target


def serve(log=print) -> str:
    """Starts a loopback-only Ollama server and waits for it to answer."""
    existing = endpoint()
    if existing:
        return existing
    exe = binary()
    if exe is None:
        raise RuntimeUnavailable("the Ollama runtime is not installed")
    environment = dict(os.environ, OLLAMA_HOST=f"127.0.0.1:{OWN_PORT}")
    log(f"starting the local model server on 127.0.0.1:{OWN_PORT}")
    subprocess.Popen(
        [str(exe), "serve"],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if _port_answers(OWN_PORT):
            return f"http://127.0.0.1:{OWN_PORT}"
        time.sleep(0.5)
    raise RuntimeUnavailable("the local model server did not start within 30s")


def _api(path: str, payload: dict, timeout: float = 600.0) -> dict:
    base = endpoint()
    if base is None:
        raise RuntimeUnavailable("no local model server is running")
    request = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def installed_models() -> list[str]:
    base = endpoint()
    if base is None:
        return []
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=5) as response:
            tags = json.loads(response.read()).get("models", [])
    except OSError:
        return []
    return [str(entry.get("name", "")) for entry in tags]


def pull(model: str, log=print) -> None:
    """Downloads model weights. This is the one step that uses the network;
    every later run of that model is local."""
    base = serve(log=log)
    request = urllib.request.Request(
        f"{base}/api/pull",
        data=json.dumps({"model": model}).encode(),
        headers={"Content-Type": "application/json"},
    )
    seen = ""
    with urllib.request.urlopen(request, timeout=3600) as response:
        for line in response:
            if not line.strip():
                continue
            update = json.loads(line)
            if update.get("error"):
                raise RuntimeUnavailable(str(update["error"]))
            status = str(update.get("status", ""))
            if status and status != seen:
                seen = status
                log(status)


def remove(model: str, log=print) -> bool:
    """Deleting weights needs the server that owns them, so it is started if
    it is not already up. Returning quietly when it is down would leave
    gigabytes on disk while telling the caller the model was removed."""
    try:
        base = serve(log=lambda *_: None)
    except RuntimeUnavailable as exc:
        log(f"cannot reach the local model server: {exc}")
        return False
    request = urllib.request.Request(
        f"{base}/api/delete",
        data=json.dumps({"model": model}).encode(),
        headers={"Content-Type": "application/json"},
        method="DELETE",
    )
    try:
        urllib.request.urlopen(request, timeout=30).close()
        return True
    except OSError as exc:
        log(f"could not delete {model}: {exc}")
        return False


def generate(model: str, prompt: str, image_b64: str | None = None,
             timeout: float = 600.0) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }
    if image_b64:
        payload["images"] = [image_b64]
    return str(_api("/api/generate", payload, timeout=timeout).get("response", "")).strip()
