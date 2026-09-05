import pytest

from talkback_validator.parsing import (
    FieldType,
    ParseStatus,
    parse,
    parse_percentage,
    parse_signed_level,
)


@pytest.mark.parametrize(
    "utterance,expected",
    [
        ("Battery, eighty-five percent", 85),
        ("85 per cent", 85),
        ("Fifteen percent", 15),
        ("Battery 85%", 85),
        ("Left battery, 42 percent", 42),
        ("Battery, eighty-five percent, charging", 85),
        ("Battery 100 percent", 100),
        ("Battery zero percent", 0),
    ],
)
def test_percentage_ok(utterance, expected):
    result = parse_percentage(utterance)
    assert result.status is ParseStatus.OK
    assert result.value == expected


def test_percentage_ignores_duration_numerals():
    result = parse_percentage("85%, 2 hours 10 minutes until full")
    assert result.status is ParseStatus.OK
    assert result.value == 85


def test_percentage_repeat_announcement_is_not_ambiguous():
    result = parse_percentage("Battery 85%. Battery 85%.")
    assert result.status is ParseStatus.OK
    assert result.value == 85


def test_percentage_conflicting_announcements_abstain():
    result = parse_percentage("Battery 15%. Battery 50%.")
    assert result.status is ParseStatus.AMBIGUOUS
    assert result.candidates == [15, 50]
    assert result.value is None


def test_percentage_requires_percentage_semantics():
    assert parse_percentage("Battery level 85").status is ParseStatus.NO_VALUE


def test_percentage_inaudible():
    assert parse_percentage("[inaudible] percent").status is ParseStatus.NO_VALUE


def test_percentage_empty():
    assert parse_percentage("").status is ParseStatus.NO_VALUE


def test_percentage_out_of_range():
    assert parse_percentage("Battery 140 percent").status is ParseStatus.OUT_OF_RANGE


@pytest.mark.parametrize(
    "utterance,expected",
    [
        ("Right volume, level minus 3", -3),
        ("Right volume, level 3", 3),
        ("Left volume, level 4", 4),
        ("Volume, level 0", 0),
        ("Left volume, level minus six", -6),
        ("Right volume, level negative two", -2),
        ("Volume level -3", -3),
    ],
)
def test_signed_level(utterance, expected):
    result = parse_signed_level(utterance)
    assert result.status is ParseStatus.OK
    assert result.value == expected


def test_sign_is_material():
    """The volume_sign defect: -3 announced as 3 must not compare equal."""
    assert parse_signed_level("Right volume, level minus 3").value == -3
    assert parse_signed_level("Right volume, level 3").value == 3
    assert parse_signed_level("Right volume, level minus 3").value != parse_signed_level(
        "Right volume, level 3"
    ).value


def test_signed_level_out_of_range():
    assert parse_signed_level("Volume level 40").status is ParseStatus.OUT_OF_RANGE


def test_name_with_state():
    result = parse(
        "Program, Noisy Environment, selected",
        FieldType.NAME_WITH_STATE,
        vocabulary=["Universal", "Noisy Environment", "Restaurant", "Music"],
    )
    assert result.status is ParseStatus.OK
    assert result.value == "Noisy Environment"
    assert result.state == "selected"


def test_name_unknown_abstains():
    result = parse(
        "Program, Aeroplane, selected",
        FieldType.NAME_WITH_STATE,
        vocabulary=["Universal", "Noisy Environment"],
    )
    assert result.status is ParseStatus.NO_VALUE


def test_enum_state():
    result = parse(
        "Left hearing aid, connected",
        FieldType.ENUM_STATE,
        vocabulary=["connected", "disconnected"],
    )
    assert result.status is ParseStatus.OK
    assert result.value == "connected"


def test_enum_state_disconnected_not_confused_with_connected():
    result = parse(
        "Left hearing aid, disconnected",
        FieldType.ENUM_STATE,
        vocabulary=["connected", "disconnected"],
    )
    assert result.status is ParseStatus.OK
    assert result.value == "disconnected"
