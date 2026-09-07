# TalkBack Audio Validation — Evaluator Guide

Reference: this directory (`talkback-audio-validation/`). This document explains how an
evaluator runs the pipeline, what "evaluated" means in terms of verdicts and
reason codes, and walks through real, already-executed test cases — showing
what TalkBack said, what the screen showed, and why the comparator ruled the
way it did.

---

## 1. What is being evaluated

The tool checks a single claim: **does Android's TalkBack screen reader say
out loud the same value the screen is showing?** A UI test that reads the
accessibility tree cannot catch a bug where the tree is correct but the
*spoken label* is wrong — e.g. the screen shows `-3` but TalkBack announces
"level 3". This tool catches that class of bug by actually recording the
phone's speaker and comparing the transcript against an independently read
screen value.

```
screen -> TalkBack -> speaker -> air -> microphone -> WAV -> speech model -> spoken value
screen -> screenshot OCR + accessibility text node ------------------------> shown value
                    Python comparator -> PASS / FAIL / INCONCLUSIVE / ERROR
```

Two rules keep the result honest:

- **The speech model only ever receives audio.** Never the screenshot, the
  expected value, or the intent extras that set up the test scenario — so it
  cannot infer the right answer, only report what it heard.
- **Only the comparator (plain Python, not a model) ever sees both channels**
  and decides equality.

---

## 2. How an evaluator runs the setup

### 2.1 Zero-hardware smoke run (start here)

No phone, no microphone, no API key required. Runs from a clean clone against
six committed audio fixtures:

```bash
./run-demo.sh --replay
```

This does, in order:
1. Installs `uv` if missing, then `uv sync --quiet` (base dependencies only).
2. Runs the full pytest suite (`uv run --with pytest pytest -q`).
3. Executes `talkback-validator replay fixtures --out runs/replay`.
4. Opens the generated `runs/replay/index.html` dashboard in the browser.

### 2.2 Full live run against a real device

```bash
./run-demo.sh
```

This additionally installs `uv sync --extra cloud --extra capture --extra ocr --extra local`,
requires a connected Android phone over `adb` with TalkBack enabled, a working
microphone, and (for the default cloud backend) `GEMINI_API_KEY` set in
`talkback-validator/.env`. It side-loads the shipped `artifacts/aidsim.apk`
directly — **no Gradle build, no Android SDK, no app source is ever touched**
by the validator. That boundary is enforced by
`tests/test_black_box_boundary.py`, which fails the build if any validator
source imports or references the app's own source tree.

### 2.3 Prerequisite check

```bash
cd talkback-validator && uv run talkback-validator doctor
```

Prints an `[ok]/[FAIL]` line per prerequisite — device connectivity, TalkBack
enabled state, microphone availability, OCR engine, cloud model reachability,
local model reachability, and output-directory writability — and exits
non-zero if anything is missing.

### 2.4 Driving a specific scenario

```bash
uv run talkback-validator run aidsim --defect volume_sign --control
```

`--defect` sets the phone into a specific broken state (see §5); `--control`
adds one extra capture with TalkBack switched off, which should record
silence — the negative control described in §4.

### 2.5 Test suite

```bash
cd talkback-validator && uv run --with pytest pytest -q
```

138 tests, confirmed passing as of this write-up. Beyond ordinary coverage,
several are regression tests written for specific failures encountered during
development (torn JSON while a live log was being written concurrently, a
dead-server state leaving the UI's Run button disabled forever, a model
reporting itself unavailable while calls to it were actually succeeding,
etc.) — each locks down one real incident, not a checklist item.

---

## 3. The decision pipeline (how a verdict is reached)

`compare()` in `comparison.py` is the single function that ever sees both the
spoken value and the visual value. It resolves in a fixed gate order, so a
capture with a problem never gets to a PASS/FAIL comparison at all:

