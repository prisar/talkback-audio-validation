"""Generic accessibility-tree checks that need no ground truth.

These rules catch label defects a screen-reader user would hit that the
value comparator in comparison.py cannot see, because it only compares a
configured field's spoken value against its displayed value. A control
that is clickable but unreachable, or labelled with a word that names no
target, fails regardless of which field it happens to be.

What this cannot catch: a label that is fluent, specific, and simply
wrong (says "Increase volume" on a control that opens Programs). Nothing
in the tree alone distinguishes that from a correct label; it needs a
ground truth this scanner does not have.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .drivers.base import HierarchySnapshot, Node

GENERIC_LABELS = {"button", "image", "icon", "item", "unlabeled"}


class Rule(str, Enum):
    NO_ACCESSIBLE_NAME = "NO_ACCESSIBLE_NAME"
    GENERIC_LABEL = "GENERIC_LABEL"


@dataclass
class Finding:
    rule: Rule
    resource_id: str
    text: str
    content_desc: str


def _accessible_name(node: Node) -> str:
    return (node.content_desc or node.text).strip()


def _is_system_chrome(node: Node) -> bool:
    """A resource-id-less android.view.View is status bar or nav bar chrome
    bleeding into the dump, not app content: this app sets
    testTagsAsResourceId, so every real content node carries a resource-id."""
    return not node.resource_id and node.class_name == "android.view.View"


def audit(snapshot: HierarchySnapshot) -> list[Finding]:
    findings: list[Finding] = []
    for node in snapshot.nodes:
        if not node.clickable or _is_system_chrome(node):
            continue
        name = _accessible_name(node)
        if not name:
            findings.append(Finding(Rule.NO_ACCESSIBLE_NAME, node.resource_id, node.text, node.content_desc))
        elif name.lower() in GENERIC_LABELS:
            findings.append(Finding(Rule.GENERIC_LABEL, node.resource_id, node.text, node.content_desc))
    return findings
