from talkback_validator.comparison import (
    CaptureValidity,
    Reason,
    Verdict,
    VisualResult,
    compare,
)
from talkback_validator.parsing import FieldType, parse_percentage, parse_signed_level

OK = CaptureValidity()


def visual(value, **kwargs):
    return VisualResult(value=value, channels={"ocr": value, "text_node": value}, **kwargs)


def test_exact_match_passes():
    result = compare(parse_percentage("Battery 85 percent"), visual(85), OK)
    assert result.verdict is Verdict.PASS
    assert result.reason is Reason.MATCH


def test_mismatch_fails():
    result = compare(parse_percentage("Battery 55 percent"), visual(85), OK)
    assert result.verdict is Verdict.FAIL
    assert result.reason is Reason.MISMATCH
    assert result.spoken_value == 55
    assert result.visual_value == 85


def test_volume_sign_lost_is_diagnosed():
    """The volume_sign defect: screen shows -3, TalkBack says level 3."""
    result = compare(
        parse_signed_level("Right volume, level 3"),
        visual(-3),
        OK,
        field_type=FieldType.SIGNED_LEVEL,
    )
    assert result.verdict is Verdict.FAIL
    assert result.reason is Reason.VOLUME_SIGN_LOST


def test_correct_negative_volume_passes():
    result = compare(
        parse_signed_level("Right volume, level minus 3"),
        visual(-3),
        OK,
        field_type=FieldType.SIGNED_LEVEL,
    )
    assert result.verdict is Verdict.PASS


def test_swapped_sides_fail():
    """swap_sides: left shows 85 but announces the right value 42."""
    result = compare(parse_percentage("Left battery, 42 percent"), visual(85), OK)
    assert result.verdict is Verdict.FAIL


def test_ambiguous_speech_is_inconclusive_not_fail():
    result = compare(parse_percentage("Battery 15%. Battery 50%."), visual(85), OK)
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.reason is Reason.SPOKEN_VALUE_AMBIGUOUS


def test_silence_is_inconclusive_not_fail():
    result = compare(parse_percentage(""), visual(85), CaptureValidity(silent=True))
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.reason is Reason.AUDIO_SILENT


def test_suppressed_accessibility_never_reports_fail():
    """A UiAutomation connection can mute TalkBack. That must not read as a defect."""
    result = compare(
        parse_percentage(""),
        visual(85),
        CaptureValidity(silent=True, accessibility_suppressed=True),
    )
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.reason is Reason.ACCESSIBILITY_SUPPRESSED


def test_unreadable_visual_is_inconclusive():
    result = compare(
        parse_percentage("Battery 85 percent"),
        VisualResult(value=None, readable=False),
        OK,
    )
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.reason is Reason.VISUAL_VALUE_UNREADABLE


def test_visual_channels_disagreeing_is_inconclusive():
    result = compare(
        parse_percentage("Battery 85 percent"),
        VisualResult(value=85, channels={"ocr": 85, "text_node": 86}, disagreement=True),
        OK,
    )
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.reason is Reason.VISUAL_CHANNELS_DISAGREE


def test_dumpsys_never_rescues_unreadable_visual():
    """dumpsys is corroboration; it must not stand in as the visual reference."""
    result = compare(
        parse_percentage("Battery 85 percent"),
        VisualResult(value=None, readable=False, channels={"dumpsys": 85}),
        OK,
    )
    assert result.verdict is Verdict.INCONCLUSIVE


def test_state_changed_is_inconclusive():
    result = compare(
        parse_percentage("Battery 85 percent"), visual(84), CaptureValidity(state_changed=True)
    )
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.reason is Reason.STATE_CHANGED


def test_unconfirmed_focus_is_inconclusive():
    result = compare(
        parse_percentage(""), visual(85), CaptureValidity(silent=True, focus_confirmed=False)
    )
    assert result.verdict is Verdict.INCONCLUSIVE
    assert result.reason is Reason.FOCUS_NOT_CONFIRMED


def test_control_capture_with_speech_is_error():
    result = compare(
        parse_percentage("Battery 85 percent"), visual(85), CaptureValidity(control_not_silent=True)
    )
    assert result.verdict is Verdict.ERROR
    assert result.reason is Reason.CONTROL_CAPTURE_NOT_SILENT


def test_infrastructure_error_is_error_not_fail():
    result = compare(
        parse_percentage(""), visual(85), CaptureValidity(infrastructure_error="adb device offline")
    )
    assert result.verdict is Verdict.ERROR
    assert result.reason is Reason.ADB_DISCONNECTED


def test_program_name_mismatch_is_diagnosed():
    from talkback_validator.parsing import parse_name_with_state

    result = compare(
        parse_name_with_state("Program, Universal, selected", ["Universal", "Music"]),
        visual("Music"),
        OK,
        field_type=FieldType.NAME_WITH_STATE,
    )
    assert result.verdict is Verdict.FAIL
    assert result.reason is Reason.PROGRAM_NAME_MISMATCH