| Order | Gate | Outcome if it trips |
|---|---|---|
| 1 | Infrastructure error (adb dropped, mic unavailable) | `ERROR` |
| 2 | Negative control captured actual speech | `ERROR` — the whole run is untrusted |
| 3 | Accessibility settings changed mid-capture | `INCONCLUSIVE` (`ACCESSIBILITY_SUPPRESSED`) |
| 4 | Accessibility focus on the target never confirmed | `INCONCLUSIVE` (`FOCUS_NOT_CONFIRMED`) |
| 5 | Displayed value changed during the capture window | `INCONCLUSIVE` (`STATE_CHANGED`) |
| 6 | Audio truncated | `INCONCLUSIVE` (`AUDIO_TRUNCATED`) |
| 7 | OCR and the accessibility text node disagree with each other | `INCONCLUSIVE` (`VISUAL_CHANNELS_DISAGREE`) |
| 8 | Neither visual channel produced a readable value | `INCONCLUSIVE` (`VISUAL_VALUE_UNREADABLE`) |
| 9 | Transcript parsed to two conflicting values | `INCONCLUSIVE` (`SPOKEN_VALUE_AMBIGUOUS`) |
| 10 | Transcript parsed to a value outside the field's valid range | `INCONCLUSIVE` (`SPOKEN_VALUE_OUT_OF_RANGE`) |
| 11 | No value could be parsed out of the transcript at all | `INCONCLUSIVE` (`SPOKEN_VALUE_ABSENT` / `AUDIO_SILENT`) |
| 12 | Spoken value equals visual value | **`PASS`** (`MATCH`) |
| 13 | Spoken value differs from visual value | **`FAIL`** (`MISMATCH`, or a field-aware reason — see below) |

Two of the `FAIL` reasons are field-aware, not generic string mismatches:

- **`VOLUME_SIGN_LOST`** — for a `signed_level` field, when the spoken number
  equals the *absolute value* of a negative displayed number (`-3` shown,
  `3` heard). This is exactly the sign-drop bug the tool exists to catch.
- **`PROGRAM_NAME_MISMATCH`** — for a `name_with_state` field.

`INCONCLUSIVE` is a first-class result, never silently folded into a pass or
a fail — abstaining when the evidence doesn't support a decision is treated
as more honest than guessing.

---

## 4. The negative control

Every run can add one extra capture with TalkBack switched off. It should
record silence. Without it, a silent capture is ambiguous — did TalkBack fail
to speak, or was the microphone simply muted? If the control **does** pick up
sound, the run was recording the room, not the phone, and every other result
in that run is marked untrustworthy (`CONTROL_CAPTURE_NOT_SILENT`, gate #2
above — it fires before any per-field comparison runs).

---

## 5. Deliberately injected defects (how the tool proves it can fail)

The demo app (`com.talkbacklab.aidsim`) ships defect modes that corrupt
**only the spoken label** (`contentDescription`) while leaving the visible
text untouched — reproducing exactly the bug class this tool exists to
catch, and a bug class invisible to any test that reads the UI tree instead
of the audio:

| `--defect` | What breaks | Expected verdict |
|---|---|---|
| `none` | nothing; labels correct | `PASS` |
| `battery_value` | speech announces a different percentage than the screen | `FAIL` |
| `swap_sides` | left announces the right side's value | `FAIL` |
| `volume_sign` | `-3` on screen is announced as "level 3" | `FAIL` |
| `missing_label` | the control has no spoken label at all | `FAIL` |
| `a11y_suite` | five structural label faults, for the static tree audit | findings |

The defect flag is never visible to the comparator or the speech model — it
only sets the phone's state before capture starts.

---

## 6. The dashboard

