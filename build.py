#!/usr/bin/env python3
"""Render the profile SVG cards: a PDP-11 front panel banner and a UNIBUS rail.

Every glyph is converted to a path (fontTools), so the SVGs render identically
on github.com and in any viewer -- no web font, no fallback.

    python3 build.py            # writes assets/banner.svg + assets/unibus.svg

Colors come from the RoOt-Se mk2 scheme. Red = state only, gold = silkscreen only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"

# ---------------------------------------------------------------- palette ----
BG        = "#0F0F0F"
BG_DEEP   = "#0B0A0A"
PANEL     = "#141111"
PANEL_HI  = "#171414"
SILK      = "#2A2222"   # hairlines / bezel
RED       = "#C62828"
RED_DIM   = "#5C1212"
RED_HI    = "#E53935"
GOLD      = "#C9A227"
GOLD_DIM  = "#7A6420"
BONE      = "#EDE6D6"
MUTE      = "#B3AC9E"
OUTLINE   = "#7A736A"
GREEN     = "#66BB6A"

FONTS = {
    "mono":    "/usr/share/fonts/TTF/IosevkaNerdFontMono-Regular.ttf",
    "mono-md": "/usr/share/fonts/TTF/IosevkaNerdFontMono-Medium.ttf",
    "mono-sb": "/usr/share/fonts/TTF/IosevkaNerdFontMono-SemiBold.ttf",
    "mono-bd": "/usr/share/fonts/TTF/IosevkaNerdFontMono-Bold.ttf",
    "sans":    "/usr/share/fonts/inter/InterVariable.ttf",
}


# ------------------------------------------------------------------ fonts ----
class Face:
    """A loaded font whose every glyph can be emitted as path data."""

    def __init__(self, path: str):
        self.tt = TTFont(path, fontNumber=0)
        self.upem = self.tt["head"].unitsPerEm
        self.glyphset = self.tt.getGlyphSet()
        self.cmap = self.tt.getBestCmap()
        self.hmtx = self.tt["hmtx"]
        self.missing = set()

    def gname(self, ch: str) -> str | None:
        n = self.cmap.get(ord(ch))
        if n is None:
            self.missing.add(ch)
        return n

    def advance(self, ch: str) -> float:
        n = self.gname(ch)
        return self.hmtx[n][0] if n else 0.0

    def width(self, text: str, size: float, ls: float = 0.0) -> float:
        """Rendered width in px, letter-spacing included."""
        if not text:
            return 0.0
        u = sum(self.advance(c) for c in text) + ls * self.upem / size * (len(text) - 1)
        return u * size / self.upem

    def path(self, text: str, size: float, x: float, y: float,
             ls: float = 0.0, anchor: str = "start") -> str:
        """One <path d="..."> worth of outlines, baseline at (x, y)."""
        if not text:
            return ""
        w = self.width(text, size, ls)
        if anchor == "middle":
            x -= w / 2
        elif anchor == "end":
            x -= w
        s = size / self.upem
        parts: list[str] = []
        pen_d: list[str] = []
        cursor = 0.0
        for ch in text:
            n = self.gname(ch)
            if n is None:
                cursor += self.upem * 0.5
                continue
            spen = SVGPathPen(self.glyphset, ntos=lambda v: f"{v:.2f}")
            tpen = TransformPen(spen, (s, 0, 0, -s, x + cursor * s, y))
            self.glyphset[n].draw(tpen)
            d = spen.getCommands()
            if d:
                pen_d.append(d)
            cursor += self.hmtx[n][0] + (ls / s if ls else 0.0)
        if pen_d:
            parts.append("".join(pen_d))
        return "".join(parts)


def T(face: Face, text: str, size: float, x: float, y: float, fill: str,
      ls: float = 0.0, anchor: str = "start", opacity: float | None = None,
      extra: str = "") -> str:
    d = face.path(text, size, x, y, ls=ls, anchor=anchor)
    if not d:
        return ""
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return f'<path d="{d}" fill="{fill}"{op}{extra}/>'


# ------------------------------------------------------------------ utils ----
def rect(x, y, w, h, fill, extra="") -> str:
    return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" fill="{fill}" {extra}/>'


def line(x1, y1, x2, y2, stroke, w=1, extra="") -> str:
    return (f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" '
            f'stroke="{stroke}" stroke-width="{w:g}" {extra}/>')


def edge_connector(x, y, w, h, pitch=11, tooth=6, color=GOLD, opacity=0.55) -> str:
    out, cx = [], 0
    while cx + tooth <= w:
        out.append(rect(x + cx, y, tooth, h, color, 'opacity="%s"' % opacity))
        cx += pitch
    return "".join(out)


def led(x, y, size, color, on=True, opacity=1.0) -> str:
    if on:
        return (f'<rect x="{x:g}" y="{y:g}" width="{size:g}" height="{size:g}" fill="{color}" '
                f'opacity="{opacity}" filter="url(#glow)"/>')
    return rect(x, y, size, size, "#241A1A", f'stroke="#3A2E2E" stroke-width="0.6" opacity="{opacity}"')


# ----------------------------------------------------------------- banner ----
def banner(mono: dict[str, Face]) -> str:
    W, H = 1000, 300
    f_reg, f_sb, f_bd = mono["mono"], mono["mono-sb"], mono["mono-bd"]
    sans = mono["sans"]

    o: list[str] = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Root-Securty - lock screens, shells and plugins for the Ryoku desktop">')
    o.append("<title>Root-Securty / PDP-11 front panel</title>")
    o.append(
        "<defs>"
        f'<linearGradient id="glass" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{PANEL_HI}"/><stop offset="1" stop-color="{BG}"/></linearGradient>'
        f'<linearGradient id="die" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#2A0E0E"/><stop offset="1" stop-color="{BG}"/></linearGradient>'
        '<filter id="glow" x="-80%" y="-80%" width="260%" height="260%">'
        '<feGaussianBlur stdDeviation="2.4" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        f'<pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">'
        f'<path d="M20 0H0V20" fill="none" stroke="#ffffff" stroke-opacity="0.022" stroke-width="1"/></pattern>'
        f'<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">'
        '<rect width="4" height="1" fill="#ffffff" fill-opacity="0.016"/></pattern>'
        "</defs>"
    )

    # body : bezel, glass, texture
    o.append(rect(0, 0, W, H, BG))
    o.append(rect(0, 0, W, H, "url(#glass)"))
    o.append(rect(0, 0, W, H, "url(#grid)"))
    o.append(rect(0, 0, W, H, "url(#scan)"))
    o.append(rect(0.5, 0.5, W - 1, H - 1, "none", f'stroke="{SILK}" stroke-width="1"'))
    o.append(rect(0, 0, W, 1, GOLD, 'opacity="0.18"'))

    # ---- top bezel strip
    o.append(rect(0, 0, W, 30, "#121010"))
    o.append(line(0, 30, W, 30, SILK))
    o.append(T(f_bd, "M7264", 10, 32, 19.5, GOLD, ls=2.4))
    o.append(T(f_reg, "KDJ11-A", 10, 92, 19.5, OUTLINE, ls=2.0))
    o.append(T(f_reg, "UNIBUS", 10, 160, 19.5, OUTLINE, ls=2.0))
    o.append(T(f_reg, "PDP-11/70 FRONT PANEL", 9.5, 236, 19.5, RED_DIM, ls=2.4))
    o.append(T(f_bd, "001 000", 11, W - 32, 19.5, RED, ls=2.0, anchor="end"))

    # ---- monogram
    mx, my, ms = 32, 56, 70
    o.append(rect(mx, my, ms, ms, "url(#die)", f'stroke="{RED}" stroke-width="2"'))
    o.append(rect(mx + 5.5, my + 5.5, ms - 11, ms - 11, "none",
                  f'stroke="{RED_DIM}" stroke-width="1"'))
    o.append(T(f_bd, "RS", 26, mx + ms / 2, my + ms / 2 + 9.5, RED, ls=1.0, anchor="middle"))
    o.append(rect(mx + ms + 6, my, 1, ms, RED_DIM, 'opacity="0.5"'))

    # ---- identity block
    tx = mx + ms + 24
    o.append(T(f_bd, "ROOT-SECURTY", 40, tx, 112, BONE, ls=4.0))
    o.append(T(f_sb, "LOCK-SCREEN ENGINEER", 11, tx + 2, 138, RED, ls=3.4))
    o.append(T(f_reg, "QML / RUST / HYPRLAND", 10, tx + 2, 158, GOLD_DIM, ls=2.6))
    o.append(T(sans, "Shells, plugins and lock skins for the Ryoku desktop.",
               13.5, tx + 2, 187, MUTE))

    # ---- stat chips
    chips = [("04", "REPOS"), ("02", "LANGUAGES"), ("01", "FORK"), ("2019", "SINCE")]
    cx = tx
    for i, (val, label) in enumerate(chips):
        w = 96
        y = 206
        o.append(rect(cx, y, w, 40, "#121010", f'stroke="{SILK}" stroke-width="1"'))
        o.append(rect(cx, y, 2, 40, GOLD, 'opacity="0.7"'))
        o.append(T(f_bd, val, 15, cx + 12, y + 19, BONE, ls=1.2))
        o.append(T(f_reg, label, 8, cx + 12, y + 31, OUTLINE, ls=1.6))
        cx += w + 8

    # ---- front panel (right)
    px, py, pw, ph = 636, 48, 332, 200
    o.append(rect(px, py, pw, ph, "#100E0E", f'stroke="#332B2B" stroke-width="1"'))
    o.append(rect(px, py, pw, ph, "url(#scan)"))
    o.append(rect(px + 0.5, py + 0.5, pw - 1, 1, "#3D3434"))
    o.append(rect(px - 1, py + 8, 2, ph - 16, RED, 'opacity="0.55"'))

    # ADDRESS / DATA displays
    right = px + pw - 16
    for label, value, yy in [("ADDRESS", "001000", 84), ("DATA", "042176", 118)]:
        o.append(T(f_reg, label, 8.5, px + 14, yy - 8, OUTLINE, ls=1.8))
        dx = right - (len(value) * 23 - 3)
        for ch in value:
            o.append(rect(dx, yy - 15, 20, 19, "#0A0808", f'stroke="#2C2222" stroke-width="1"'))
            o.append(T(f_bd, ch, 12, dx + 10, yy - 1.5, RED_HI, anchor="middle", opacity=0.92))
            dx += 23
    # LED register
    o.append(T(f_reg, "LED", 8.5, px + 14, 158, OUTLINE, ls=1.8))
    lx = right - (12 * 11 - 4)
    pattern = [1, 1, 1, 0, 1, 1, 0, 1, 1, 0, 0, 1]
    for i, on in enumerate(pattern):
        o.append(led(lx, 150, 7, RED_HI if i % 4 else GREEN, on=bool(on)))
        lx += 11
    # switch register
    o.append(T(f_reg, "SR", 8.5, px + 14, 192, OUTLINE, ls=1.8))
    sx = right - (8 * 16 - 3)
    sw = [1, 1, 0, 1, 0, 1, 1, 0]
    for i, up in enumerate(sw):
        o.append(rect(sx, 178, 13, 18, "url(#glass)", f'stroke="#3A3232" stroke-width="1"'))
        o.append(rect(sx + 4, 180 if up else 187, 5, 7, GOLD, 'opacity="0.85"'))
        sx += 16
    # status line
    o.append(line(px + 14, 214, px + pw - 14, 214, SILK))
    o.append(rect(px + 14, 222, 6, 6, GREEN, 'filter="url(#glow)"'))
    o.append(T(f_sb, "RUN", 9, px + 26, 229, GREEN, ls=2.0))
    o.append(T(f_reg, "HALT", 9, px + 66, 229, "#4A4038", ls=2.0))
    o.append(T(f_reg, "DC OK", 8.5, px + pw - 14, 229, GOLD_DIM, ls=1.6, anchor="end"))

    # ---- bottom edge connector
    o.append(rect(0, 262, W, 38, BG_DEEP))
    o.append(line(0, 262, W, 262, "#241E1E"))
    o.append(edge_connector(0, 274, W, 11, pitch=12, tooth=7))
    o.append(T(f_reg, "SERIAL  RS-2026  ·  ALL CARDS IN BACKPLANE", 8, 32, 296, "#3A3330", ls=2.2))
    o.append(edge_connector(0, 296, W, 3, pitch=12, tooth=7, opacity=0.18))
    o.append("</svg>")
    return "".join(o)


# ------------------------------------------------------------------ rail ----
def fit(face: Face, text: str, size: float, width: float) -> str:
    """Truncate to the widest string that fits, with an ellipsis."""
    if face.width(text, size) <= width:
        return text
    ell = "."
    for cand in ("\u2026", "..."):
        try:
            face.path(cand, size, 0, 0)
            ell = cand
            break
        except Exception:  # noqa: BLE001
            continue
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if face.width(text[:mid].rstrip() + ell, size) <= width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip(" ,;:-\u2013") + ell


def wrap(face: Face, text: str, size: float, width: float, max_lines: int = 2) -> list[str]:
    """Greedy word wrap; the last line is truncated with an ellipsis if it must be."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for i, w in enumerate(words):
        trial = (cur + " " + w).strip()
        if face.width(trial, size) <= width:
            cur = trial
            continue
        lines.append(cur)
        cur = w
        if len(lines) == max_lines - 1:
            lines.append(fit(face, " ".join(words[i:]), size, width))
            return [l for l in lines if l]
    if cur:
        lines.append(cur)
    return [l for l in lines if l]


