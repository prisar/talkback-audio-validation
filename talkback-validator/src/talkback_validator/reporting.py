from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

STATUS_GLYPH = {"PASS": "●", "FAIL": "▲", "INCONCLUSIVE": "■", "ERROR": "✖"}
STATUS_ORDER = ("PASS", "FAIL", "INCONCLUSIVE", "ERROR")

FAVICON = "data:image/svg+xml,%3Csvg%20xmlns=%27http://www.w3.org/2000/svg%27%20viewBox=%270%200%2032%2032%27%3E%3Crect%20width=%2732%27%20height=%2732%27%20rx=%277%27%20fill=%27%230c7a6c%27/%3E%3Crect%20x=%277%27%20y=%279%27%20width=%2718%27%20height=%273%27%20rx=%271.5%27%20fill=%27%23fff%27/%3E%3Crect%20x=%277%27%20y=%2720%27%20width=%2718%27%20height=%273%27%20rx=%271.5%27%20fill=%27%23fff%27/%3E%3C/svg%3E"

SPEECH_THRESHOLD = 0.02
LEVEL_FULL_SCALE = 0.10

CSS = """
:root {
  --paper: #e9edf2; --card: #ffffff; --ink: #0d1520; --muted: #56646f;
  --line: #ccd6e0; --rule: #aab8c6;
  --pass: #0c7a6c; --fail: #c5330f; --incon: #9a6c05; --error: #63489c;
  --ear-l: #1a4fd6; --ear-r: #c8102e; --accent: #0c7a6c;
  --shadow: 0 1px 2px rgba(13, 21, 32, .06), 0 8px 24px -16px rgba(13, 21, 32, .3);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #0a0f16; --card: #121b25; --ink: #e5ecf3; --muted: #8b9aa9;
    --line: #223040; --rule: #35485c;
    --pass: #2ec4a6; --fail: #ff7a5c; --incon: #dda62c; --error: #b096e6;
    --ear-l: #6f9dff; --ear-r: #ff6f83; --accent: #2ec4a6;
    --shadow: 0 1px 2px rgba(0, 0, 0, .5), 0 10px 30px -18px rgba(0, 0, 0, .9);
  }
}
:root[data-theme="dark"] {
  --paper: #0a0f16; --card: #121b25; --ink: #e5ecf3; --muted: #8b9aa9;
  --line: #223040; --rule: #35485c;
  --pass: #2ec4a6; --fail: #ff7a5c; --incon: #dda62c; --error: #b096e6;
  --ear-l: #6f9dff; --ear-r: #ff6f83; --accent: #2ec4a6;
  --shadow: 0 1px 2px rgba(0, 0, 0, .5), 0 10px 30px -18px rgba(0, 0, 0, .9);
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, ui-sans-serif, sans-serif;
  font-feature-settings: "kern" 1;
}
.mono, code, .val, .eyebrow, .cap, h1, .seg, .stamp dd, .tag, .reason {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}
.wrap { max-width: 1040px; margin: 0 auto; padding: 0 24px 96px; }
a { color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 3px; }

.masthead { padding: 56px 0 28px; border-bottom: 1px solid var(--rule); }
.eyebrow { margin: 0 0 14px; font-size: 11px; letter-spacing: .2em;
  text-transform: uppercase; color: var(--accent); }
h1 { margin: 0 0 14px; font-size: clamp(26px, 4.4vw, 40px); font-weight: 600;
  letter-spacing: -.02em; line-height: 1.1; }
.lede { margin: 0; max-width: 60ch; color: var(--muted); font-size: 15.5px; }
.stamp { display: flex; flex-wrap: wrap; gap: 6px 34px; margin: 26px 0 0; }
.stamp div { min-width: 0; }
.stamp dt { font-size: 10.5px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 3px; }
.stamp dd { margin: 0; font-size: 13px; overflow-wrap: anywhere; }

section { margin: 44px 0 0; }
h2 { margin: 0 0 14px; font-size: 12px; letter-spacing: .16em;
  text-transform: uppercase; color: var(--muted); font-weight: 600; }

.meter { display: flex; gap: 3px; height: 58px; }
.meter .seg { display: flex; align-items: center; gap: 9px; min-width: fit-content;
  padding: 0 16px; border-radius: 4px; color: #fff; white-space: nowrap;
  font-size: 12px; letter-spacing: .1em; text-transform: uppercase; }
.meter .seg b { font-size: 21px; letter-spacing: -.01em; }
.seg.PASS { background: var(--pass); } .seg.FAIL { background: var(--fail); }
.seg.INCONCLUSIVE { background: var(--incon); } .seg.ERROR { background: var(--error); }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) .meter .seg { color: #06110d; }
}
:root[data-theme="dark"] .meter .seg { color: #06110d; }
.meter .empty { flex: 1; border: 1px dashed var(--line); border-radius: 4px;
  display: flex; align-items: center; padding: 0 16px; color: var(--muted); font-size: 13px; }

.findings { margin: 18px 0 0; padding: 0; list-style: none; }
.findings li { display: flex; gap: 12px; padding: 9px 0; border-top: 1px solid var(--line);
  font-size: 14px; align-items: baseline; }
.findings li:first-child { border-top: none; }
.findings .who { font-weight: 600; }
.findings .what { color: var(--muted); }
.allclear { margin: 18px 0 0; font-size: 14px; color: var(--muted); }

.control { display: flex; flex-wrap: wrap; align-items: center; gap: 14px 20px;
  background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 16px 18px; box-shadow: var(--shadow); }
.tag { font-size: 10.5px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--muted); }
.level { position: relative; flex: 1 1 220px; height: 10px; min-width: 180px;
  background: var(--paper); border: 1px solid var(--line); border-radius: 999px; }
.level .fill { position: absolute; inset: 0 auto 0 0; border-radius: 999px; }
.level .mark { position: absolute; top: -5px; bottom: -5px; width: 2px;
  background: var(--rule); }
.control p { margin: 0; flex: 1 1 100%; font-size: 13.5px; color: var(--muted); }
.control p strong { color: var(--ink); }

.case { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  margin: 0 0 14px; box-shadow: var(--shadow); overflow: hidden; }
.case-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 14px 18px; border-bottom: 1px solid var(--line); }
.ear { width: 22px; height: 22px; border-radius: 5px; display: grid; place-items: center;
  font-size: 11px; font-weight: 700; color: #fff; flex: none; }
.ear.L { background: var(--ear-l); } .ear.R { background: var(--ear-r); }
.ear.none { background: none; border: 1px dashed var(--line); }
.case-head .name { font-weight: 600; font-size: 15px; }
.case-head .type { font-size: 12px; color: var(--muted); }
.case-head .badge { margin-left: auto; font-size: 12px; font-weight: 700;
  letter-spacing: .08em; white-space: nowrap; }
.badge.PASS { color: var(--pass); } .badge.FAIL { color: var(--fail); }
.badge.INCONCLUSIVE { color: var(--incon); } .badge.ERROR { color: var(--error); }

.confront { display: grid; align-items: center; gap: 18px; padding: 26px 18px 22px;
  grid-template-columns: minmax(0, 1fr) minmax(150px, 240px) minmax(0, 1fr); }
.side { min-width: 0; }
.side.shown { text-align: right; }
.cap { display: block; font-size: 10.5px; letter-spacing: .16em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 6px; }
.val { display: block; font-size: clamp(24px, 4.6vw, 36px); font-weight: 600;
  letter-spacing: -.02em; line-height: 1.1; overflow-wrap: anywhere; }
.val.absent { color: var(--muted); font-size: 15px; font-weight: 500;
  letter-spacing: .02em; }
.src { display: block; margin-top: 7px; font-size: 12px; color: var(--muted);
  overflow-wrap: anywhere; }
.link { position: relative; text-align: center; }
.link::before { content: ""; position: absolute; left: 0; right: 0; top: 50%;
  height: 2px; margin-top: -1px; }
.reason { position: relative; display: inline-block; padding: 0 9px;
  background: var(--card); font-size: 10.5px; letter-spacing: .1em;
  text-transform: uppercase; }
.case.PASS .reason { color: var(--pass); }
.case.PASS .link::before { background: var(--pass); }
.case.FAIL .reason { color: var(--fail); }
.case.INCONCLUSIVE .reason { color: var(--incon); }
.case.ERROR .reason { color: var(--error); }
.case.FAIL .val { color: var(--fail); }
.case.FAIL .link::before { background: repeating-linear-gradient(90deg,
  var(--fail) 0 7px, transparent 7px 14px); }
.case.INCONCLUSIVE .link::before { background: repeating-linear-gradient(90deg,
  var(--incon) 0 7px, transparent 7px 14px); }
.case.ERROR .link::before { background: repeating-linear-gradient(90deg,
  var(--error) 0 7px, transparent 7px 14px); }

.quote { margin: 0; padding: 0 18px 20px; }
.quote q { color: var(--muted); font-size: 14.5px; font-style: italic; }
.quote .none { color: var(--muted); font-size: 14px; }

.warn { margin: 0 18px 20px; padding: 11px 14px; border-radius: 8px;
  border-left: 3px solid var(--incon); background: var(--paper);
  font-size: 13px; color: var(--muted); }
.warn strong { color: var(--ink); }

details.evidence { border-top: 1px solid var(--line); }
details.evidence > summary { cursor: pointer; padding: 12px 18px; font-size: 12px;
  letter-spacing: .12em; text-transform: uppercase; color: var(--muted);
  list-style: none; display: flex; align-items: center; gap: 9px; }
details.evidence > summary::-webkit-details-marker { display: none; }
details.evidence > summary::before { content: "+"; font-family: ui-monospace, monospace;
  font-size: 14px; line-height: 1; }
details.evidence[open] > summary::before { content: "\2212"; }
details.evidence > summary:hover { color: var(--ink); }
details.evidence[open] > summary { border-bottom: 1px solid var(--line); }
.evidence-body { padding: 18px; display: grid; gap: 22px; }
h3 { margin: 0 0 9px; font-size: 11px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; }
.kv { display: grid; grid-template-columns: minmax(120px, 190px) 1fr; gap: 5px 16px;
  font-size: 13.5px; }
.kv dt { color: var(--muted); }
.kv dd { margin: 0; overflow-wrap: anywhere; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; min-width: 440px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line);
  vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 10.5px;
  text-transform: uppercase; letter-spacing: .1em; }
tr:last-child td { border-bottom: none; }
audio { width: 100%; max-width: 420px; }
.shots { display: flex; gap: 16px; flex-wrap: wrap; }
.shots figure { margin: 0; max-width: 240px; }
.shots img { max-width: 100%; border: 1px solid var(--line); border-radius: 8px;
  display: block; }
.shots figcaption { font-size: 12px; color: var(--muted); margin-top: 6px; }

.panel { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 18px; box-shadow: var(--shadow); }
.panel .hint { margin: 0 0 18px; font-size: 13.5px; color: var(--muted); max-width: 62ch; }
.panel .group { margin: 0 0 16px; }
.panel .group > span { display: block; font-size: 10.5px; letter-spacing: .14em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }
.panel label { display: inline-flex; align-items: center; gap: 7px; margin: 0 16px 8px 0;
  font-size: 14px; cursor: pointer; }
.panel input { accent-color: var(--accent); }
.panel button { font: inherit; font-weight: 600; padding: 10px 22px; border-radius: 8px;
  cursor: pointer; border: 1px solid transparent; background: var(--accent);
  color: var(--card); }
.panel button:hover { filter: brightness(1.08); }
.panel button[disabled] { opacity: .55; cursor: progress; filter: none; }
.models { display: grid; gap: 2px; }
.models .row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 11px 0; border-top: 1px solid var(--line); font-size: 14px; }
.models .row:first-child { border-top: none; }
.models .id { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 600; min-width: 150px; }
.models .roles { font-size: 11px; letter-spacing: .1em; text-transform: uppercase;
  color: var(--muted); }
.models .size { color: var(--muted); font-size: 13px; }
.models .why { flex: 1 1 100%; font-size: 13px; color: var(--muted); }
.models .why.stop { color: var(--incon); }
.models .act { margin-left: auto; }
.models button { padding: 6px 14px; font-size: 13px; }
.models button.ghost { background: none; border-color: var(--line); color: var(--muted); }
.models .on { color: var(--pass); font-weight: 600; font-size: 13px; }
#rerun-log:empty { display: none; }
#rerun-log { white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px; line-height: 1.5; color: var(--muted); margin-top: 16px;
  max-height: 220px; overflow: auto; background: var(--paper);
  border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; }

.footnote { margin: 44px 0 0; padding-top: 20px; border-top: 1px solid var(--rule); }
.footnote p { margin: 0; font-size: 13.5px; color: var(--muted); max-width: 68ch; }

@media (max-width: 620px) {
  .confront { grid-template-columns: 1fr; gap: 20px; }
  .side.shown { text-align: left; }
  .link { min-width: 0; align-items: flex-start; }
  .meter { height: auto; flex-direction: column; }
  .meter .seg { padding: 12px 16px; }
}

@media (prefers-reduced-motion: no-preference) {
  .case, .meter .seg { animation: rise .55s cubic-bezier(.22,.7,.28,1) backwards; }
  @keyframes rise { from { opacity: 0; transform: translateY(10px); } }
}
"""


