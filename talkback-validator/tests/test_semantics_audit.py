from __future__ import annotations

from talkback_validator.drivers.base import HierarchySnapshot, Node
from talkback_validator.semantics_audit import Rule, audit


def test_clean_node_has_no_finding():
    snapshot = HierarchySnapshot(nodes=[
        Node(resource_id="programs_button", text="Programs",
             content_desc="Programs, change program", clickable=True),
    ])
    assert audit(snapshot) == []


def test_clickable_node_with_no_name_is_flagged():
    snapshot = HierarchySnapshot(nodes=[
        Node(resource_id="chip_battery_left", text="", content_desc="", clickable=True),
    ])
    findings = audit(snapshot)
    assert len(findings) == 1
    assert findings[0].rule == Rule.NO_ACCESSIBLE_NAME
    assert findings[0].resource_id == "chip_battery_left"


def test_generic_label_is_flagged():
    snapshot = HierarchySnapshot(nodes=[
        Node(resource_id="open_volume_panel", text="L|R", content_desc="Button", clickable=True),
    ])
    findings = audit(snapshot)
    assert len(findings) == 1
    assert findings[0].rule == Rule.GENERIC_LABEL


def test_non_clickable_node_without_name_is_not_flagged():
    snapshot = HierarchySnapshot(nodes=[
        Node(resource_id="status_indicator", text="", content_desc="", clickable=False),
    ])
    assert audit(snapshot) == []


def test_status_bar_chrome_is_ignored():
    snapshot = HierarchySnapshot(nodes=[
        Node(resource_id="", text="", content_desc="", clickable=True, class_name="android.view.View"),
    ])
    assert audit(snapshot) == []
