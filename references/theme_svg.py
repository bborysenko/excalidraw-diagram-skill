"""Make an exported Excalidraw SVG follow light/dark mode with the Flexoki palette.

Flexoki (https://stephango.com/flexoki, MIT, by Steph Ango) is an "inky" palette
with a warm base scale and 8 accent hues, each defined for light and dark mode.

Draw the diagram with the Flexoki *light* values below, one per role, so the
.excalidraw source looks right in Excalidraw and Obsidian. Export it with
`render_excalidraw.py file.excalidraw -o file.raw.svg`, then run:

    uv run python theme_svg.py file.raw.svg file.svg

The script swaps each role color for a CSS variable with a light and a dark value.
Running it again on a themed SVG replaces the old style block.

Base roles (color in the source -> role):
    #100f0f text (black)          #6f6e69 muted text (base-600)
    #9f9d96 line (base-400)       #575653 arrow (base-700)
    #e6e4d9 node fill (base-100)  #b7b5ac node border (base-300)

Hues: the 600 value is the strong tone (strokes, dots, colored text), the 100
value the fill (bands, highlighted boxes; text on it stays black):
    red     #af3029 / #ffcabb     orange  #bc5215 / #fed3af
    yellow  #ad8301 / #f6e2a0     green   #66800b / #dde2b2
    cyan    #24837b / #bfe8d9     blue    #205ea6 / #c6dde8
    purple  #5e409d / #e2d9e9     magenta #a02f6f / #fccfda

Legacy placeholders (#010101..#080808) from the first version are still accepted.

The SVG gets an opaque background (paper / black) so it reads the same on any
surface; pass --no-bg to keep it transparent. Values are chosen for contrast on both the
Flexoki backgrounds and common app backgrounds (white, #1E1E1E): body and muted
text >= 4.5:1, lines and arrows >= 2.5:1.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Flexoki base scale
BASE = {
    "paper": "#FFFCF0", "50": "#F2F0E5", "100": "#E6E4D9", "150": "#DAD8CE",
    "200": "#CECDC3", "300": "#B7B5AC", "400": "#9F9D96", "500": "#878580",
    "600": "#6F6E69", "700": "#575653", "800": "#403E3C", "850": "#343331",
    "900": "#282726", "950": "#1C1B1A", "black": "#100F0F",
}
# Flexoki accents: 600 / 400 are the documented light / dark values; 100 / 900 are fills
ACCENTS = {
    "red":     {"100": "#FFCABB", "400": "#D14D41", "600": "#AF3029", "900": "#3E1715"},
    "orange":  {"100": "#FED3AF", "400": "#DA702C", "600": "#BC5215", "900": "#40200D"},
    "yellow":  {"100": "#F6E2A0", "400": "#D0A215", "600": "#AD8301", "900": "#3A2D04"},
    "green":   {"100": "#DDE2B2", "400": "#879A39", "600": "#66800B", "900": "#252D09"},
    "cyan":    {"100": "#BFE8D9", "400": "#3AA99F", "600": "#24837B", "900": "#122F2C"},
    "blue":    {"100": "#C6DDE8", "400": "#4385BE", "600": "#205EA6", "900": "#12253B"},
    "purple":  {"100": "#E2D9E9", "400": "#8B7EC8", "600": "#5E409D", "900": "#261C39"},
    "magenta": {"100": "#FCCFDA", "400": "#CE5D97", "600": "#A02F6F", "900": "#39172B"},
}
HUES = ["red", "orange", "yellow", "green", "cyan", "blue", "purple", "magenta"]

# Each role is drawn with its real Flexoki *light* value, so the .excalidraw source
# looks right when opened in Excalidraw or Obsidian. theme_svg.py maps that value to a
# CSS variable with a light and a dark value.
# role color in the source: (css variable, light value, dark value)
ROLES: dict[str, tuple[str, str, str]] = {}


def role(var: str, light: str, dark: str) -> None:
    ROLES[light.lower()] = (var, light, dark)


BG = ("--d-bg", BASE["paper"], BASE["black"])  # page background, not a drawing role
role("--d-text", BASE["black"], BASE["200"])
role("--d-muted", BASE["600"], BASE["400"])
role("--d-line", BASE["400"], BASE["600"])
role("--d-arrow", BASE["700"], BASE["300"])
role("--d-fill", BASE["100"], BASE["850"])
role("--d-border", BASE["300"], BASE["700"])
for hue in HUES:
    a = ACCENTS[hue]
    role(f"--d-{hue}", a["600"], a["400"])
    role(f"--d-{hue}-fill", a["100"], a["900"])

# Legacy placeholders from the first version (#010101..#080808)
LEGACY = {
    "#010101": BASE["black"], "#020202": BASE["600"], "#030303": BASE["400"],
    "#040404": BASE["700"], "#050505": BASE["100"], "#060606": BASE["300"],
    "#070707": ACCENTS["blue"]["600"], "#080808": ACCENTS["blue"]["100"],
}


def palette(mode: int) -> str:
    return "".join(f"{var}:{vals[mode]};" for var, *vals in [*ROLES.values(), BG])


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    svg = src.read_text(encoding="utf-8")
    # Normalize: lowercase hex in fill/stroke, legacy placeholders -> role colors
    def norm(m: re.Match) -> str:
        c = m.group(2).lower()
        return f'{m.group(1)}="{LEGACY.get(c, c).lower()}"'

    svg = re.sub(r'\b(fill|stroke)="(#[0-9a-fA-F]{6})"', norm, svg)
    found = set(re.findall(r'(?:fill|stroke)="(#[0-9a-f]{6})"', svg))
    unknown = found - set(ROLES)
    if unknown:
        print(f"warning: colors outside the Flexoki roles stay fixed: {sorted(unknown)}", file=sys.stderr)
    rules = [
        f'[fill="{c}"]{{fill:var({ROLES[c][0]})}} [stroke="{c}"]{{stroke:var({ROLES[c][0]})}}'
        for c in sorted(found & set(ROLES))
    ]
    style = (
        "<style>"
        f"svg{{{palette(0)}}}"
        f"@media (prefers-color-scheme: dark){{svg{{{palette(1)}}}}}"
        + " ".join(rules)
        + " text{font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif!important;font-weight:500}"
        # fontFamily 3 (code) stays monospace
        " text[font-family^='Cascadia']{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace!important;font-weight:400}"
        "</style>"
    )
    # Size the SVG at 1:1 with its viewBox (the export is at 2x), so it embeds at a natural size
    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if vb:
        svg = re.sub(r'(<svg[^>]*?)\swidth="[\d.]+"', rf'\1 width="{vb.group(1)}"', svg, count=1)
        svg = re.sub(r'(<svg[^>]*?)\sheight="[\d.]+"', rf'\1 height="{vb.group(2)}"', svg, count=1)
    # Drop the style block and background from an earlier theming run
    svg = re.sub(r"(<svg[^>]*>)<style>.*?</style>", r"\1", svg, count=1, flags=re.S)
    svg = re.sub(r'<rect id="d-bg"[^>]*/>', "", svg, count=1)
    # Opaque themed background, so the diagram stays readable wherever it is shown
    # (Obsidian's full-screen viewer, GitHub, image viewers). --no-bg keeps it transparent.
    bg = ""
    if vb and "--no-bg" not in sys.argv:
        bg = f'<rect id="d-bg" x="0" y="0" width="{vb.group(1)}" height="{vb.group(2)}" style="fill:var(--d-bg)"/>'
    svg = re.sub(r"(<svg[^>]*>)", lambda m: m.group(1) + style + bg, svg, count=1)
    dst.write_text(svg, encoding="utf-8")
    print(f"Themed SVG saved to {dst}")


if __name__ == "__main__":
    main()
