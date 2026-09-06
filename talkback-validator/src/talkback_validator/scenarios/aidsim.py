from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..parsing import FieldType

PROGRAMS = ["Universal", "Noisy", "Restaurant", "Music"]
CONNECTION_WORDS = ["connected", "disconnected"]


@dataclass
class FieldSpec:
    name: str
    node_id: str
    field_type: FieldType
    panel: str | None = None
    parse_kwargs: dict = field(default_factory=dict)


FIELDS = [
    FieldSpec("left_battery", "chip_battery_left", FieldType.PERCENTAGE),
    FieldSpec("right_battery", "chip_battery_right", FieldType.PERCENTAGE),
    FieldSpec("program", "program_name", FieldType.NAME_WITH_STATE,
              parse_kwargs={"vocabulary": PROGRAMS}),
    FieldSpec("left_volume", "volume_left", FieldType.SIGNED_LEVEL, panel="volume"),
    FieldSpec("right_volume", "volume_right", FieldType.SIGNED_LEVEL, panel="volume"),
    FieldSpec("left_connection", "status_left_connection", FieldType.ENUM_STATE,
              panel="status", parse_kwargs={"vocabulary": CONNECTION_WORDS}),
]

BY_NAME = {spec.name: spec for spec in FIELDS}


def default_state() -> dict:
    """Asymmetric left/right on purpose: a side swap is undetectable when both
    sides hold the same value."""
    return {
        "left_battery": 85,
        "right_battery": 42,
        "left_volume": 4,
        "right_volume": -3,
        "program": "Noisy",
        "defect": "none",
    }


def open_panel(driver, panel: str | None) -> None:
    """Navigate to a panel by tapping a control on Home.

    With TalkBack active, a raw `adb shell input tap` is intercepted as a
    touch-exploration gesture (it announces the control, it does not click
    it) exactly like a real screen-reader user's single tap would be. This
    is scenario setup, not the thing under test, so TalkBack is disabled for
    the tap and restored immediately after, the same as `set_talkback` does
    for the audio capture window itself.
    """
    if panel is None:
        return
    snapshot = driver.dump_hierarchy()
    if panel == "volume":
        node = snapshot.by_id("open_volume_panel")
    elif panel == "status":
        node = snapshot.by_id("chip_battery_left")
    else:
        return
    if node is None:
        raise RuntimeError(f"cannot open {panel} panel: control not found")

    was_enabled = driver.accessibility_settings().enabled
    if was_enabled:
        driver.set_talkback(False)
    driver.tap(*node.center)
    if panel == "volume":
        # The right slider can sit below the fold; scroll so both sliders are
        # reachable, the way a sighted user would swipe to find it. Scroll
        # distance is a fraction of the actual screen height so this works
        # the same on a small emulator and a tall physical phone.
        content = snapshot.by_id("content")
        _, _, width, height = content.bounds if content else (0, 0, 1080, 2400)
        driver.swipe(width // 2, int(height * 0.93), width // 2, int(height * 0.55), 300)
    if was_enabled:
        driver.set_talkback(True)
        time.sleep(1.0)
