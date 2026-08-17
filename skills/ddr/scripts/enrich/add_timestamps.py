#!/usr/bin/env python3
"""Inject per-turn timestamps into a BPR podcast HTML, from a YouTube .vtt.

Why this exists (lessons-learned L6): YouTube subtitles are ROLLUP captions —
each cue repeats the previous line's text plus a few newly appended words, and
the first word of each cue sits BARE before the first <c> tag. A naive parser
that only reads <c> words (and ignores rollup) produces a broken/duplicated
word stream that almost never matches the rendered sentences. This script:
  1. parses cues (start time + plain text, tags stripped),
  2. rebuilds a clean word->time stream by emitting ONLY each cue's newly
     appended tail words (rollup-aware),
  3. for each <div class="turn">, takes its first <p class="en"> sentence,
     normalizes it (drops [bracketed] insertions), and finds that word
     sequence in the stream to get the start time,
  4. inserts <span class="timestamp">HH:MM:SS</span> after the speaker span.

Unmatched short interjections (<4 distinctive words) are left without a
timestamp rather than guessed. Monotonic: a turn never goes backward in time.

Usage:  python3 add_timestamps.py <transcript.en-orig.vtt> <reader.html>
Prints  matched/total. Edits the HTML in place.
"""
import re, sys, html as ihtml


def norm_words(s):
    s = ihtml.unescape(s)
    s = re.sub(r"\[[^\]]*\]", " ", s)        # drop [bracketed] editorial insertions
    s = re.sub(r"<[^>]+>", " ", s)           # drop any inline tags (e.g. <a>)
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return s.split()


def hms(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def fmt(sec):
    sec = int(sec)
    return f"{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d}"


def build_stream(vtt_path):
    raw = open(vtt_path, encoding="utf-8").read()
    stream, emitted = [], []
    for b in re.split(r"\n\n+", raw):
        mh = re.search(r"(\d\d:\d\d:\d\d\.\d\d\d)\s*-->", b)
        if not mh:
            continue
        start = hms(mh.group(1))
        payload = re.sub(r"^.*-->.*$", "", b, count=1, flags=re.M)
        payload = re.sub(r"<[^>]+>", "", payload)
        payload = ihtml.unescape(payload).replace(">>", " ")
        w = norm_words(payload)
        if not w:
            continue
        # rollup: emit only the tail that extends what's already emitted
        maxk = min(len(emitted), len(w))
        k = 0
        for cand in range(maxk, 0, -1):
            if emitted[-cand:] == w[:cand]:
                k = cand
                break
        for word in w[k:]:
            stream.append((start, word))
            emitted.append(word)
    return stream


def main():
    if len(sys.argv) != 3:
        print("usage: add_timestamps.py <vtt> <html>", file=sys.stderr)
        sys.exit(2)
    vtt, htmlf = sys.argv[1], sys.argv[2]
    stream = build_stream(vtt)
    words = [w for _, w in stream]
    N = len(words)

    def find(kw, cur):
        for klen in (8, 6, 5, 4):
            key = kw[:klen]
            if len(key) < 4:
                continue
            for i in range(cur, N - len(key) + 1):
                if words[i:i + len(key)] == key:
                    return stream[i][0], i
            for i in range(0, N - len(key) + 1):
                if words[i:i + len(key)] == key:
                    return stream[i][0], max(cur, i)
        return None, cur

    doc = open(htmlf, encoding="utf-8").read()
    doc = re.sub(r'<span class="timestamp">[^<]*</span>', "", doc)  # idempotent
    turns = list(re.finditer(
        r'<div class="turn">\s*<div class="turn-head">(.*?)</div>\s*'
        r'<div class="turn-body">(.*?)</div>\s*</div>', doc, re.S))
    cur, last, matched, repl = 0, -1, 0, []
    for m in turns:
        head, body = m.group(1), m.group(2)
        en = re.search(r'<p class="en">(.*?)</p>', body, re.S)
        t = None
        if en:
            t, cur = find(norm_words(en.group(1)), cur)
        if t is None:
            continue
        if t >= last:
            last = t
        matched += 1
        newhead = re.sub(r'(</span>)',
                         r'\1<span class="timestamp">' + fmt(t) + '</span>',
                         head, count=1)
        repl.append((m.span(), m.group(0).replace(head, newhead, 1)))
    for (s, e), nb in reversed(repl):
        doc = doc[:s] + nb + doc[e:]
    open(htmlf, "w", encoding="utf-8").write(doc)
    print(f"timestamps: matched {matched}/{len(turns)} turns")


if __name__ == "__main__":
    main()