RERUN_SCRIPT = """
const btn = document.getElementById('rerun-go');
const log = document.getElementById('rerun-log');
function picked(name) {
  return Array.from(document.querySelectorAll('input[name="' + name + '"]:checked'))
    .map(function (i) { return i.value; });
}
async function poll() {
  let r;
  try {
    r = await fetch('status').then(function (x) { return x.json(); });
  } catch (err) {
    log.textContent = 'Lost contact with the server while the run was in flight.';
    btn.disabled = false;
    btn.textContent = 'Run selected';
    return;
  }
  log.textContent = r.log;
  log.scrollTop = log.scrollHeight;
  if (r.running) { setTimeout(poll, 1000); return; }
  btn.disabled = false;
  btn.textContent = 'Run selected';
  if (r.exit_code === 0) { location.reload(); }
  else { loadModels(); }
}
function release(message) {
  log.textContent = message;
  btn.disabled = false;
  btn.textContent = 'Run selected';
}
async function loadModels() {
  const host = document.getElementById('model-list');
  let data;
  try {
    data = await fetch('models').then(function (x) { return x.json(); });
  } catch (err) {
    return;
  }
  const readers = document.querySelector('input[name="screen_reader"]').parentNode.parentNode;
  host.innerHTML = '';
  data.models.forEach(function (m) {
    const row = document.createElement('div');
    row.className = 'row';
    const roles = m.roles.length ? m.roles.join(' + ') : 'neither channel';
    row.innerHTML = '<span class="id">' + m.id + '</span>' +
      '<span class="roles">' + roles + '</span>' +
      '<span class="size">' + m.size_gb.toFixed(1) + ' GB</span>';
    const act = document.createElement('span');
    act.className = 'act';
    if (m.blocked) {
      act.innerHTML = '<span class="size">unavailable</span>';
    } else if (m.installed) {
      act.innerHTML = '<span class="on">installed</span>';
    } else {
      const go = document.createElement('button');
      go.type = 'button';
      go.className = 'ghost';
      go.textContent = 'Install';
      go.addEventListener('click', function () { install(m.id, go); });
      act.appendChild(go);
    }
    row.appendChild(act);
    if (m.blocked || m.note) {
      const why = document.createElement('span');
      why.className = m.blocked ? 'why stop' : 'why';
      why.textContent = m.blocked || m.note;
      row.appendChild(why);
    }
    host.appendChild(row);
    if (m.installed && m.roles.indexOf('vision') >= 0) {
      if (!document.querySelector('input[name="screen_reader"][value="' + m.id + '"]')) {
        const label = document.createElement('label');
        label.innerHTML = '<input type="radio" name="screen_reader" value="' + m.id +
          '"> ' + m.id + ' (local)';
        readers.appendChild(label);
      }
    }
  });
}
async function install(model, button) {
  button.disabled = true;
  button.textContent = 'Installing...';
  log.textContent = 'starting download...';
  let res;
  try {
    res = await fetch('install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: model })
    });
  } catch (err) {
    button.disabled = false;
    button.textContent = 'Install';
    release('Cannot reach the server that published this page.');
    return;
  }
  if (!res.ok) {
    button.disabled = false;
    button.textContent = 'Install';
    release(res.status === 409
      ? 'Something is already running on this device. Wait for it to finish.'
      : 'The server refused the install (' + res.status + ').');
    return;
  }
  btn.disabled = true;
  poll();
}
loadModels();
btn.addEventListener('click', async function () {
  const fields = picked('field');
  if (!fields.length) { log.textContent = 'Select at least one field.'; return; }
  btn.disabled = true;
  btn.textContent = 'Running on device...';
  log.textContent = 'starting...';
  let res;
  try {
    res = await fetch('rerun', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fields: fields,
        backend: picked('backend')[0],
        screen_reader: picked('screen_reader')[0],
        local_only: picked('local_only').length > 0,
        defect: picked('defect')[0],
        control: picked('control').length > 0
      })
    });
  } catch (err) {
    release('Cannot reach the server that published this page. Start it again ' +
      'with: talkback-validator serve-report ' + '(a report opened from disk is read-only).');
    return;
  }
  if (res.status === 409) { release('A run is already in progress on this device.'); return; }
  if (!res.ok) { release('The server refused the run (' + res.status + ').'); return; }
  poll();
});
"""