Every run writes `runs/<name>/index.html` (self-contained, no server needed —
`run-demo.sh` opens it directly; `talkback-validator serve-report` serves one
over `127.0.0.1` when that's more convenient).

![TalkBack audio validation dashboard](artifacts/screenshots/dashboard.png)

Reading it top to bottom:

- **Header strip** — run mode (`replay (fixtures)` here, `live device` in a
  real run), driver (`adb` or `none`), backend (`gemini`/`whisper`/`fixture`),
  device identity, and generation timestamp. In this fixture-mode screenshot
  the box explicitly flags that the audio is *synthesized*, not a real device
  capture — the tool refuses to let a replay run masquerade as accuracy
  evidence.
- **Five summary tiles** — counts of `PASS`, `FAIL`, `INCONCLUSIVE`, `ERROR`,
  and **decision coverage** (`5/7` here): the fraction of captures that
  reached an actual PASS/FAIL decision rather than abstaining. Coverage is
  reported separately from the pass count on purpose — a run that abstains
  on everything would otherwise look deceptively clean.
- **Negative-control banner** — states the measured peak level and duration
  with TalkBack off, and whether it counted as silent. This is the run's own
  proof that it was listening to the phone and not the room.
- **Cases table** — one row per capture: id, scenario, field, `STATUS`,
  `REASON`, the **spoken** value, and the **displayed** value side by side —
  the literal heard-vs-rendered confrontation described in the README.
- **Evidence** — one expandable panel per case with the full transcript,
  screenshot, audio waveform, and event timeline (focus action, speech start,
  speech end), so a disagreement can be checked by ear and by eye instead of
  taken on faith.

---

## 7. Field types and how spoken text is parsed into a value

Deterministic Python — never a model — turns raw transcript text into a
comparable value:

| `field_type` | Recognizes | Example |
|---|---|---|
| `percentage` | a number immediately followed by `%` / "percent" | `"battery is 85%"` → `85` |
| `signed_level` | a number, anchored to the word "level" when the transcript contains noise numbers, with `minus`/`negative`/`-` giving the sign | `"level minus 3"` → `-3` |
| `name_with_state` | a known name from a supplied vocabulary, plus an optional "selected" state | `"Noisy Environment, selected"` → `Noisy`, state `selected` |
| `enum_state` | a known token from a supplied vocabulary | `"connected"` → `connected` |

Real Gemini transcripts are not clean sentences — they carry ASR noise around
the actual announcement (background words, stray digits, mis-heard
fragments). The parser is deliberately narrow: for `signed_level` it only
trusts a number that directly follows "level," and discards every other
number in the transcript once an anchored one is found — see the real
transcripts in §8 below, several of which contain exactly this kind of noise.

---

## 8. Passing test cases, explained (real executed run)

The run below (`runs/full-verified`) is a genuine on-device capture — model
`gemini-3.5-flash-lite` over an `adb`-driven Oppo `CPH2447`, defect `none` —
not a synthesized fixture. Three screens from the demo app show the values
these cases were checked against:

| Home | Volume panel | Status panel |
|---|---|---|
| ![AidSim home screen](artifacts/screenshots/home.png) | ![AidSim volume panel](artifacts/screenshots/volume.png) | ![AidSim hearing-aid status](artifacts/screenshots/status.png) |
| `L 85%`, `R 42%`, program "Noisy Environment" | Left `4` | Left/Right "Connected" |

For each case: what TalkBack actually said (raw transcript, unedited), what
the parser extracted from it, what the two visual channels independently
read off the screen, and the verdict.

### `left_battery-none` → **PASS** (`MATCH`)

| | |
|---|---|
| Heard (raw transcript) | *"All A/C is 85%."* |
| Parsed spoken value | `85` — the only number in the transcript followed by `%` |
| Shown (text node / OCR) | `85%` / `85%` → both channels agree: `85` |
| Verdict | **PASS** — spoken `85` == displayed `85` |

The transcript's leading words ("All A/C is") are ASR noise around the real
announcement; the `percentage` parser ignores everything that isn't a number
anchored to `%`, so the noise never enters the comparison.

### `right_battery-none` → **PASS** (`MATCH`)

| | |
|---|---|
| Heard | *"back on, left right battery 42%"* |
| Parsed spoken value | `42` |
| Shown | `42%` / `42%` → `42` |
| Verdict | **PASS** |

### `left_volume-none` → **PASS** (`MATCH`)

| | |
|---|---|
| Heard | *"on 878 left volume level 4"* |
| Parsed spoken value | `4` — anchored to the word "level"; the stray digits `878` earlier in the transcript are discarded because they are not level-anchored |
| Shown | `4` / `4` (matches the Volume panel screenshot above) |
| Verdict | **PASS** |

This is the clearest example of why the anchoring rule exists: a naive
"grab any number in the sentence" parser would have had to choose between
`878` and `4`, and could easily have picked wrong.

### `right_volume-none` → **PASS** (`MATCH`)

| | |
|---|---|
| Heard | *"Turn A7Q, right volume, level minus 3."* |
| Parsed spoken value | `-3` — "minus" immediately precedes the level-anchored number |
| Shown | `-3` / `-3` |
| Verdict | **PASS** |

This is the sign-preserving twin of the `volume_sign` defect described in
§5 — the exact case that, with the defect switched on, would announce
"level 3" for a screen still showing `-3` and correctly turn into a `FAIL`
with reason `VOLUME_SIGN_LOST`.

### `left_connection-none` → **PASS** (`MATCH`)

| | |
|---|---|
| Heard | *"Call 87, left hearing aid, connected."* |
| Parsed spoken value | `connected` — the only vocabulary token (`connected`/`disconnected`) present |
| Shown | `connected` / `connected` (matches the Status panel screenshot above) |
| Verdict | **PASS** |

### `program-none` → **INCONCLUSIVE** (`SPOKEN_VALUE_ABSENT`), for contrast

| | |
|---|---|
| Heard | *"on 8 7 back program noise cancel selective"* |
| Parsed spoken value | none — "noise cancel selective" doesn't match any name in the configured vocabulary closely enough to be recognized |
| Shown | `Noisy` / `Noisy` (screen: "Noisy Environment") |
| Verdict | **INCONCLUSIVE**, not FAIL — the tool declined to guess rather than force a decision the transcript doesn't support |

This case is included deliberately: it shows the comparator abstaining
instead of coercing a messy transcript into either a pass or a fail, which
is exactly the behavior §3 and §4 describe as a first-class result rather
than an edge case being swept under the rug.

**Run total: 5 PASS, 1 INCONCLUSIVE, 0 FAIL** — every field the parser could
extract a value for matched the screen; the one field it couldn't confidently
parse was correctly reported as inconclusive rather than silently scored
either way.

---

## 9. What a caught defect looks like

For a side-by-side of PASS against an actually-injected bug, the fixture
dashboard (`runs/replay-demo`, synthesized audio, `--replay` mode) carries
both in one run:

| id | field | status | reason | spoken | displayed |
|---|---|---|---|---|---|
| `battery-clean` | `left_battery` | PASS | `MATCH` | `85` | `85` |
| `battery-defect` | `left_battery` | **FAIL** | `MISMATCH` | `55` | `85` |
| `volume-clean` | `right_volume` | PASS | `MATCH` | `-3` | `-3` |
| `volume-sign-defect` | `right_volume` | **FAIL** | `VOLUME_SIGN_LOST` | `3` | `-3` |
| `ambiguous` | `left_battery` | INCONCLUSIVE | `SPOKEN_VALUE_AMBIGUOUS` | — | `85` |
| `silence` | `left_battery` | INCONCLUSIVE | `AUDIO_SILENT` | — | `85` |

The `volume-sign-defect` row is the one worth pausing on: the displayed value
never changes (`-3` throughout), only the announced sign is dropped — the
exact silent-failure class this whole tool was built to surface, and the one
a fuzzy string-match comparator (or a casual human listener) would most
plausibly wave through.

---

## Source references

- Pipeline overview and defect table: `README.md`
- Comparator gate order: `talkback-validator/src/talkback_validator/comparison.py`
- Parsing rules: `talkback-validator/src/talkback_validator/parsing.py`
- Dashboard renderer: `talkback-validator/src/talkback_validator/reporting.py`
- Real executed run used in §8: `talkback-validator/runs/full-verified/result.json`
- Fixture run used in §9: `talkback-validator/runs/replay-demo/result.json`
- Demo-app screenshots: `artifacts/screenshots/`
