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


GLOSSARY_DEFAULT = os.path.expanduser("~/.config/volc/glossary.txt")


def load_mappings(path: str) -> dict:
    """遗留 correct_table.json 读法。2026-07-25 起该文件已并入 glossary.txt 第 3 列,
    仅作向后兼容保留 —— 新代码走 parse_glossary / glossary_mappings。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("mappings", {})


def parse_glossary(path: str) -> list[tuple[str, str, list[str]]]:
    """读 glossary.txt(专名单一真源)。每行 `正确名|权重|错法1,错法2,...`,
    后两列可缺。返回 [(term, weight, [variants...])];文件不存在返回 []。"""
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cols = line.split("|")
            term = cols[0].strip()
            if not term:
                continue
            weight = cols[1].strip() if len(cols) > 1 else ""
            variants = [v.strip() for v in cols[2].split(",")] if len(cols) > 2 else []
            out.append((term, weight, [v for v in variants if v]))
    return out


def glossary_mappings(entries: list) -> dict:
    """从 glossary 条目构 {错法 → 正确名} 硬映射(第 3 列)。"""
    return {v: term for term, _w, variants in entries for v in variants}


def scan_glossary(text: str, entries: list) -> list[dict]:
    """用正文反查全表,返回命中的专名 + 它们的已知错法。
    给 PREP Step 1 的 brief 用 —— 取代"人眼扫前 20 行"的抽样判断。"""
    low = text.lower()
    hits = []
    for term, _w, variants in entries:
        if len(term) < 3:
            continue                      # 2 字以内太容易误命中
        found = term.lower() in low
        seen = [v for v in variants if v.lower() in low]
        if found or seen:
            hits.append({"term": term, "misspellings": variants,
                         "seen_in_source": seen})
    return hits


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
    needs_leading_newline = False

    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            content = f.read()
            # Build dedup set from single read
            for line in content.split('\n'):
                term = line.strip().split("|", 1)[0]
                if term:
                    existing[term.lower()] = True
            # Check if file ends with newline
            needs_leading_newline = content and not content.endswith("\n")

    added = []
    for n in names:
        n = n.strip()
        if n and n.lower() not in existing:
            existing[n.lower()] = True
            added.append(n)

    if added:
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
    cov = word_coverage(apply_correct_table(raw, mappings), joined)
    return {"turns": out_turns, "coverage": cov, "ok": cov >= gate}


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", help="拼好的 turns JSON(finalize 模式必填)")
    ap.add_argument("--raw", help="原始逐字稿(算覆盖用;finalize 模式必填)")
    ap.add_argument("--correct-table", default=None,
                    help="遗留 correct_table.json;默认不用(专名真源是 glossary 第 3 列)")
    ap.add_argument("--glossary", default=GLOSSARY_DEFAULT)
    ap.add_argument("--names", help="本期专名清单 JSON(list),用于回写 glossary")
    ap.add_argument("--out", help="输出 turns.clean.json(finalize 模式必填)")
    ap.add_argument("--scan", metavar="TRANSCRIPT",
                    help="扫描模式:用 transcript 反查 glossary 全表,输出命中专名 JSON,供 PREP Step 1 brief 用")
    a = ap.parse_args(argv)

    entries = parse_glossary(a.glossary)
    if not entries:
        print(f"WARN: glossary 读不到或为空 → {a.glossary}(专名硬映射本轮不生效)",
              file=sys.stderr)

    # ── 扫描模式:只出 brief 用的命中清单,不做 finalize ──
    if a.scan:
        hits = scan_glossary(open(a.scan, encoding="utf-8").read(), entries)
        print(json.dumps(hits, ensure_ascii=False, indent=1))
        print(f"glossary {len(entries)} 条 → 本期命中 {len(hits)} 条", file=sys.stderr)
        return 0

    missing = [n for n in ("turns", "raw", "out") if not getattr(a, n)]
    if missing:
        ap.error("finalize 模式缺参数: " + ", ".join("--" + m for m in missing))

    turns = json.load(open(a.turns, encoding="utf-8"))
    raw = open(a.raw, encoding="utf-8").read()

    # 专名硬映射:glossary 第 3 列为真源;--correct-table 仅遗留兼容,glossary 优先。
    mappings = {}
    if a.correct_table:
        if os.path.exists(a.correct_table):
            mappings.update(load_mappings(a.correct_table))
        else:
            print(f"WARN: --correct-table 指向的文件不存在 → {a.correct_table}",
                  file=sys.stderr)
    mappings.update(glossary_mappings(entries))
    if not mappings:
        print("WARN: 专名硬映射为空,apply_correct_table 本轮等于空转 —— "
              "确认 glossary 第 3 列(错法)是否已维护", file=sys.stderr)
    else:
        print(f"专名硬映射 {len(mappings)} 条(来自 glossary 第 3 列)")

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