DEFECTS = ("none", "battery_value", "swap_sides", "volume_sign", "missing_label", "a11y_suite")


def _rerun_panel(run: dict) -> str:
    """Runs are issued from the report itself so a disagreement can be
    re-observed immediately, on the same device, without reconstructing the
    command. The selections are capture inputs only -- never an expected
    value -- so the comparator still learns nothing from this form."""
    cases = run.get("cases", [])
    fields = run.get("available_fields") or sorted(
        {c.get("field") for c in cases if c.get("field")}
    )
    if not fields:
        return ""
    ran = {c.get("field") for c in cases}
    env = run.get("environment", {})
    current_backend = "whisper" if "whisper" in str(env.get("backend") or "") else "gemini"
    current_defect = str(run.get("defect") or "none")

    field_boxes = "".join(
        f"<label><input type='checkbox' name='field' value='{_esc(f)}'"
        f"{' checked' if f in ran else ''}> {_esc(f)}</label>"
        for f in fields
    )
    backend_radios = "".join(
        f"<label><input type='radio' name='backend' value='{b}'"
        f"{' checked' if b == current_backend else ''}> {label}</label>"
        for b, label in (("gemini", "Gemini (cloud)"), ("whisper", "Whisper (local)"))
    )
    reader_radios = "".join(
        f"<label><input type='radio' name='screen_reader' value='{value}'"
        f"{' checked' if value == 'auto' else ''}> {label}</label>"
        for value, label in (
            ("auto", "Auto"),
            ("gemini", "Gemini (cloud)"),
            ("tesseract", "Tesseract (local OCR)"),
        )
    )
    defect_radios = "".join(
        f"<label><input type='radio' name='defect' value='{d}'"
        f"{' checked' if d == current_defect else ''}> {_esc(d)}</label>"
        for d in DEFECTS
    )
    return f"""<section><h2>Run</h2>
<div class="panel">
<p class="hint">Captures live audio from the connected phone. Keep the laptop microphone
near its speaker while the run is in flight.</p>
<div class="group"><span>Fields</span>{field_boxes}</div>
<div class="group"><span>Transcription backend</span>{backend_radios}</div>
<div class="group"><span>Screen reader</span>{reader_radios}</div>
<div class="group"><span>Injected defect</span>{defect_radios}</div>
<div class="group"><label><input type="checkbox" name="control" value="1" checked>
Include the TalkBack-disabled negative control</label>
<label><input type="checkbox" name="local_only" value="1">
Local only: block all network access for the run</label></div>
<button id="rerun-go" type="button">Run selected</button>
<div id="rerun-log"></div>
</div></section>

<section><h2>Models</h2>
<div class="panel">
<p class="hint">Nothing here is downloaded until you ask for it. A model marked local
runs entirely on this machine; combined with <em>Local only</em> above, the run is
executed behind a guard that blocks every non-loopback connection, so an accidental
call to a hosted API fails instead of succeeding quietly.</p>
<div class="models" id="model-list">
<p class="hint">The model list loads when this report is served. Start it with
<code>talkback-validator serve-report</code>.</p>
</div>
</div></section>"""


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _rel(path, base: Path) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def _side(field: str) -> str:
    name = str(field or "").lower()
    if name.startswith("left"):
        return "L"
    if name.startswith("right"):
        return "R"
    return ""