def rail(mono: dict[str, Face], repos: list[dict]) -> str:
    W = 1000
    HDR, ROW = 44, 64
    H = HDR + ROW * len(repos) + 34
    f_reg, f_sb, f_bd, sans = mono["mono"], mono["mono-sb"], mono["mono-bd"], mono["sans"]

    o: list[str] = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" role="img" aria-label="Repository index as a UNIBUS card rail">')
    o.append("<title>UNIBUS - repository index</title>")
    o.append(
        "<defs>"
        '<filter id="glow" x="-80%" y="-80%" width="260%" height="260%">'
        '<feGaussianBlur stdDeviation="2"/><feMerge><feMergeNode/>'
        '<feMergeNode in="SourceGraphic"/></feMerge></filter>'
        f'<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">'
        '<rect width="4" height="1" fill="#ffffff" fill-opacity="0.014"/></pattern>'
        "</defs>"
    )
    o.append(rect(0, 0, W, H, BG))
    o.append(rect(0, 0, W, H, "url(#scan)"))
    o.append(rect(0.5, 0.5, W - 1, H - 1, "none", f'stroke="{SILK}" stroke-width="1"'))

    # header
    o.append(rect(0, 0, W, HDR, "#0C0B0B"))
    o.append(line(0, HDR, W, HDR, SILK))
    o.append(rect(0, 0, 3, HDR, RED))
    o.append(T(f_bd, "UNIBUS", 11, 32, 27, GOLD, ls=2.8))
    o.append(T(f_reg, "REPOSITORY INDEX", 9, 130, 27, OUTLINE, ls=2.2))
    o.append(T(f_reg, "SLOT \u00b7 MODULE \u00b7 LANGUAGE \u00b7 STATE", 8.5,
               W - 32, 27, "#4A4038", ls=1.8, anchor="end"))

    for i, r in enumerate(repos):
        y = HDR + i * ROW
        o.append(rect(0, y, W, ROW, PANEL if i % 2 == 0 else BG))
        o.append(line(0, y + ROW, W, y + ROW, "#221C1C"))
        o.append(line(32, y, W - 32, y, "#1A1515"))

        # slot
        o.append(T(f_bd, r["slot"], 11, 32, y + 34, RED, ls=1.6))
        o.append(line(78, y + 12, 78, y + ROW - 12, "#2A2222"))

        # name + tags
        o.append(T(f_sb, r["display"], 13.5, 96, y + 30, BONE, ls=1.5))
        tag = f'{r["lang"]}  /  {r["kind"]}'
        o.append(T(f_reg, tag, 8.5, 96, y + 47, GOLD_DIM, ls=1.6))

        # description : two lines when it needs them, never clipped mid-word
        lines = wrap(sans, r["desc"], 11.5, 470, max_lines=2)
        base = y + (28 if len(lines) > 1 else 37)
        for i, ln in enumerate(lines):
            o.append(T(sans, ln, 11.5, 366, base + i * 16, MUTE))

        # state
        o.append(rect(898, y + 26, 6, 6, GREEN, 'filter="url(#glow)"'))
        o.append(T(f_sb, "RUN", 8.5, 910, y + 32.5, GREEN, ls=1.8))
        o.append(T(f_reg, "PUBLIC", 8.5, W - 32, y + 32.5, "#4A4038", ls=1.6, anchor="end"))

    # bus bar
    by = HDR + ROW * len(repos)
    o.append(rect(0, by, W, 22, BG_DEEP))
    o.append(line(0, by, W, by, "#241E1E"))
    o.append(edge_connector(0, by + 6, W, 9, pitch=12, tooth=7, opacity=0.42))
    o.append(T(f_reg, "BACKPLANE  22-BIT  \u00b7  ALL MODULES PRESENT", 8, 32, by + 15,
               "#3A3330", ls=2.0))
    o.append(T(f_reg, "%02d CARDS" % len(repos), 8, W - 32, by + 15, GOLD_DIM,
               ls=1.8, anchor="end"))
    o.append("</svg>")
    return "".join(o)


