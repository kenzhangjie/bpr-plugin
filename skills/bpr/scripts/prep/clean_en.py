#!/usr/bin/env python3
"""英文 PREP 源清洗 —— 确定性部分(agent 派子代理做纠错/归属,本脚本做拼装与闸门)。

见 references/prep-and-modes.md「英文子模式源清洗」与
docs/superpowers/specs/2026-07-24-bpr-english-prep-correction-design.md。
"""
from __future__ import annotations
import html, re, json, os, argparse, sys
from collections import Counter


def parse_blocks(raw: str) -> list[str]:
    """把扁平字幕流按 >> 切成块(html 反转义、去空白、丢空块)。"""
    text = html.unescape(raw)
    parts = re.split(r">>\s*", text)
    return [p.strip() for p in parts if p.strip()]


def split_windows(blocks: list, size: int = 25) -> list[list]:
    """按固定大小切窗,供逐窗派子代理。"""
    return [blocks[i:i + size] for i in range(0, len(blocks), size)]


def load_mappings(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("mappings", {})


def apply_correct_table(text: str, mappings: dict) -> str:
    """套用无歧义硬映射。长键优先,避免短键抢先命中长专名。"""
    sorted_keys = sorted(mappings.keys(), key=len, reverse=True)

    i = 0
    result = []
    while i < len(text):
        matched = False
        for key in sorted_keys:
            if text[i:i+len(key)] == key:
                result.append(mappings[key])
                i += len(key)
                matched = True
                break
        if not matched:
            result.append(text[i])
            i += 1

    return ''.join(result)


def norm_words(s: str) -> list[str]:
    s = html.unescape(s).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return s.split()


def word_coverage(src: str, out: str) -> float:
    """源词多重集被输出覆盖的比例。丢句 → 比例下降。1.0 = 全覆盖。"""
    sc, oc = Counter(norm_words(src)), Counter(norm_words(out))
    total = sum(sc.values())
    if total == 0:
        return 1.0
    covered = sum(min(n, oc.get(w, 0)) for w, n in sc.items())
    return covered / total


def append_glossary(names: list, path: str, default_weight: int = 5) -> int:
    """新专名去重后 append 进共用 glossary.txt(格式 name|weight)。返回新增条数。"""
    existing = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                term = line.strip().split("|", 1)[0]
                if term:
                    existing[term.lower()] = True
    added = []
    for n in names:
        n = n.strip()
        if n and n.lower() not in existing:
            existing[n.lower()] = True
            added.append(n)
    if added:
        # Ensure file ends with \n before appending to prevent merging with last line
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                needs_leading_newline = content and not content.endswith("\n")
        else:
            needs_leading_newline = False

        with open(path, "a", encoding="utf-8") as f:
            if needs_leading_newline:
                f.write("\n")
            for n in added:
                f.write(f"{n}|{default_weight}\n")
    return len(added)


def finalize(turns: list, raw: str, mappings: dict, gate: float = 0.98) -> dict:
    """对每句套 apply_correct_table;整体算 word_coverage。返回 {"turns":[...], "coverage": float, "ok": bool}。"""
    out_turns = []
    for t in turns:
        out_turns.append({
            "speaker": t["speaker"],
            "sents": [apply_correct_table(s, mappings) for s in t["sents"]],
        })
    joined = " ".join(s for t in out_turns for s in t["sents"])
    cov = word_coverage(raw, joined)
    return {"turns": out_turns, "coverage": cov, "ok": cov >= gate}


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", required=True, help="拼好的 turns JSON")
    ap.add_argument("--raw", required=True, help="原始逐字稿(算覆盖用)")
    ap.add_argument("--correct-table",
                    default=os.path.expanduser("~/.config/volc/correct_table.json"))
    ap.add_argument("--glossary",
                    default=os.path.expanduser("~/.config/volc/glossary.txt"))
    ap.add_argument("--names", help="本期专名清单 JSON(list),用于回写 glossary")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    turns = json.load(open(a.turns, encoding="utf-8"))
    raw = open(a.raw, encoding="utf-8").read()
    mappings = load_mappings(a.correct_table) if os.path.exists(a.correct_table) else {}
    res = finalize(turns, raw, mappings)
    json.dump(res["turns"], open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if a.names and os.path.exists(a.names):
        added = append_glossary(json.load(open(a.names, encoding="utf-8")), a.glossary)
        print(f"glossary += {added}")
    print(f"coverage {res['coverage']:.3f}  ok={res['ok']}")
    if not res["ok"]:
        print("WARN: 词覆盖 < 0.98,疑似丢句,回 Step 2 重派该窗", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