def _display(value) -> str:
    if value is None or value == "":
        return "not recovered"
    return _esc(value)


def _stamp(env: dict) -> str:
    """Device identity arrives as a JSON blob; unpacked here so the masthead
    reads as a lab stamp rather than as a serialised dict."""
    items: list[tuple[str, str]] = []
    for key, value in env.items():
        if key == "device":
            try:
                device = json.loads(value) if isinstance(value, str) else dict(value)
            except (ValueError, TypeError):
                items.append((key, str(value)))
                continue
            phone = " ".join(
                part
                for part in (
                    device.get("model", ""),
                    f"Android {device['android_version']}" if device.get("android_version") else "",
                    device.get("locale", ""),
                )
                if part
            )
            items.append(("phone", phone or str(value)))
        else:
            items.append((key, str(value)))
    return "".join(
        f"<div><dt>{_esc(k)}</dt><dd>{_esc(v)}</dd></div>" for k, v in items
    )


def _meter(counts: dict, total: int) -> str:
    if not total:
        return "<div class='meter'><div class='empty'>No fields observed.</div></div>"
    segments = "".join(
        f"<div class='seg {s}' style='flex-grow:{counts[s]};animation-delay:{i * 70}ms'>"
        f"<b>{counts[s]}</b> {s.lower()}</div>"
        for i, s in enumerate(STATUS_ORDER)
        if counts[s]
    )
    summary = ", ".join(f"{counts[s]} {s.lower()}" for s in STATUS_ORDER if counts[s])
    return (
        f"<div class='meter' role='img' aria-label='{_esc(total)} fields: {_esc(summary)}'>"
        f"{segments}</div>"
    )


