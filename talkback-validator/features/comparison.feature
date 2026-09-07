Feature: Comparing what TalkBack said against what the screen shows
  The comparator is the only code that sees both channels. Given a spoken
  value, an independently read screen value, and what is known about the
  capture itself, it decides PASS, FAIL, INCONCLUSIVE, or ERROR - and never
  guesses when the evidence does not support a decision.

  Background:
    Given the capture was recorded cleanly

  Scenario: Speech matches the screen
    Given the screen shows the percentage 85
    And TalkBack announces "Battery 85 percent"
    When the two channels are compared
    Then the verdict is PASS
    And the reason is MATCH

  Scenario: Speech contradicts the screen
    Given the screen shows the percentage 85
    And TalkBack announces "Battery 55 percent"
    When the two channels are compared
    Then the verdict is FAIL
    And the reason is MISMATCH
    And the spoken value was recorded as 55
    And the visual value was recorded as 85

  Scenario: A negative sign is dropped in speech
    Given the screen shows the signed level -3
    And TalkBack announces "Right volume, level 3"
    When the two channels are compared
    Then the verdict is FAIL
    And the reason is VOLUME_SIGN_LOST

  Scenario: A negative sign is announced correctly
    Given the screen shows the signed level -3
    And TalkBack announces "Right volume, level minus 3"
    When the two channels are compared
    Then the verdict is PASS

  Scenario: The left and right sides are swapped
    Given the screen shows the percentage 85
    And TalkBack announces "Left battery, 42 percent"
    When the two channels are compared
    Then the verdict is FAIL

  Scenario: The wrong program name is diagnosed by name, not a generic mismatch
    Given the screen shows the program "Music" selected from "Universal, Music"
    And TalkBack announces "Program, Universal, selected"
    When the two channels are compared
    Then the verdict is FAIL
    And the reason is PROGRAM_NAME_MISMATCH

  Scenario: Ambiguous speech abstains instead of guessing
    Given the screen shows the percentage 85
    And TalkBack announces "Battery 15%. Battery 50%."
    When the two channels are compared
    Then the verdict is INCONCLUSIVE
    And the reason is SPOKEN_VALUE_AMBIGUOUS

  Scenario: Silence abstains instead of failing
    Given the screen shows the percentage 85
    And the capture recorded silence
    When the two channels are compared
    Then the verdict is INCONCLUSIVE
    And the reason is AUDIO_SILENT

  Scenario: TalkBack being suppressed is never mistaken for a defect
    Given the screen shows the percentage 85
    And the capture recorded silence
    And accessibility was suppressed during the capture
    When the two channels are compared
    Then the verdict is INCONCLUSIVE
    And the reason is ACCESSIBILITY_SUPPRESSED

  Scenario: An unreadable screen abstains
    Given the screen could not be read
    And TalkBack announces "Battery 85 percent"
    When the two channels are compared
    Then the verdict is INCONCLUSIVE
    And the reason is VISUAL_VALUE_UNREADABLE

  Scenario: Disagreeing visual channels abstain
    Given the screenshot and the accessibility tree disagree
    And TalkBack announces "Battery 85 percent"
    When the two channels are compared
    Then the verdict is INCONCLUSIVE
    And the reason is VISUAL_CHANNELS_DISAGREE

  Scenario: The value changing mid-capture abstains
    Given the screen shows the percentage 84
    And TalkBack announces "Battery 85 percent"
    And the on-screen value changed during the capture
    When the two channels are compared
    Then the verdict is INCONCLUSIVE
    And the reason is STATE_CHANGED

  Scenario: Unconfirmed accessibility focus abstains
    Given the screen shows the percentage 85
    And the capture recorded silence
    And accessibility focus on the target was not confirmed
    When the two channels are compared
    Then the verdict is INCONCLUSIVE
    And the reason is FOCUS_NOT_CONFIRMED

  Scenario: A noisy negative control makes the run untrustworthy
    Given the screen shows the percentage 85
    And TalkBack announces "Battery 85 percent"
    And the negative control captured speech
    When the two channels are compared
    Then the verdict is ERROR
    And the reason is CONTROL_CAPTURE_NOT_SILENT

  Scenario: A disconnected device is an error, not a fail
    Given the screen shows the percentage 85
    And the capture recorded silence
    And the device reported "adb device offline"
    When the two channels are compared
    Then the verdict is ERROR
    And the reason is ADB_DISCONNECTED
