from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .parsing import FieldType, ParseStatus, SpokenValue


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"


class Reason(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    VISUAL_VALUE_UNREADABLE = "VISUAL_VALUE_UNREADABLE"
    VISUAL_CHANNELS_DISAGREE = "VISUAL_CHANNELS_DISAGREE"
    SPOKEN_VALUE_AMBIGUOUS = "SPOKEN_VALUE_AMBIGUOUS"
    SPOKEN_VALUE_ABSENT = "SPOKEN_VALUE_ABSENT"
    SPOKEN_VALUE_OUT_OF_RANGE = "SPOKEN_VALUE_OUT_OF_RANGE"
    AUDIO_SILENT = "AUDIO_SILENT"
    AUDIO_TRUNCATED = "AUDIO_TRUNCATED"
    AUDIO_CLIPPED = "AUDIO_CLIPPED"
    ACCESSIBILITY_SUPPRESSED = "ACCESSIBILITY_SUPPRESSED"
    FOCUS_NOT_CONFIRMED = "FOCUS_NOT_CONFIRMED"
    ELEMENT_NOT_IN_A11Y_TREE = "ELEMENT_NOT_IN_A11Y_TREE"
    NAVIGATION_FAILED = "NAVIGATION_FAILED"
    STATE_CHANGED = "STATE_CHANGED"
    CONTROL_CAPTURE_NOT_SILENT = "CONTROL_CAPTURE_NOT_SILENT"
    VOLUME_SIGN_LOST = "VOLUME_SIGN_LOST"
    SIDE_BINDING_AMBIGUOUS = "SIDE_BINDING_AMBIGUOUS"
    PROGRAM_NAME_MISMATCH = "PROGRAM_NAME_MISMATCH"
    ADB_DISCONNECTED = "ADB_DISCONNECTED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MIC_UNAVAILABLE = "MIC_UNAVAILABLE"


@dataclass
class VisualResult:
    """Independently extracted on-screen value. Never sees audio."""

    value: object | None = None
    channels: dict = field(default_factory=dict)
    readable: bool = True
    disagreement: bool = False
    note: str = ""


@dataclass
class CaptureValidity:
    """Everything known about whether the recording is usable evidence."""

    silent: bool = False
    truncated: bool = False
    clipped: bool = False
    accessibility_suppressed: bool = False
    focus_confirmed: bool = True
    state_changed: bool = False
    control_not_silent: bool = False
    infrastructure_error: str | None = None
    duration_s: float = 0.0
    peak_level: float = 0.0


@dataclass
class CaseResult:
    verdict: Verdict
    reason: Reason
    spoken_value: object | None = None
    visual_value: object | None = None
    detail: str = ""
    diagnostics: list = field(default_factory=list)


def _resolve_visual(visual: VisualResult) -> CaseResult | None:
    if visual.disagreement:
        return CaseResult(
            Verdict.INCONCLUSIVE,
            Reason.VISUAL_CHANNELS_DISAGREE,
            visual_value=visual.value,
            detail=visual.note or "visual channels reported different values",
        )
    if not visual.readable or visual.value is None:
        return CaseResult(
            Verdict.INCONCLUSIVE,
            Reason.VISUAL_VALUE_UNREADABLE,
            detail=visual.note or "no visual channel produced a value",
        )
    return None


def _resolve_validity(validity: CaptureValidity) -> CaseResult | None:
    if validity.infrastructure_error:
        return CaseResult(
            Verdict.ERROR,
            Reason.ADB_DISCONNECTED
            if "adb" in validity.infrastructure_error.lower()
            else Reason.MIC_UNAVAILABLE,
            detail=validity.infrastructure_error,
        )
    if validity.control_not_silent:
        return CaseResult(
            Verdict.ERROR,
            Reason.CONTROL_CAPTURE_NOT_SILENT,
            detail="negative control captured speech; the run is not trustworthy",
        )
    if validity.accessibility_suppressed:
        return CaseResult(
            Verdict.INCONCLUSIVE,
            Reason.ACCESSIBILITY_SUPPRESSED,
            detail="accessibility settings changed across the capture window",
        )
    if not validity.focus_confirmed:
        return CaseResult(
            Verdict.INCONCLUSIVE,
            Reason.FOCUS_NOT_CONFIRMED,
            detail="accessibility focus on the target was not confirmed",
        )
    if validity.state_changed:
        return CaseResult(
            Verdict.INCONCLUSIVE,
            Reason.STATE_CHANGED,
            detail="displayed value changed across the capture window",
        )
    if validity.truncated:
        return CaseResult(Verdict.INCONCLUSIVE, Reason.AUDIO_TRUNCATED)
    return None


def _diagnose_mismatch(spoken, visual, field_type: FieldType) -> tuple[Reason, str]:
    if field_type == FieldType.SIGNED_LEVEL:
        if isinstance(spoken, int) and isinstance(visual, int):
            if spoken == abs(visual) and visual < 0:
                return (
                    Reason.VOLUME_SIGN_LOST,
                    f"displayed {visual}, announced {spoken}: the sign was dropped",
                )
    if field_type == FieldType.NAME_WITH_STATE:
        return (Reason.PROGRAM_NAME_MISMATCH, f"displayed {visual!r}, announced {spoken!r}")
    return (Reason.MISMATCH, f"displayed {visual!r}, announced {spoken!r}")


def compare(
    spoken: SpokenValue,
    visual: VisualResult,
    validity: CaptureValidity,
    field_type: FieldType = FieldType.PERCENTAGE,
) -> CaseResult:
    """The only function that sees both channels. Python decides equality, not a model."""
    blocked = _resolve_validity(validity)
    if blocked is not None:
        return blocked

    blocked = _resolve_visual(visual)
    if blocked is not None:
        return blocked

    if spoken.status is ParseStatus.AMBIGUOUS:
        return CaseResult(
            Verdict.INCONCLUSIVE,
            Reason.SPOKEN_VALUE_AMBIGUOUS,
            visual_value=visual.value,
            detail=f"candidates: {spoken.candidates}",
        )
    if spoken.status is ParseStatus.OUT_OF_RANGE:
        return CaseResult(
            Verdict.INCONCLUSIVE,
            Reason.SPOKEN_VALUE_OUT_OF_RANGE,
            spoken_value=spoken.value,
            visual_value=visual.value,
        )
    if spoken.status is ParseStatus.NO_VALUE:
        reason = Reason.AUDIO_SILENT if validity.silent else Reason.SPOKEN_VALUE_ABSENT
        return CaseResult(
            Verdict.INCONCLUSIVE,
            reason,
            visual_value=visual.value,
            detail=spoken.note or "no value could be extracted from the audio",
        )

    if spoken.value == visual.value:
        return CaseResult(
            Verdict.PASS,
            Reason.MATCH,
            spoken_value=spoken.value,
            visual_value=visual.value,
        )

    reason, detail = _diagnose_mismatch(spoken.value, visual.value, field_type)
    return CaseResult(
        Verdict.FAIL,
        reason,
        spoken_value=spoken.value,
        visual_value=visual.value,
        detail=detail,
    )