# ------------------------------------------------------------------ main ----
def main() -> int:
    mono = {k: Face(v) for k, v in FONTS.items()}
    repos = json.loads((HERE / "repos.json").read_text())

    raw_dir = HERE / "_build"
    ASSETS.mkdir(exist_ok=True)
    raw_dir.mkdir(exist_ok=True)
    jobs = {"banner": banner(mono), "unibus": rail(mono, repos)}
    for name, svg in jobs.items():
        (raw_dir / f"{name}.svg").write_text(svg)
        shutil.copyfile(raw_dir / f"{name}.svg", ASSETS / f"{name}.svg")
    # ship a slimmed copy when scour is around (paths only, nothing external)
    scour = shutil.which("scour") or str(Path(sys.executable).with_name("scour"))
    if Path(scour).exists():
        for name in jobs:
            # -q only: any extra flag (e.g. --set-precision) changes coordinates and
            # the raster stops being pixel-identical to the source. Verified, don't.
            r = subprocess.run([scour, "-i", str(raw_dir / f"{name}.svg"),
                                "-o", str(ASSETS / f"{name}.svg"), "-q"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"WARN scour failed on {name}: {r.stderr.strip()[:200]}", file=sys.stderr)
                shutil.copyfile(raw_dir / f"{name}.svg", ASSETS / f"{name}.svg")

    missing = {k: sorted(f.missing) for k, f in mono.items() if f.missing}
    for name, chars in missing.items():
        print(f"WARN missing glyphs in {name}: {chars}", file=sys.stderr)
    for p in sorted(ASSETS.glob("*.svg")):
        print(f"{p.relative_to(HERE)}  {p.stat().st_size/1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())