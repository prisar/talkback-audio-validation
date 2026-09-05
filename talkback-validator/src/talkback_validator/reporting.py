from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

STATUS_GLYPH = {"PASS": "●", "FAIL": "▲", "INCONCLUSIVE": "■", "ERROR": "✖"}

CSS = """
:root {
  --bg: #ffffff; --fg: #14141a; --muted: #5c5c6b; --line: #e2e2ea;
  --card: #f7f7fa; --pass: #1a7f45; --fail: #b3261e; --incon: #8a6d0b; --error: #6b3fa0;
  --accent: #4338ca;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f0f14; --fg: #ececf2; --muted: #a0a0b0; --line: #2a2a35;
    --card: #17171f; --pass: #4ade80; --fail: #f87171; --incon: #fbbf24; --error: #c4b5fd;
    --accent: #a5b4fc;
  }
}
:root[data-theme="dark"] {
  --bg: #0f0f14; --fg: #ececf2; --muted: #a0a0b0; --line: #2a2a35;
  --card: #17171f; --pass: #4ade80; --fail: #f87171; --incon: #fbbf24; --error: #c4b5fd;
  --accent: #a5b4fc;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 15px/1.55 ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 32px 20px 80px; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 36px 0 12px; }
.sub { color: var(--muted); margin: 0 0 24px; }
.band { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 14px 16px; display: flex; flex-wrap: wrap; gap: 18px; font-size: 13px; }
.band div span { color: var(--muted); display: block; font-size: 11px;
  text-transform: uppercase; letter-spacing: .04em; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px; margin: 18px 0; }
.tile { background: var(--card); border: 1px solid var(--line); border-left-width: 4px;
  border-radius: 10px; padding: 14px 16px; }
.tile .n { font-size: 28px; font-weight: 700; }
.tile .l { font-size: 12px; color: var(--muted); text-transform: uppercase;
  letter-spacing: .05em; }
.tile.PASS { border-left-color: var(--pass); } .tile.PASS .n { color: var(--pass); }
.tile.FAIL { border-left-color: var(--fail); } .tile.FAIL .n { color: var(--fail); }
.tile.INCONCLUSIVE { border-left-color: var(--incon); } .tile.INCONCLUSIVE .n { color: var(--incon); }
.tile.ERROR { border-left-color: var(--error); } .tile.ERROR .n { color: var(--error); }
.tile.COVER { border-left-color: var(--accent); } .tile.COVER .n { color: var(--accent); }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; min-width: 720px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line);
  vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 11.5px;
  text-transform: uppercase; letter-spacing: .04em; }
.badge { font-weight: 700; white-space: nowrap; }
.badge.PASS { color: var(--pass); } .badge.FAIL { color: var(--fail); }
.badge.INCONCLUSIVE { color: var(--incon); } .badge.ERROR { color: var(--error); }
code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; }
details.case { background: var(--card); border: 1px solid var(--line);
  border-radius: 10px; margin: 10px 0; padding: 12px 16px; }
details.case summary { cursor: pointer; font-weight: 600; }
.kv { display: grid; grid-template-columns: 190px 1fr; gap: 6px 14px;
  margin: 12px 0; font-size: 13.5px; }
.kv div:nth-child(odd) { color: var(--muted); }
.note { background: var(--card); border-left: 3px solid var(--accent);
  padding: 10px 14px; border-radius: 0 8px 8px 0; margin: 14px 0;
  font-size: 13.5px; color: var(--muted); }
img { max-width: 100%; border: 1px solid var(--line); border-radius: 8px; }
.shots { display: flex; gap: 14px; flex-wrap: wrap; }
.shots figure { margin: 0; max-width: 260px; }
.shots figcaption { font-size: 12px; color: var(--muted); margin-top: 4px; }
audio { width: 100%; margin: 8px 0; }
"""


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _rel(path, base: Path) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def _case_block(case: dict, base: Path) -> str:
    status = case.get("status", "ERROR")
    glyph = STATUS_GLYPH.get(status, "?")
    rows = [
        ("Scenario", case.get("scenario")),
        ("Field", f"{case.get('field')} ({case.get('field_type')})"),
        ("Reason", case.get("reason")),
        ("Detail", case.get("detail")),
        ("Spoken value", case.get("spoken_value")),
        ("Displayed value", case.get("visual_value")),
        ("Transcript", case.get("transcript")),
        ("Backend / model", f"{case.get('backend')} / {case.get('model')}"),
        ("Prompt version", case.get("prompt_version")),
        ("Driver", case.get("driver")),
    ]
    kv = "".join(f"<div>{_esc(k)}</div><div>{_esc(v)}</div>" for k, v in rows)

    channels = case.get("channels") or {}
    ch_rows = "".join(
        f"<tr><td class='mono'>{_esc(name)}</td><td class='mono'>{_esc(data.get('raw'))}</td>"
        f"<td class='mono'>{_esc(data.get('value'))}</td>"
        f"<td class='mono'>{_esc(data.get('error', ''))}</td></tr>"
        for name, data in channels.items()
    )
    ch_table = (
        "<div class='scroll'><table><tr><th>Channel</th><th>Raw</th><th>Parsed</th>"
        f"<th>Error</th></tr>{ch_rows}</table></div>"
        if ch_rows
        else ""
    )

    audio_path = _rel(case.get("audio_path"), base)
    audio = f"<audio controls src='{_esc(audio_path)}'></audio>" if audio_path else ""

    shots = ""
    shot = _rel(case.get("screenshot"), base)
    crop = _rel(case.get("crop"), base)
    if shot or crop:
        parts = []
        if shot:
            parts.append(
                f"<figure><img src='{_esc(shot)}' alt='screenshot'>"
                "<figcaption>Full screenshot</figcaption></figure>"
            )
        if crop:
            parts.append(
                f"<figure><img src='{_esc(crop)}' alt='crop'>"
                "<figcaption>Value crop</figcaption></figure>"
            )
        shots = f"<div class='shots'>{''.join(parts)}</div>"

    a11y = case.get("accessibility") or {}
    a11y_html = ""
    if a11y:
        a11y_html = (
            "<div class='kv'>"
            f"<div>Accessibility before</div><div class='mono'>{_esc(a11y.get('before'))}</div>"
            f"<div>Accessibility after</div><div class='mono'>{_esc(a11y.get('after'))}</div>"
            "</div>"
        )

    events = case.get("events") or []
    ev_rows = "".join(
        f"<tr><td class='mono'>{_esc(e.get('event'))}</td>"
        f"<td class='mono'>{_esc(round(e.get('at', 0) - events[0].get('at', 0), 3))}s</td></tr>"
        for e in events
    )
    timeline = (
        f"<h3 style='font-size:14px'>Timeline</h3><div class='scroll'><table>"
        f"<tr><th>Event</th><th>Offset</th></tr>{ev_rows}</table></div>"
        if ev_rows
        else ""
    )

    injected = case.get("injected_defect")
    banner = ""
    if injected and injected != "none":
        banner = (
            f"<div class='note'><strong>Injected fixture defect: "
            f"<code>{_esc(injected)}</code>.</strong> This is a deliberate label fault in the "
            "AidSim test fixture. It is not a defect in Android, in TalkBack, or in any "
            "shipping product.</div>"
        )

    return f"""
<details class="case">
  <summary><span class="badge {status}">{glyph} {status}</span> &nbsp; {_esc(case.get('id'))}
    &mdash; {_esc(case.get('title'))}</summary>
  {banner}
  <div class="kv">{kv}</div>
  {a11y_html}
  <h3 style="font-size:14px">Visual channels</h3>
  {ch_table}
  {audio}
  {shots}
  {timeline}
</details>"""


