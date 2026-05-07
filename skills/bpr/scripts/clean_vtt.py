#!/usr/bin/env python3
"""Clean a YouTube auto-caption .vtt into deduplicated plain text.

Usage:
  python3 clean_vtt.py input.vtt output.txt

Strips: WEBVTT header, Kind/Language headers, cue numbers, timestamps,
inline <c>/<timestamp> tags, position/align metadata. De-duplicates
consecutive identical lines (YouTube often emits each line twice for
rolling captions).
"""
import re
import sys
from pathlib import Path


def clean(vtt_text: str) -> str:
    keep: list[str] = []
    seen: set[str] = set()
    for line in vtt_text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s == "WEBVTT" or s.startswith("Kind:") or s.startswith("Language:"):
            continue
        if "-->" in s:
            continue
        if re.fullmatch(r"\d+", s):
            continue
        if re.search(r"align:|position:|size:", s):
            continue
        s = re.sub(r"<[^>]+>", "", s)
        if not s or s in seen:
            continue
        seen.add(s)
        keep.append(s)
    return " ".join(keep)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    text = clean(src.read_text(encoding="utf-8", errors="replace"))
    dst.write_text(text, encoding="utf-8")
    chars = len(text)
    words = len(text.split())
    print(f"wrote {dst}: {chars:,} chars, ~{words:,} words")
    return 0


if __name__ == "__main__":
    sys.exit(main())
