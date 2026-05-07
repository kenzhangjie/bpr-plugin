#!/usr/bin/env python3
"""Auto-crop the bottom whitespace of a Chrome-rendered poster PNG and emit
both a hidpi version and a downsampled share version.

Usage:
  python3 crop_and_share.py <raw.png> <hidpi.png> <share.png>

The raw PNG is assumed to be 2x retina (e.g. 2160 wide for a 1080-logical
layout). Brightness threshold 120 finds the last row with content.
"""
import os
import sys
from pathlib import Path

from PIL import Image


def find_content_bottom(im: Image.Image, threshold: int = 120, sample_step: int = 4) -> int:
    """Return y of the last row containing a pixel brighter than threshold."""
    px = im.load()
    w, h = im.size
    for y in range(h - 1, -1, -1):
        for x in range(0, w, sample_step):
            r, g, b = px[x, y]
            if max(r, g, b) > threshold:
                return y
    return 0


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2

    raw_path, hidpi_path, share_path = (Path(p) for p in sys.argv[1:])
    im = Image.open(raw_path).convert("RGB")
    w, h = im.size
    print(f"raw: {w}x{h}")

    bottom = find_content_bottom(im)
    pad = 80  # retina pixels = 40 logical
    bottom = min(h, bottom + pad)
    cropped = im.crop((0, 0, w, bottom))
    cropped.save(hidpi_path, optimize=True)
    print(f"hidpi: {cropped.size} -> {hidpi_path} ({os.path.getsize(hidpi_path):,} bytes)")

    share = cropped.resize((w // 2, bottom // 2), Image.LANCZOS)
    share.save(share_path, optimize=True)
    print(f"share: {share.size} -> {share_path} ({os.path.getsize(share_path):,} bytes)")

    if raw_path.exists() and raw_path != hidpi_path:
        raw_path.unlink()
        print(f"removed raw: {raw_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
