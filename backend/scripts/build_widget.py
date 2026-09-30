#!/usr/bin/env python3
"""
scripts/build_widget.py
Build the production widget bundle from the readable source.

    backend/app/static/widget.js       <- canonical source, edit this
    backend/app/static/widget.min.js   <- generated, never edit

Usage:
    python backend/scripts/build_widget.py            # build + report
    python backend/scripts/build_widget.py --check    # fail if stale (CI)
    python backend/scripts/build_widget.py --terser /path/to/terser

Minification runs through terser (npx). The source stays the single readable
artifact; the bundle only exists to shrink what every visitor downloads.
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
STATIC_DIR = BACKEND / "app" / "static"
SOURCE = STATIC_DIR / "widget.js"
BUNDLE = STATIC_DIR / "widget.min.js"

BANNER = (
    "/*! XvecBot widget - production build. Generated from widget.js by "
    "scripts/build_widget.py. Do not edit; edit the source instead. */\n"
)


def _terser_cmd(extra: str | None) -> list[str]:
    """Prefer an explicit binary, else fall back to npx (cached outside the repo)."""
    if extra:
        return [extra]
    found = shutil.which("terser")
    return [found] if found else ["npx", "--yes", "terser@5"]


def build(extra: str | None = None, out_path: Path | None = None) -> bytes:
    if not SOURCE.is_file():
        sys.exit(f"error: source not found: {SOURCE}")

    target = out_path or BUNDLE
    cmd = _terser_cmd(extra) + [
        str(SOURCE),
        "--compress",
        "--mangle",
        "--output", str(target),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        sys.exit("error: terser not found. Install it (npm i -g terser) or pass --terser.")
    except subprocess.TimeoutExpired:
        sys.exit("error: terser timed out (network fetch of terser@5?)")

    if proc.returncode != 0:
        sys.exit(f"error: terser failed\n{proc.stderr.strip()}")

    # Prepend the banner terser strips, then syntax-check the result.
    body = BANNER + target.read_text(encoding="utf-8")
    target.write_text(body, encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "check.js"
        probe.write_text(body, encoding="utf-8")
        if shutil.which("node"):
            r = subprocess.run(["node", "--check", str(probe)], capture_output=True, text=True)
            if r.returncode != 0:
                target.unlink(missing_ok=True)
                sys.exit(f"error: minified bundle failed node --check\n{r.stderr.strip()}")

    return body.encode("utf-8")


def report(minified: bytes) -> None:
    src = SOURCE.read_bytes()
    src_gz = len(gzip.compress(src, 9))
    min_gz = len(gzip.compress(minified, 9))
    pct = (1 - len(minified) / len(src)) * 100
    gz_pct = (1 - min_gz / src_gz) * 100
    kb = lambda n: f"{n / 1024:.2f} KiB"
    print("XvecBot widget build")
    print(f"  source      {BUNDLE.parent.name}/widget.js       {len(src):>7,} B  {kb(len(src)):>11}  gzip {kb(src_gz)}")
    print(f"  minified    {BUNDLE.name:<21}{len(minified):>7,} B  {kb(len(minified)):>11}  gzip {kb(min_gz)}")
    print(f"  saved       {'':24}{len(src) - len(minified):>7,} B  {pct:>10.1f}%  gzip {gz_pct:>9.1f}%")
    print(f"  written to  {BUNDLE}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the bundle is missing or stale (for CI)")
    ap.add_argument("--terser", help="path to a terser binary")
    args = ap.parse_args()

    if args.check:
        if not BUNDLE.is_file():
            print("FAIL: widget.min.js is missing - run scripts/build_widget.py")
            return 1
        existing = BUNDLE.read_bytes()
        # Build to a scratch path so a check never mutates the working tree.
        with tempfile.TemporaryDirectory() as tmp:
            fresh = build(args.terser, Path(tmp) / "widget.min.js")
        if existing != fresh:
            print("FAIL: widget.min.js is stale - re-run scripts/build_widget.py")
            return 1
        print("OK: widget.min.js is up to date")
        return 0

    report(build(args.terser))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