def _findings(cases: list) -> str:
    open_cases = [c for c in cases if c.get("status") != "PASS"]
    if not cases:
        return ""
    if not open_cases:
        return (
            "<p class='allclear'>Every field agreed. The spoken value and the displayed "
            "value were recovered independently and matched in all "
            f"{len(cases)} observations.</p>"
        )
    rows = "".join(
        f"<li><span class='who mono'>{_esc(c.get('field'))}</span>"
        f"<span class='what'>{_esc(c.get('detail') or c.get('reason'))}</span></li>"
        for c in open_cases
    )
    return f"<ul class='findings'>{rows}</ul>"


def _control_strip(control: dict | None) -> str:
    if control is None:
        return (
            "<div class='control'><span class='tag'>Negative control</span>"
            "<p><strong>Not captured in this run.</strong> Without a TalkBack-disabled "
            "recording, a silent result cannot be told apart from a microphone that was "
            "never working.</p></div>"
        )
    peak = float(control.get("peak_level", 0) or 0)
    silent = bool(control.get("silent", False))
    width = min(100.0, peak / LEVEL_FULL_SCALE * 100)
    mark = min(100.0, SPEECH_THRESHOLD / LEVEL_FULL_SCALE * 100)
    colour = "var(--pass)" if silent else "var(--fail)"
    verdict = "silent, as it should be" if silent else "picked up sound"
    tail = (
        "This is what separates recording TalkBack from recording the room."
        if silent
        else "Speech was detected with the screen reader off, so the run cannot be trusted "
        "to have recorded TalkBack rather than ambient noise."
    )
    return f"""<div class="control">
<span class="tag">Negative control</span>
<div class="level" role="img"
  aria-label="peak level {peak:.3f} against a speech threshold of {SPEECH_THRESHOLD}">
  <div class="fill" style="width:{width:.1f}%;background:{colour}"></div>
  <div class="mark" style="left:{mark:.1f}%"></div>
</div>
<p>With TalkBack disabled the microphone <strong>{verdict}</strong>: peak
{peak:.3f} over {float(control.get('duration_s', 0) or 0):.1f}s against a speech
threshold of {SPEECH_THRESHOLD} (marked on the scale). {tail}</p>
</div>"""


