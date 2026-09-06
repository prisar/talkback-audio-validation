# AidSim test interface

This document plus `aidsim.apk` is everything a test team needs. No source access is required or implied.

AidSim is a **simulation fixture**, not a product. It renders a hearing-aid-style control surface and carries an on-screen `Simulation Mode` banner at all times. It talks to no hardware.

## Install

```bash
adb install -r aidsim.apk
```

Package and activity are discoverable from the APK itself:

```bash
aapt2 dump badging aidsim.apk | grep -E "package:|launchable-activity:"
```

## Launch and set state

```bash
adb shell am start -W -n com.talkbacklab.aidsim/.MainActivity \
  --ei left_battery 85 --ei right_battery 42 \
  --es left_volume "'4'" --es right_volume "'-3'" \
  --es program "'Noisy'" \
  --es defect none
```

| Extra | Type | Range | Default |
|---|---|---|---|
| `left_battery`, `right_battery` | int | 0..100 | 100 |
| `left_volume`, `right_volume` | int | -6..6 | 0 |
| `program` | string | `Universal`, `Noisy`, `Restaurant`, `Music` (any string is accepted) | `Universal` |
| `left_connected`, `right_connected` | bool | | true |
| `defect` | string | see below | `none` |

### Two shell gotchas that will cost you an hour

1. **Negative numbers must be passed as string extras.** `am start` parses `--ei right_volume -3` by treating `-3` as a command-line flag, and it then **silently discards every extra after it** — no error, no warning. Pass `--es right_volume "'-3'"` instead; the app parses string extras into integers. This is why string form is used above for volume.
2. **Values containing spaces need double quoting**: `--es program "'Custom Program'"`. With single quoting only, the local shell splits the value and the app receives only `Custom`.

State is re-read on every launch, including when the activity is already running.

## Reading values

The app sets `testTagsAsResourceId`, so every value is one accessibility node carrying `resource-id`, `content-desc`, and `text` together:

```bash
adb shell uiautomator dump /sdcard/d.xml && adb pull /sdcard/d.xml
```

| `resource-id` | `text` (displayed) | `content-desc` (spoken) |
|---|---|---|
| `chip_battery_left` / `_right` | `85%` | `Left battery, 85 percent` |
| `status_left_battery` / `status_right_battery` | `85%` | `Left hearing aid battery, 85 percent` |
| `status_left_connection` / `status_right_connection` | `Connected` | `Left hearing aid, connected` |
| `volume_left` / `volume_right` | `-3` | `Right volume, level minus 3` |
| `master_volume` | `0` | `Volume, level 0` |
| `program_name` | `Noisy` | `Program, Noisy, selected` |

`volume_left` and `volume_right` are inside the volume panel: tap `open_volume_panel`. The status cards are behind `chip_battery_left`. `volume_right` may sit below the fold on small screens; scroll before dumping.

**Warning:** `uiautomator dump` opens a `UiAutomation` connection, which suppresses TalkBack while it is active. Never dump during an audio recording window — you will capture silence and misread it as a TalkBack defect.

## Defect injection

`--es defect <mode>` corrupts **only `content-desc`. The visible `text` is never altered.** The screen stays correct while the screen reader lies, which is the defect class an audio-validation pipeline exists to catch.

| Mode | Effect | Verified behaviour at `left_battery=85` |
|---|---|---|
| `none` | correct labels | text `85%`, desc `...85 percent` |
| `battery_value` | spoken percentage differs from displayed | text `85%`, desc `...55 percent` |
| `swap_sides` | each side announces the other's value | text `85%`, desc `...42 percent` |
| `volume_sign` | negative volume announced without its sign | text `-3`, desc `level 3` |
| `missing_label` | no `content-desc` at all | text `85%`, desc empty |
| `a11y_suite` | five simultaneous defects, one per category (below) | see table below |

Every row above was confirmed on-device, not inferred.

### `a11y_suite`: five defect categories at once

For exercising an accessibility-scanning tool rather than the audio comparator. All five
are active together, each in a different category, and each verified on-device:

| # | Category | Element | Visible | Accessibility tree |
|---|---|---|---|---|
| 1 | Skipped element | `chip_battery_left` | `L 85%` | **absent entirely** - no focus, no announcement |
| 2 | Missing information | `chip_battery_right` | `R 42%` | `content-desc` = `Battery`, percentage omitted |
| 3 | Incorrect information | `programs_button` | `Programs` | `content-desc` = `Increase volume` |
| 4 | Unclear action | `open_volume_panel` | `L|R` | `content-desc` = `Button`, names no action or target |
| 5 | Inverted priority | status cards | `85%` + a dot | `status_*_indicator` = `Blue circle icon` is announced; `status_*_battery` is **absent** |

Defect 5 needs the status panel open (tap `chip_battery_right`). Defect 1 makes the left
chip unreachable by a screen reader while it stays visible and touchable.

The default `none` mode remains clean and correct, so a scanner can be validated against a
known-good baseline before being pointed at the defective one.

`volume_sign` is the most instructive case: `-3` announced as "level 3" is a one-character divergence that a fuzzy string comparison would very likely accept, and a human listening casually would probably miss.

## Expected pipeline usage

These extras reach a state. They are **not an answer key**. A validator should treat the screen as ground truth and must not feed the extras, the screenshot, or any expected value to a transcription model.
