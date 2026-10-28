#!/usr/bin/env python3
"""Static + raster checks for the generated cards.

Not a screenshot diff -- it asserts the things that actually break on GitHub:
declared text fits its column, every glyph exists, the raster is opaque, and the
palette stayed inside the RoOt-Se set (no pink, no magenta).

    python3 verify.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "_check"
sys.path.insert(0, str(HERE))

import build  # noqa: E402  (module-level font table only)

ALLOWED_FAMILIES = ("#0F0F0F", "#0B0A0A", "#141111", "#171414", "#121010", "#100E0E",
                    "#0C0B0B", "#0A0808", "#C62828", "#5C1212", "#E53935", "#C9A227",
                    "#7A6420", "#EDE6D6", "#B3AC9E", "#7A736A", "#66BB6A", "#2A2222",
                    "#1A1515", "#221C1C", "#241E1E", "#332B2B", "#3A3232", "#3D3434",
                    "#2A0E0E", "#4A4038", "#3A3330", "#241A1A", "#3A2E2E", "#2C2222",
                    "#ffffff")

fails: list[str] = []
notes: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        fails.append(msg)


def main() -> int:
    mono = {k: build.Face(v) for k, v in build.FONTS.items()}

    # ---- 1. text fits its column (measured with the real advance widths) ----
    name_w = mono["mono-bd"].width("ROOT-SECURTY", 40, ls=4.0)
    check(126 + name_w < 636 - 20, f"banner name overruns panel: ends at {126 + name_w:.0f}")
    notes.append(f"banner name width {name_w:.0f}px  (budget {636 - 20 - 126}px)")

    ttl = mono["mono-sb"].width("LOCK-SCREEN ENGINEER", 11, ls=3.4)
    check(128 + ttl < 600, f"tagline overruns: {128 + ttl:.0f}")
    notes.append(f"tagline width {ttl:.0f}px")

    sub = mono["sans"].width("Shells, plugins and lock skins for the Ryoku desktop.", 13.5)
    check(128 + sub < 620, f"subtitle overruns panel: {128 + sub:.0f}")
    notes.append(f"subtitle width {sub:.0f}px")

    for label, size, ls in [("ADDRESS", 8.5, 1.8), ("DATA", 8.5, 1.8),
                            ("LED", 8.5, 1.8), ("SR", 8.5, 1.8)]:
        w = mono["mono"].width(label, size, ls=ls)
        check(652 + w < 817, f"panel label {label} collides with the readout column")

    # every readable line in the rail must fit its 452px column after fitting
    import json
    repos = json.loads((HERE / "repos.json").read_text())
    for r in repos:
        lines = build.wrap(mono["sans"], r["desc"], 11.5, 470, max_lines=2)
        for ln in lines:
            w = mono["sans"].width(ln, 11.5)
            check(w <= 470.5, f"rail desc line overflows for {r['name']}: {w:.1f}px")
        notes.append(f"rail {r['slot']} desc {len(lines)} line(s), widest "
                     f"{max(mono['sans'].width(l, 11.5) for l in lines):.0f}/470px  {lines[-1][-22:]!r}")
        nw = mono["mono-sb"].width(r["display"], 13.5, ls=1.5)
        check(96 + nw < 366 - 12, f"rail name collides with description: {r['display']}")

    # ---- 2. no missing glyphs, no forbidden color strings ----
    for k, f in mono.items():
        check(not f.missing, f"font {k} missing glyphs: {sorted(f.missing)}")

    for svg in (HERE / "assets").glob("*.svg"):
        src = svg.read_text()
        low = src.lower()
        for bad in ("#ff00ff", "#e91e63", "magenta", "pink", "url(http", "@font-face"):
            check(bad not in low, f"{svg.name}: forbidden token {bad!r}")
        check("<text" not in src, f"{svg.name}: still contains <text> (font would not be embedded)")
        import re
        for hexv in set(re.findall(r"#[0-9a-fA-F]{6}", src)):
            check(hexv.upper() in {c.upper() for c in ALLOWED_FAMILIES},
                  f"{svg.name}: off-palette color {hexv}")
        notes.append(f"{svg.name} {svg.stat().st_size / 1024:.0f} KB")

    # ---- 3. raster: it must actually render, opaque, at the right size ----
    OUT.mkdir(exist_ok=True)
    for svg in sorted((HERE / "assets").glob("*.svg")):
        png = OUT / (svg.stem + ".png")
        r = subprocess.run(["resvg", "--zoom", "2", str(svg), str(png)],
                           capture_output=True, text=True)
        check(r.returncode == 0, f"resvg failed on {svg.name}: {r.stderr.strip()[:300]}")
        if r.returncode != 0:
            continue
        try:
            from PIL import Image
        except ImportError:
            notes.append("PIL absent - skipped raster probes")
            continue
        im = Image.open(png).convert("RGBA")
        w, h = im.size
        check(im.getextrema()[3] == (255, 255), f"{svg.name}: has transparent pixels")
        px = im.load()
        check(px[1, 1][3] == 255, f"{svg.name}: corner not opaque")
        notes.append(f"{png.name} {w}x{h}")

        if svg.stem == "banner":
            # monogram border must be red at (32, 90)*zoom
            p = px[64, 180][:3]
            check(p[0] > p[1] + 40 and p[0] > 100, f"monogram border not red: {p}")
            # a readout digit box interior stays near-black
            p = px[int(824 * 2), int(84 * 2)][:3]
            check(max(p) < 40, f"readout box not dark: {p}")
            # the name row must contain bone text pixels around y=100
            row = [px[x, 200][:3] for x in range(260, 800, 3)]
            check(any(c[0] > 200 and c[1] > 190 for c in row), "name row has no bone pixels")
        if svg.stem == "banner":
            def count(x0, x1, y0, y1, pred):
                return sum(1 for yy in range(int(y0 * 2), int(y1 * 2))
                           for xx in range(int(x0 * 2), int(x1 * 2)) if pred(px[xx, yy][:3]))
            red = lambda p: p[0] > 150 and p[1] < 80
            for label, box, pred, least in [
                ("address digits", (810, 965, 68, 105), red, 300),
                ("data digits", (810, 965, 102, 140), red, 250),
                ("led register", (810, 965, 140, 160), red, 400),
                ("switch register", (810, 965, 170, 200),
                 lambda p: p[0] > 140 and 110 < p[1] < 190 and p[2] < 90, 500),
                ("RUN lamp", (640, 760, 215, 235), lambda p: p[1] > 120 and p[0] < 120, 60),
                ("name glyphs", (126, 420, 80, 115), lambda p: min(p) > 170, 4000),
            ]:
                got = count(*box, pred)
                check(got >= least, f"banner: {label} looks empty ({got} px, want >= {least})")
                notes.append(f"banner {label}: {got} px")

        if svg.stem == "unibus":
            band = [px[x, yy][:3] for yy in range(96, 190, 2) for x in range(200, 700, 3)]
            check(sum(1 for c in band if sum(c) > 260) > 40, "rail first row looks empty")

    # ---- report ----
    for n in notes:
        print("  ·", n)
    if fails:
        print("\nFAIL")
        for f in fails:
            print("  x", f)
        return 1
    print(f"\nPASS  {len(notes)} checks, 0 failures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
