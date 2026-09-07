"""Step definitions for features/comparison.feature.

The feature file is the spec, written for a reader who does not know Python.
These steps translate it into calls against the real `compare()` function -
nothing here re-implements the behavior, it only wires English to the API.
"""
from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from talkback_validator.comparison import CaptureValidity, Reason, Verdict, VisualResult, compare
from talkback_validator.parsing import FieldType, parse_name_with_state, parse_percentage, parse_signed_level

scenarios("../../features/comparison.feature")


@pytest.fixture
def context():
    return {
        "validity_kwargs": {},
        "field_type": FieldType.PERCENTAGE,
        "spoken_text": "",
        "known_values": [],
        "visual": None,
    }


@given("the capture was recorded cleanly")
def _(context):
    pass


@given(parsers.re(r'the screen shows the percentage (?P<value>\d+)'))
def _(context, value):
    value = int(value)
    context["visual"] = VisualResult(value=value, channels={"ocr": value, "text_node": value})
    context["field_type"] = FieldType.PERCENTAGE


@given(parsers.re(r'the screen shows the signed level (?P<value>-?\d+)'))
def _(context, value):
    value = int(value)
    context["visual"] = VisualResult(value=value, channels={"ocr": value, "text_node": value})
    context["field_type"] = FieldType.SIGNED_LEVEL


@given(parsers.re(r'the screen shows the program "(?P<selected>[^"]+)" selected from "(?P<options>[^"]+)"'))
def _(context, selected, options):
    context["visual"] = VisualResult(value=selected, channels={"ocr": selected, "text_node": selected})
    context["field_type"] = FieldType.NAME_WITH_STATE
    context["known_values"] = [name.strip() for name in options.split(",")]


@given("the screen could not be read")
def _(context):
    context["visual"] = VisualResult(value=None, readable=False)


@given("the screenshot and the accessibility tree disagree")
def _(context):
    context["visual"] = VisualResult(
        value=85, channels={"ocr": 85, "text_node": 86}, disagreement=True
    )


@given(parsers.parse('TalkBack announces "{text}"'))
def _(context, text):
    context["spoken_text"] = text


@given("the capture recorded silence")
def _(context):
    context["validity_kwargs"]["silent"] = True


@given("accessibility was suppressed during the capture")
def _(context):
    context["validity_kwargs"]["accessibility_suppressed"] = True


@given("the on-screen value changed during the capture")
def _(context):
    context["validity_kwargs"]["state_changed"] = True


@given("accessibility focus on the target was not confirmed")
def _(context):
    context["validity_kwargs"]["focus_confirmed"] = False


@given("the negative control captured speech")
def _(context):
    context["validity_kwargs"]["control_not_silent"] = True


@given(parsers.parse('the device reported "{message}"'))
def _(context, message):
    context["validity_kwargs"]["infrastructure_error"] = message


def _parse_spoken(context):
    field_type = context["field_type"]
    text = context["spoken_text"]
    if field_type is FieldType.SIGNED_LEVEL:
        return parse_signed_level(text)
    if field_type is FieldType.NAME_WITH_STATE:
        return parse_name_with_state(text, context["known_values"])
    return parse_percentage(text)


@when("the two channels are compared", target_fixture="result")
def _(context):
    spoken = _parse_spoken(context)
    validity = CaptureValidity(**context["validity_kwargs"])
    return compare(spoken, context["visual"], validity, field_type=context["field_type"])


@then(parsers.parse("the verdict is {verdict}"))
def _(result, verdict):
    assert result.verdict is Verdict[verdict]


@then(parsers.parse("the reason is {reason}"))
def _(result, reason):
    assert result.reason is Reason[reason]


@then(parsers.parse("the spoken value was recorded as {value:d}"))
def _(result, value):
    assert result.spoken_value == value


@then(parsers.parse("the visual value was recorded as {value:d}"))
def _(result, value):
    assert result.visual_value == value