def _evidence(case: dict, base: Path) -> str:
    rows = [
        ("Case", case.get("id")),
        ("Scenario", case.get("scenario")),
        ("Reason", case.get("reason")),
        ("Detail", case.get("detail")),
        ("Transcript", case.get("transcript")),
        ("Backend / model", f"{case.get('backend')} / {case.get('model')}"),
        ("Prompt version", case.get("prompt_version")),
        ("Driver", case.get("driver")),
        ("Focus method", case.get("focus_method")),
    ]
    a11y = case.get("accessibility") or {}
    if a11y:
        rows += [
            ("Accessibility before", a11y.get("before")),
            ("Accessibility after", a11y.get("after")),
        ]
    kv = "".join(
        f"<dt>{_esc(k)}</dt><dd>{_esc(v)}</dd>" for k, v in rows if v not in (None, "")
    )

    channels = case.get("channels") or {}
    ch_rows = "".join(
        f"<tr><td class='mono'>{_esc(name)}</td><td class='mono'>{_esc(data.get('raw'))}</td>"
        f"<td class='mono'>{_esc(data.get('value'))}</td>"
        f"<td class='mono'>{_esc(data.get('error', ''))}</td></tr>"
        for name, data in channels.items()
    )
    ch_block = (
        "<div><h3>Visual channels</h3><div class='scroll'><table>"
        "<tr><th>Channel</th><th>Raw</th><th>Parsed</th><th>Error</th></tr>"
        f"{ch_rows}</table></div></div>"
        if ch_rows
        else ""
    )

    audio_path = _rel(case.get("audio_path"), base)
    audio = (
        f"<div><h3>Recording</h3><audio controls src='{_esc(audio_path)}'></audio></div>"
        if audio_path
        else ""
    )

    figures = []
    for path, caption in (
        (_rel(case.get("screenshot"), base), "Full screenshot"),
        (_rel(case.get("crop"), base), "Value crop read by OCR"),
    ):
        if path:
            figures.append(
                f"<figure><img src='{_esc(path)}' alt='{_esc(caption)}' loading='lazy'>"
                f"<figcaption>{_esc(caption)}</figcaption></figure>"
            )
    shots = (
        f"<div><h3>Screen</h3><div class='shots'>{''.join(figures)}</div></div>"
        if figures
        else ""
    )

    events = case.get("events") or []
    ev_rows = "".join(
        f"<tr><td class='mono'>{_esc(e.get('event'))}</td>"
        f"<td class='mono'>+{_esc(round(e.get('at', 0) - events[0].get('at', 0), 3))}s</td></tr>"
        for e in events
    )
    timeline = (
        "<div><h3>Timeline</h3><div class='scroll'><table>"
        f"<tr><th>Event</th><th>Offset</th></tr>{ev_rows}</table></div></div>"
        if ev_rows
        else ""
    )

    return f"""<details class="evidence"><summary>Evidence</summary>
<div class="evidence-body">
<dl class="kv">{kv}</dl>
{ch_block}{audio}{shots}{timeline}
</div></details>"""


