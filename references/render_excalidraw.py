"""Render Excalidraw JSON to PNG using Playwright + headless Chromium.

Usage:
    cd .claude/skills/excalidraw-diagram/references
    uv run python render_excalidraw.py <path-to-file.excalidraw> [--output path.png] [--scale 2] [--width 1920]

First-time setup:
    cd .claude/skills/excalidraw-diagram/references
    uv sync
    uv run playwright install chromium
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ESM_CACHE_DIR = Path(__file__).parent / ".esm-cache"


def _serve_esm_from_cache(route) -> None:
    """Answer a browser request to esm.sh from the disk cache, fetching it on a miss."""
    url = route.request.url
    key = hashlib.sha256(url.encode()).hexdigest()
    body_path = ESM_CACHE_DIR / key
    type_path = ESM_CACHE_DIR / f"{key}.type"
    if not body_path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (excalidraw-render)"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                content_type = resp.headers.get("Content-Type", "application/javascript")
        except urllib.error.HTTPError as e:
            # Pass the error through without caching it, so the browser sees a normal failed request.
            print(f"esm.sh {e.code}: {url}", file=sys.stderr)
            route.fulfill(status=e.code, body=e.read() or b"")
            return
        except Exception as e:  # network problem: fail this request instead of hanging the page
            print(f"esm.sh fetch failed ({e}): {url}", file=sys.stderr)
            route.abort()
            return
        ESM_CACHE_DIR.mkdir(exist_ok=True)
        body_path.write_bytes(body)
        type_path.write_text(content_type)
    route.fulfill(
        status=200,
        body=body_path.read_bytes(),
        headers={
            "Content-Type": type_path.read_text(),
            "Access-Control-Allow-Origin": "*",
        },
    )


def validate_excalidraw(data: dict) -> list[str]:
    """Validate Excalidraw JSON structure. Returns list of errors (empty = valid)."""
    errors: list[str] = []

    if data.get("type") != "excalidraw":
        errors.append(f"Expected type 'excalidraw', got '{data.get('type')}'")

    if "elements" not in data:
        errors.append("Missing 'elements' array")
    elif not isinstance(data["elements"], list):
        errors.append("'elements' must be an array")
    elif len(data["elements"]) == 0:
        errors.append("'elements' array is empty — nothing to render")

    return errors


def compute_bounding_box(elements: list[dict]) -> tuple[float, float, float, float]:
    """Compute bounding box (min_x, min_y, max_x, max_y) across all elements."""
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for el in elements:
        if el.get("isDeleted"):
            continue
        x = el.get("x", 0)
        y = el.get("y", 0)
        w = el.get("width", 0)
        h = el.get("height", 0)

        # For arrows/lines, points array defines the shape relative to x,y
        if el.get("type") in ("arrow", "line") and "points" in el:
            for px, py in el["points"]:
                min_x = min(min_x, x + px)
                min_y = min(min_y, y + py)
                max_x = max(max_x, x + px)
                max_y = max(max_y, y + py)
        else:
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + abs(w))
            max_y = max(max_y, y + abs(h))

    if min_x == float("inf"):
        return (0, 0, 800, 600)

    return (min_x, min_y, max_x, max_y)


def render(
    excalidraw_path: Path,
    output_path: Path | None = None,
    scale: int = 2,
    max_width: int = 1920,
) -> Path:
    """Render an .excalidraw file to PNG. Returns the output PNG path."""
    # Import playwright here so validation errors show before import errors
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed.", file=sys.stderr)
        print("Run: cd .claude/skills/excalidraw-diagram/references && uv sync && uv run playwright install chromium", file=sys.stderr)
        sys.exit(1)

    # Read and validate
    raw = excalidraw_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {excalidraw_path}: {e}", file=sys.stderr)
        sys.exit(1)

    errors = validate_excalidraw(data)
    if errors:
        print(f"ERROR: Invalid Excalidraw file:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # Compute viewport size from element bounding box
    elements = [e for e in data["elements"] if not e.get("isDeleted")]
    min_x, min_y, max_x, max_y = compute_bounding_box(elements)
    padding = 80
    diagram_w = max_x - min_x + padding * 2
    diagram_h = max_y - min_y + padding * 2

    # Cap viewport width, let height be natural
    vp_width = min(int(diagram_w), max_width)
    vp_height = max(int(diagram_h), 600)

    # Output path
    if output_path is None:
        output_path = excalidraw_path.with_suffix(".png")

    # Template path (same directory as this script)
    template_path = Path(__file__).parent / "render_template.html"
    if not template_path.exists():
        print(f"ERROR: Template not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    template_url = template_path.as_uri()

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as e:
            if "Executable doesn't exist" in str(e) or "browserType.launch" in str(e):
                print("ERROR: Chromium not installed for Playwright.", file=sys.stderr)
                print("Run: cd .claude/skills/excalidraw-diagram/references && uv run playwright install chromium", file=sys.stderr)
                sys.exit(1)
            raise

        page = browser.new_page(
            viewport={"width": vp_width, "height": vp_height},
            device_scale_factor=scale,
        )

        # Headless Chromium runs in its own sandbox and often can't reach esm.sh,
        # even when this Python process can. Fetch esm.sh requests here instead,
        # and cache them on disk so later renders work offline.
        page.route("https://esm.sh/**", _serve_esm_from_cache)

        # Load the template
        page.goto(template_url)

        # Wait for the ES module to load (imports from esm.sh)
        page.wait_for_function("window.__moduleReady === true", timeout=30000)

        # Inject the diagram data and render
        json_str = json.dumps(data)
        result = page.evaluate(f"window.renderDiagram({json_str})")

        if not result or not result.get("success"):
            error_msg = result.get("error", "Unknown render error") if result else "renderDiagram returned null"
            print(f"ERROR: Render failed: {error_msg}", file=sys.stderr)
            browser.close()
            sys.exit(1)

        # Wait for render completion signal
        page.wait_for_function("window.__renderComplete === true", timeout=15000)

        # Screenshot the SVG element
        svg_el = page.query_selector("#root svg")
        if svg_el is None:
            print("ERROR: No SVG element found after render.", file=sys.stderr)
            browser.close()
            sys.exit(1)

        if output_path.suffix.lower() == ".svg":
            # Vector output: keeps text crisp and lets CSS restyle colors afterwards.
            output_path.write_text(svg_el.evaluate("el => el.outerHTML"), encoding="utf-8")
        else:
            svg_el.screenshot(path=str(output_path))
        browser.close()

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Excalidraw JSON to PNG")
    parser.add_argument("input", type=Path, help="Path to .excalidraw JSON file")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output path: .png (screenshot) or .svg (vector). Default: same name with .png")
    parser.add_argument("--scale", "-s", type=int, default=2, help="Device scale factor (default: 2)")
    parser.add_argument("--width", "-w", type=int, default=1920, help="Max viewport width (default: 1920)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    png_path = render(args.input, args.output, args.scale, args.width)
    print(str(png_path))


if __name__ == "__main__":
    main()
