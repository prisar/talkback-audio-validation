# TalkBack audio validation

Validates that Android's screen reader **audibly speaks the value shown on screen**.

The phone speaks. A laptop microphone records the air. An AI speech model transcribes the
audio and nothing else. Deterministic Python compares that spoken value against the value
independently extracted from the screen.

```
Android UI -> TalkBack/TTS -> phone speaker -> air -> laptop microphone -> WAV -> ASR -> spoken value
Android UI -> screenshot/OCR + rendered text node ----------------------------> displayed value
                                    deterministic comparator -> PASS / FAIL / INCONCLUSIVE / ERROR
```

## One command

```bash
./run-demo.sh --replay     # no phone, no API key, works from a clean clone
./run-demo.sh              # full live run against a connected Android device
```

Both install dependencies, run the test suite, execute the pipeline, and open the report.
`make replay` and `make demo` are equivalent.

Start with `--replay`. It exercises the entire pipeline over committed fixtures and needs
nothing but `uv`.

`./run-demo.sh` **never builds the APK.** It installs `artifacts/aidsim.apk` — the one
already shipped in this repo — onto whatever device `adb devices` currently sees, then runs
against it. No Gradle, no Android SDK build tools, no app source tree, and no Appium are
needed for this to work; verified by running it with `talkback-demo-app/` deleted entirely.
If `artifacts/aidsim.apk` is ever missing, the script fails with the one command that
rebuilds it — it will not attempt that itself. If `adb` sees no device, it tells you to fall
back to `--replay` rather than hanging. If `tesseract` is missing and Homebrew can't install
it, the adb-only semantics-tree audit still runs to completion and the audio-capture
scenarios are skipped, not failed.

## What the demo shows

| Case | Verdict | Why |
|---|---|---|
| Battery announced correctly | `PASS` | spoken 85 equals displayed 85 |
| Injected `battery_value` defect | `FAIL` | screen shows 85%, speech says 55% |
| Negative volume with its sign | `PASS` | spoken -3 equals displayed -3 |
| Injected `volume_sign` defect | `FAIL` | screen shows `-3`, speech says "level 3" |
| Program name and state | `PASS` | name and selected state both match |
| Two conflicting percentages | `INCONCLUSIVE` | ambiguity is abstained on, never guessed |
| Silent capture | `INCONCLUSIVE` | silence is not evidence of a defect |
| Negative control, TalkBack off | silent | proves the microphone was recording TalkBack |

`volume_sign` is the case worth pausing on. `-3` announced as "level 3" is a
one-character divergence that fuzzy string matching would accept and a human listening
casually would likely miss.

## Semantics-tree audit, no microphone needed

`talkback-validator audit` walks the live accessibility tree instead of comparing a
configured field's spoken value against its displayed one, so it catches a different
class of defect: a control that is clickable but has no accessible name, or a name
generic enough to name nothing (`"Button"`, `"Image"`). It needs no ground truth and no
audio capture, only a running device.

```bash
uv run talkback-validator audit --defect none        # 0 findings on the clean baseline
uv run talkback-validator audit --defect a11y_suite   # flags open_volume_panel: "Button"
```

What it cannot catch: a label that reads fine but is simply wrong, e.g. a control
labelled "Increase volume" that actually opens Programs. Nothing in the tree
distinguishes that from a correct label without a ground truth this scanner does not
have. `AidSim`'s `a11y_suite` defect mode carries five defects on purpose; `audit`
detects the one that is structurally visible, `run` detects value mismatches, and
neither alone covers all five. See `docs/talkback-audio-validation/SPEC.md` §16 for the
full coverage table.

## Design

**The speech model only ever sees audio.** Not the screenshot, not the expected value, not
the intent extras, not a prior result. If it saw any of them it could infer the answer
instead of reporting it. Only the comparator sees both channels, and Python — not a model —
decides whether two values are equal.

**Four independent channels.** Screenshot OCR and the rendered text node are peers; the
accessibility label is the expected speech; `dumpsys battery` corroborates but never
arbitrates. Channels that disagree produce `INCONCLUSIVE`, not a silent tiebreak.

**Abstention is a first-class outcome.** `INCONCLUSIVE` and `ERROR` are never folded into a
passing count. A mismatch reports disagreement in one observation; it does not name a root
cause.

**One gotcha worth knowing.** A `UiAutomation` connection — `uiautomator dump`, an Appium
UiAutomator2 session — suppresses TalkBack by default. It silences the exact speech this
pipeline records, and the result looks like a TalkBack defect. Hierarchy reads are therefore
sequenced strictly outside every audio window, and accessibility settings are recorded on
both sides of each capture. A silent capture whose settings changed is reported as
`ACCESSIBILITY_SUPPRESSED`, never as `FAIL`.

## Layout

```
talkback-audio-validation/
├── run-demo.sh                 the master command
├── artifacts/                  aidsim.apk + INTERFACE.md   <- all the validator may use
├── talkback-demo-app/          AidSim source (Kotlin/Compose)
└── talkback-validator/         the pipeline (Python)
```

`AidSim` is a **simulation fixture**, not a product: its own name and design, a permanent
`Simulation Mode` banner, no hardware, and no asset or copy taken from any real application.
It exists to provide typed fields and injectable label defects.

### Black box by construction

A test automation team receives an APK, not source. The validator honours that:

- it reads only `artifacts/aidsim.apk` and `artifacts/INTERFACE.md`;
- package and activity come from `aapt2 dump badging`, never hardcoded;
- locators are discovered from runtime hierarchy dumps.

`tests/test_black_box_boundary.py` fails the build if any validator source references the
app tree or hardcodes its package name. Delete `talkback-demo-app/` entirely and the
validator still runs.

## Commands

```bash
cd talkback-validator
uv run talkback-validator doctor            # every prerequisite, with reasons
uv run talkback-validator audio-devices     # list microphone inputs
uv run talkback-validator run aidsim --defect volume_sign --control
uv run talkback-validator audit --defect a11y_suite   # semantics-tree scan, no ground truth needed
uv run talkback-validator replay fixtures
uv run talkback-validator serve-report      # dashboard on 127.0.0.1
uv run --with pytest pytest -q
```

Set `GEMINI_API_KEY` for the cloud speech backend. Without it the pipeline falls back to
recorded fixture transcripts, and every result records which backend produced it.

## Honest status

- The shipped fixtures are **synthesized speech, not device captures through air**. They
  exist so the replay path runs from a clean clone. The manifest and the report both say so.
  Replace them with real TalkBack captures before making any accuracy claim.
- Verified on a headless Android 16 emulator (`sdk_gphone64_x86_64`). The acoustic
  phone-to-microphone path needs a physical device.
- Deliberately not built yet, and specified in `docs/talkback-audio-validation/SPEC.md`:
  the Appium driver, offline Whisper/Gemma/Qwen backends, the full evaluation harness with
  model benchmarking, JUnit output and CI gates, and iOS/VoiceOver.

A green run means these observations agreed. It is not a general claim about TalkBack.
