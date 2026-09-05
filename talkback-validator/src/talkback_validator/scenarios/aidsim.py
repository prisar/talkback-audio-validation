from __future__ import annotations

from dataclasses import dataclass, field

from ..parsing import FieldType

PROGRAMS = ["Universal", "Noisy Environment", "Restaurant", "Music"]
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
        "program": "Noisy Environment",
        "defect": "none",
    }


def open_panel(driver, panel: str | None) -> None:
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
    driver.tap(*node.center)