def _case_block(case: dict, base: Path, index: int = 0) -> str:
    status = case.get("status", "ERROR")
    glyph = STATUS_GLYPH.get(status, "?")
    side = _side(case.get("field"))
    ear = (
        f"<span class='ear {side}' title='{'left' if side == 'L' else 'right'} side'>{side}</span>"
        if side
        else "<span class='ear none' aria-hidden='true'></span>"
    )

    channels = case.get("channels") or {}
    shown_by = " + ".join(channels) or "screen"
    backend = str(case.get("backend") or "")
    model = str(case.get("model") or "")
    heard_by = (
        model
        if backend and model.startswith(backend)
        else " \u00b7 ".join(part for part in (backend, model) if part)
    )

    spoken = case.get("spoken_value")
    visual = case.get("visual_value")
    spoken_class = "val" if spoken not in (None, "") else "val absent"
    visual_class = "val" if visual not in (None, "") else "val absent"

    injected = case.get("injected_defect")
    warn = ""
    if injected and injected != "none":
        warn = (
            f"<div class='warn'><strong>Injected fixture defect: "
            f"<code>{_esc(injected)}</code>.</strong> A deliberate label fault in the AidSim "
            "test app, not a defect in Android, in TalkBack, or in any shipping product.</div>"
        )

    transcript = case.get("transcript")
    quote = (
        f"<blockquote class='quote'><q>{_esc(transcript)}</q></blockquote>"
        if transcript
        else "<blockquote class='quote'><span class='none'>Nothing intelligible was "
        "recovered from the recording.</span></blockquote>"
    )

    return f"""
<article class="case {status}" style="animation-delay:{index * 55}ms">
  <div class="case-head">
    {ear}
    <span class="name mono">{_esc(case.get('field'))}</span>
    <span class="type">{_esc(case.get('field_type'))}</span>
    <span class="badge {status}">{glyph} {_esc(status)}</span>
  </div>
  <div class="confront">
    <div class="side heard">
      <span class="cap">Heard</span>
      <span class="{spoken_class}">{_display(spoken)}</span>
      <span class="src">{_esc(heard_by)}</span>
    </div>
    <div class="link">
      <span class="reason">{_esc(case.get('reason'))}</span>
    </div>
    <div class="side shown">
      <span class="cap">Shown</span>
      <span class="{visual_class}">{_display(visual)}</span>
      <span class="src">{_esc(shown_by)}</span>
    </div>
  </div>
  {quote}
  {warn}
  {_evidence(case, base)}
</article>"""


