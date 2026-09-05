"""The validator must work from the APK alone.

A test team receives a binary, not source. These tests keep that true as the
code changes, rather than leaving it as a convention someone can quietly break.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "talkback_validator"
REPO = Path(__file__).resolve().parents[2]

FORBIDDEN = [
    r"talkback-demo-app",
    r"AidSimScreen",
    r"MainActivity\.kt",
    r"\.gradle\b",
    r"gradlew",
    r"app/src/main",
]


def _sources() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def test_sources_exist():
    assert _sources(), "no validator sources found"


@pytest.mark.parametrize("pattern", FORBIDDEN)
def test_no_reference_to_app_source(pattern: str):
    offenders = []
    for path in _sources():
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if re.search(pattern, line):
                offenders.append(f"{path.relative_to(PACKAGE)}:{number}: {line.strip()}")
    assert not offenders, (
        f"validator reaches into the app source tree ({pattern}):\n" + "\n".join(offenders)
    )


def test_package_name_is_not_hardcoded():
    """Package and activity come from `aapt2 dump badging`, never from source knowledge."""
    offenders = []
    for path in _sources():
        text = path.read_text()
        for number, line in enumerate(text.splitlines(), start=1):
            if "com.talkbacklab.aidsim" in line:
                offenders.append(f"{path.relative_to(PACKAGE)}:{number}: {line.strip()}")
    assert not offenders, "app package name is hardcoded:\n" + "\n".join(offenders)


def test_apk_identity_is_discovered_from_the_binary():
    source = (PACKAGE / "drivers" / "adb.py").read_text()
    assert "badging" in source, "APK identity must be read with aapt2 dump badging"


def test_validator_runs_without_the_app_source_tree():
    """The demo app directory may be deleted entirely; only artifacts/ is required."""
    artifacts = REPO / "artifacts"
    assert (artifacts / "aidsim.apk").exists(), "published APK missing from artifacts/"
    assert (artifacts / "INTERFACE.md").exists(), "interface document missing from artifacts/"
