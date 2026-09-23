"""Make an exported Excalidraw SVG follow light/dark mode, in the beautiful-mermaid style.

Draw the diagram with these placeholder colors (one per role), export it with
`render_excalidraw.py file.excalidraw -o file.raw.svg`, then run:

    uv run python theme_svg.py file.raw.svg file.svg

Roles (placeholder -> meaning), mixed from the zinc theme as beautiful-mermaid does:
    #010101 text      #020202 muted text   #030303 line    #040404 arrow
    #050505 node fill #060606 node border  #070707 accent  #080808 faint accent
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

THEMES = {
    "light": {"bg": "#FFFFFF", "fg": "#27272A"},  # beautiful-mermaid zinc-light
    "dark": {"bg": "#18181B", "fg": "#FAFAFA"},  # beautiful-mermaid zinc-dark
}
# placeholder: (css variable, % of fg mixed into bg) — same formulas as beautiful-mermaid
ROLES = {
    "#010101": ("--d-text", 100),
    "#020202": ("--d-muted", 60),
    "#030303": ("--d-line", 50),
    "#040404": ("--d-arrow", 85),
    "#050505": ("--d-fill", 3),
    "#060606": ("--d-border", 20),
    "#070707": ("--d-accent", 70),
    "#080808": ("--d-accent-faint", 25),
}


def mix(fg: str, bg: str, pct: int) -> str:
    f = [int(fg[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(fc * pct / 100 + bc * (100 - pct) / 100):02x}" for fc, bc in zip(f, b))


def palette(theme: str) -> str:
    t = THEMES[theme]
    return " ".join(f"{var}:{mix(t['fg'], t['bg'], pct)};" for var, pct in ROLES.values())


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    svg = src.read_text(encoding="utf-8")
    rules = []
    for ph, (var, _) in ROLES.items():
        rules.append(f'[fill="{ph}"]{{fill:var({var})}} [stroke="{ph}"]{{stroke:var({var})}}')
    style = (
        "<style>"
        f"svg{{{palette('light')}}}"
        f"@media (prefers-color-scheme: dark){{svg{{{palette('dark')}}}}}"
        + " ".join(rules)
        + " text{font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif!important;font-weight:500}"
        "</style>"
    )
    # Size the SVG at 1:1 with its viewBox (the export is at 2x), so it embeds at a natural size
    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if vb:
        svg = re.sub(r'(<svg[^>]*?)\swidth="[\d.]+"', rf'\1 width="{vb.group(1)}"', svg, count=1)
        svg = re.sub(r'(<svg[^>]*?)\sheight="[\d.]+"', rf'\1 height="{vb.group(2)}"', svg, count=1)
    # Inject the style right after the opening <svg ...> tag
    svg = re.sub(r"(<svg[^>]*>)", r"\1" + style, svg, count=1)
    dst.write_text(svg, encoding="utf-8")
    print(f"Themed SVG saved to {dst}")


if __name__ == "__main__":
    main()