def render(run: dict, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = run.get("cases", [])

    counts = {s: 0 for s in STATUS_ORDER}
    for case in cases:
        status = case.get("status", "ERROR")
        counts[status] = counts.get(status, 0) + 1

    case_blocks = "".join(_case_block(c, out_dir, i) for i, c in enumerate(cases))

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TalkBack audio validation</title>
<link rel="icon" href="{FAVICON}">
<style>{CSS}</style></head><body><div class="wrap">

<header class="masthead">
  <p class="eyebrow">Screen reader against screen</p>
  <h1>TalkBack audio validation</h1>
  <p class="lede">Each field below was heard from the phone's speaker through the laptop
  microphone and read from the phone's screen by separate channels, then compared by
  deterministic Python. Nothing that transcribes the audio is ever shown the answer.</p>
  <dl class="stamp">{_stamp(run.get('environment', {}))}
    <div><dt>generated</dt><dd>{_esc(run.get('generated_at'))}</dd></div>
  </dl>
</header>

<section>
  <h2>Agreement across {len(cases)} field{'' if len(cases) == 1 else 's'}</h2>
  {_meter(counts, len(cases))}
  {_findings(cases)}
</section>

<section>
  <h2>Capture integrity</h2>
  {_control_strip(run.get('control'))}
</section>

{_rerun_panel(run)}

<section>
  <h2>Fields</h2>
  {case_blocks or "<p class='allclear'>No fields were captured in this run.</p>"}
</section>

<footer class="footnote"><p>Agreement states that these two observations matched on this
device, in this run. It is not a claim about TalkBack's general correctness, and a
disagreement locates a conflict rather than naming its cause.</p></footer>

</div><script>{RERUN_SCRIPT}</script></body></html>"""

    html_path = out_dir / "index.html"
    html_path.write_text(doc, encoding="utf-8")
    (out_dir / "result.json").write_text(json.dumps(run, indent=2, default=str), encoding="utf-8")
    return html_path


def new_run(environment: dict) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": environment,
        "cases": [],
        "control": None,
    }
