from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Node:
    resource_id: str = ""
    text: str = ""
    content_desc: str = ""
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    focused: bool = False

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2


@dataclass
class HierarchySnapshot:
    nodes: list[Node] = field(default_factory=list)
    captured_at: float = 0.0

    def by_id(self, resource_id: str) -> Node | None:
        for node in self.nodes:
            if node.resource_id.endswith(resource_id):
                return node
        return None

    def focused(self) -> Node | None:
        for node in self.nodes:
            if node.focused:
                return node
        return None


@dataclass
class BatteryState:
    level: int | None = None
    charging: bool = False


@dataclass
class AccessibilitySettings:
    enabled: bool = False
    services: str = ""

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, AccessibilitySettings)
            and self.enabled == other.enabled
            and self.services == other.services
        )


@dataclass
class FocusEvent:
    method: str
    guided: bool = False
    confirmed: bool = False
    at: float = 0.0


class DeviceDriver(Protocol):
    """Device control. Swapping this for an Appium driver must not touch
    the parser, the comparator, the verdicts, or the report."""

    name: str

    def serial(self) -> str: ...

    def screenshot(self, path) -> None: ...

    def dump_hierarchy(self) -> HierarchySnapshot: ...

    def battery_state(self) -> BatteryState: ...

    def accessibility_settings(self) -> AccessibilitySettings: ...

    def move_accessibility_focus(self) -> FocusEvent: ...
