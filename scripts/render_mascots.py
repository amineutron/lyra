#!/usr/bin/env python3
"""Pre-render the animated SVG mascots into PNG sprite sheets for the capsule.

Source : installer/assets/mascots_svg/<name>.html  (CSS-only animated SVG, 6 states)
Output : <out>/<name>/<state>.png  (transparent sprite sheet, COLS frames per row)
         <out>/manifest.json       (frame size, fps, frame count and loop per sheet)

Needs Chrome or Chromium (headless). Usage:
    python3 scripts/render_mascots.py [--out DIR] [--only owl,cat] [--size 128] [--fps 15] [--jobs 4]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "installer" / "assets" / "mascots_svg"
STATES = ("sleep", "idle", "work", "busy", "ok", "err")
COLS = 8
MAX_LOOP_MS = 4000

PAGE_CSS = """
html,body{margin:0;background:transparent}
.mx .s{display:none}
.mx[data-state=sleep] .s-sleep,.mx[data-state=idle] .s-idle,.mx[data-state=work] .s-work,
.mx[data-state=busy] .s-busy,.mx[data-state=ok] .s-ok,.mx[data-state=err] .s-err{display:inline}
#grid{display:grid;grid-template-columns:repeat(%(cols)d,%(size)dpx);width:max-content}
.cell{width:%(size)dpx;height:%(size)dpx;overflow:hidden}
.cell svg{width:100%%;height:100%%;display:block}
"""

PROBE_JS = """
const out=document.getElementById('out');
const cell=document.querySelector('.cell');
const durs=[];let finite=0;
for(const a of cell.getAnimations({subtree:true})){
  const t=a.effect.getComputedTiming();
  if(t.iterations===Infinity) durs.push(Math.round(t.duration/50)*50||50);
}
out.textContent=JSON.stringify(durs);
"""

FRAMES_JS = """
const fps=%(fps)d, loop=%(loop)d;
for(const [i,cell] of [...document.querySelectorAll('.cell')].entries()){
  const t=(i*1000/fps)%%loop;
  for(const a of cell.getAnimations({subtree:true})){a.pause();a.currentTime=t;}
}
"""


def find_chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    sys.exit("Chrome or Chromium not found in PATH")


def lcm(a: int, b: int) -> int:
    return a * b // math.gcd(a, b)


def build_page(fragment: str, name: str, state: str, size: int, cells: int, script: str, probe: bool) -> str:
    style = re.search(r"<style>(.*?)</style>", fragment, re.S).group(1)
    svg = fragment[fragment.index("<svg"):fragment.rindex("</svg>") + 6]
    svg = svg.replace(f'class="mx m-{name}"', f'class="mx m-{name}" data-state="{state}"', 1)
    count = 1 if probe else cells
    body = "".join(f'<div class="cell">{svg}</div>' for _ in range(count))
    css = PAGE_CSS % {"cols": COLS, "size": size}
    return (
        f"<!doctype html><meta charset=utf-8><style>{css}\n{style}</style>"
        f'<div id="grid">{body}</div><pre id="out"></pre>'
        f"<script>window.addEventListener('load',()=>requestAnimationFrame(()=>{{{script}}}));</script>"
    )


def chrome_args(chrome: str, extra: list[str]) -> list[str]:
    return [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
            "--force-device-scale-factor=1", "--default-background-color=00000000", *extra]


def probe_loop_ms(chrome: str, fragment: str, name: str, state: str, size: int, tmp: Path) -> int:
    page = tmp / f"probe_{name}_{state}.html"
    page.write_text(build_page(fragment, name, state, size, 1, PROBE_JS, True))
    run = subprocess.run(chrome_args(chrome, ["--virtual-time-budget=1500", "--dump-dom", page.as_uri()]),
                         capture_output=True, text=True, timeout=60)
    match = re.search(r'<pre id="out">(.*?)</pre>', run.stdout, re.S)
    durations = json.loads(match.group(1)) if match and match.group(1).strip() else []
    loop = 1
    for d in durations:
        loop = lcm(loop, int(d))
        if loop > MAX_LOOP_MS:
            return MAX_LOOP_MS
    return max(loop, 1000) if durations else 2000


def render_state(chrome: str, name: str, state: str, args, tmp: Path) -> dict:
    fragment = (SRC / f"{name}.html").read_text()
    loop = probe_loop_ms(chrome, fragment, name, state, args.size, tmp)
    frames = max(2, round(loop * args.fps / 1000))
    rows = math.ceil(frames / COLS)
    script = FRAMES_JS % {"fps": args.fps, "loop": loop}
    page = tmp / f"sheet_{name}_{state}.html"
    page.write_text(build_page(fragment, name, state, args.size, frames, script, False))
    out_dir = args.out / name
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{state}.png"
    subprocess.run(chrome_args(chrome, [f"--window-size={COLS * args.size},{rows * args.size}",
                                        "--virtual-time-budget=800", f"--screenshot={png}", page.as_uri()]),
                   capture_output=True, timeout=120, check=True)
    return {"name": name, "state": state, "frames": frames, "loop_ms": loop, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path.home() / ".cache" / "lyra" / "mascots")
    parser.add_argument("--only", default="", help="comma-separated mascot names")
    parser.add_argument("--size", type=int, default=128)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    chrome = find_chrome()
    names = [n for n in args.only.split(",") if n] or sorted(p.stem for p in SRC.glob("*.html"))
    args.out.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"size": args.size, "fps": args.fps, "cols": COLS, "mascots": {}}
    with tempfile.TemporaryDirectory() as td, ThreadPoolExecutor(args.jobs) as pool:
        jobs = [(n, s) for n in names for s in STATES]
        for info in pool.map(lambda j: render_state(chrome, j[0], j[1], args, Path(td)), jobs):
            manifest["mascots"].setdefault(info["name"], {})[info["state"]] = {
                k: info[k] for k in ("frames", "loop_ms", "rows")}
            print(f"{info['name']:10} {info['state']:6} {info['frames']:3} frames  loop {info['loop_ms']} ms")
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