def render(run: dict, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = run.get("cases", [])

    counts = {s: 0 for s in ("PASS", "FAIL", "INCONCLUSIVE", "ERROR")}
    for case in cases:
        counts[case.get("status", "ERROR")] = counts.get(case.get("status", "ERROR"), 0) + 1
    decided = counts["PASS"] + counts["FAIL"]
    coverage = f"{decided}/{len(cases)}" if cases else "0/0"

    tiles = "".join(
        f"<div class='tile {s}'><div class='n'>{counts[s]}</div>"
        f"<div class='l'>{STATUS_GLYPH[s]} {s}</div></div>"
        for s in ("PASS", "FAIL", "INCONCLUSIVE", "ERROR")
    )
    tiles += (
        f"<div class='tile COVER'><div class='n'>{coverage}</div>"
        "<div class='l'>Decision coverage</div></div>"
    )

    env = run.get("environment", {})
    band = "".join(
        f"<div><span>{_esc(k)}</span>{_esc(v)}</div>"
        for k, v in env.items()
    )

    rows = "".join(
        f"<tr><td class='mono'>{_esc(c.get('id'))}</td>"
        f"<td>{_esc(c.get('scenario'))}</td>"
        f"<td>{_esc(c.get('field'))}</td>"
        f"<td><span class='badge {c.get('status')}'>{STATUS_GLYPH.get(c.get('status'), '?')} "
        f"{_esc(c.get('status'))}</span></td>"
        f"<td class='mono'>{_esc(c.get('reason'))}</td>"
        f"<td class='mono'>{_esc(c.get('spoken_value'))}</td>"
        f"<td class='mono'>{_esc(c.get('visual_value'))}</td></tr>"
        for c in cases
    )

    control = run.get("control")
    if control is None:
        control_html = (
            "<div class='note'><strong>No negative control in this run.</strong> "
            "Without a TalkBack-disabled capture, a silent result cannot be distinguished "
            "from a recording failure.</div>"
        )
    else:
        ok = control.get("silent", False)
        control_html = (
            f"<div class='note'><strong>Negative control: "
            f"{'silent as expected' if ok else 'CAPTURED SPEECH'}.</strong> "
            f"Peak level {_esc(round(control.get('peak_level', 0), 4))} over "
            f"{_esc(round(control.get('duration_s', 0), 2))}s with TalkBack disabled. "
            + (
                "This is what separates recording TalkBack from recording something."
                if ok
                else "The run is not trustworthy."
            )
            + "</div>"
        )

    case_blocks = "".join(_case_block(c, out_dir) for c in cases)

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TalkBack Audio Validation</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>TalkBack audio validation</h1>
<p class="sub">Spoken value extracted from audio only, compared against the displayed
value by deterministic Python. Generated {_esc(run.get('generated_at'))}.</p>
<div class="band">{band}</div>
<div class="tiles">{tiles}</div>
{control_html}
<h2>Cases</h2>
<div class="scroll"><table>
<tr><th>ID</th><th>Scenario</th><th>Field</th><th>Status</th><th>Reason</th>
<th>Spoken</th><th>Displayed</th></tr>
{rows}
</table></div>
<h2>Evidence</h2>
{case_blocks}
<div class="note">A green run states that these observations agreed. It is not a
statement about TalkBack's general correctness, and a mismatch identifies disagreement
in this observation rather than naming its root cause.</div>
</div></body></html>"""

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
