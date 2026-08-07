#!/usr/bin/env python3
"""英文 PREP 源清洗 —— 确定性部分(agent 派子代理做纠错/归属,本脚本做拼装与闸门)。

见 references/prep-and-modes.md「英文子模式源清洗」与
docs/superpowers/specs/2026-07-24-bpr-english-prep-correction-design.md。

glossary 的解析 / 映射 / 替换 / 回写全部落在 `scripts/lib/glossary_lib.py`
—— 那是单一实现,volc_asr.py 也 import 同一份(2026-08-07 起,详见该模块 docstring)。
"""
from __future__ import annotations
import re, json, os, argparse, sys, pathlib
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))
import glossary_lib as G  # noqa: E402

# 兼容层:既有调用方 / 测试沿用这些名字,实现在 glossary_lib。
GLOSSARY_DEFAULT = G.GLOSSARY_PATH
parse_glossary = G.parse_glossary
glossary_mappings = G.glossary_mappings
scan_glossary = G.scan_glossary
apply_correct_table = G.apply_correct_table
append_glossary = G.append_glossary


def parse_blocks(raw: str) -> list[str]:
    """把扁平字幕流按 >> 切成块(html 反转义、去空白、丢空块)。"""
    import html
    text = html.unescape(raw)
    parts = re.split(r">>\s*", text)
    return [p.strip() for p in parts if p.strip()]


def split_windows(blocks: list, size: int = 25) -> list[list]:
    """按固定大小切窗,供逐窗派子代理。"""
    return [blocks[i:i + size] for i in range(0, len(blocks), size)]


def load_mappings(path: str) -> dict:
    """遗留 correct_table.json 读法。2026-07-25 起该文件已并入 glossary.txt 第 3 列,
    仅作向后兼容保留 —— 新代码走 glossary_lib。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("mappings", {})


def norm_words(s: str) -> list[str]:
    import html
    s = html.unescape(s).lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return s.split()


def _cov(src: Counter, out: Counter) -> float:
    total = sum(src.values())
    if total == 0:
        return 1.0
    return sum(min(n, out.get(w, 0)) for w, n in src.items()) / total


def word_coverage(src: str, out: str) -> float:
    """源词多重集被输出覆盖的比例。丢句 → 比例下降。1.0 = 全覆盖。"""
    return _cov(Counter(norm_words(src)), Counter(norm_words(out)))


def added_ratio(src: str, out: str) -> float:
    """输出里**多出来**的词占源词总量的比例 —— 覆盖率的反向指标。

    `word_coverage` 只问「源词有没有被盖住」,子代理凭空加一整段完全不掉分。
    这个指标补上那半边:偏高 = 疑似加译 / 幻觉 / 复述。专名纠错本身会贡献少量
    新词(变体只在源侧),所以它是**报告项不是硬闸**,阈值只用来提醒。
    """
    sc, oc = Counter(norm_words(src)), Counter(norm_words(out))
    total = sum(sc.values())
    if total == 0:
        return 0.0
    return sum(max(0, n - sc.get(w, 0)) for w, n in oc.items()) / total


#: added_ratio 超过它就在 stdout 提醒(不影响退出码)。
ADDED_WARN = 0.05


def finalize(turns: list, raw: str, mappings, gate: float = 0.98,
             windows: list | None = None) -> dict:
    """对每句套硬映射;算整体 + 逐窗覆盖率与加译率。

    `mappings` 可以是 dict(旧签名)或 `glossary_lib.Corrections`(带保护名单,
    CLI 走这条)。`windows` 给原始窗文本列表时,额外产出**逐窗覆盖率**和最差窗
    序号 —— 没有它,「把该窗打回 Step 2 重派」这条硬规则拿不到「哪一窗」。

    返回 {"turns", "coverage", "ok", "added_ratio", "windows", "worst_window"}
    """
    corr = mappings if isinstance(mappings, G.Corrections) else \
        G.Corrections(mappings or {}, set(), [])

    out_turns = [{"speaker": t["speaker"],
                  "sents": [corr.apply(s) for s in t["sents"]]} for t in turns]
    joined = " ".join(s for t in out_turns for s in t["sents"])

    # 源侧也过一遍映射,让专名变体在比对前先收敛(否则纠对了反而掉覆盖率)
    canon_raw = corr.apply(raw)
    out_c = Counter(norm_words(joined))
    cov = _cov(Counter(norm_words(canon_raw)), out_c)

    per_window = []
    worst = None
    if windows:
        for i, w in enumerate(windows):
            wtext = w if isinstance(w, str) else " ".join(map(str, w))
            wcov = _cov(Counter(norm_words(corr.apply(wtext))), out_c)
            row = {"index": i, "coverage": round(wcov, 4), "ok": wcov >= gate}
            per_window.append(row)
            if worst is None or wcov < worst["coverage"]:
                worst = {"index": i, "coverage": round(wcov, 4)}

    ok = cov >= gate and all(r["ok"] for r in per_window)
    return {"turns": out_turns, "coverage": cov, "ok": ok,
            "added_ratio": added_ratio(canon_raw, joined),
            "windows": per_window, "worst_window": worst}


def _print_lint(report: dict) -> int:
    s = report["stats"]
    print(f"glossary 体检:{s['terms']} 条专名 · {s['mappings']} 条硬映射 · "
          f"{s['protected']} 项保护名单")
    for label, key in (("拒收的错法(键太短,已不生效)", "rejected"),
                       ("冲突(同一错法映射到多个正确名)", "conflicts"),
                       ("碰撞(与保护名单互为子串)", "collisions")):
        rows = report[key]
        print(f"\n{label}:{len(rows)} 条")
        for r in rows:
            print(f"  · {r}")
    bad = len(report["conflicts"]) + len(report["collisions"])
    print("\n" + ("✓ 没有冲突/碰撞" if not bad else f"✗ {bad} 条要处理"))
    return 1 if bad else 0


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", help="拼好的 turns JSON(finalize 模式必填)")
    ap.add_argument("--raw", help="原始逐字稿(算覆盖用;finalize 模式必填)")
    ap.add_argument("--windows", help="原始窗 JSON(list[str] 或 list[list[str]]);"
                                     "给了就出逐窗覆盖率 + 最差窗序号")
    ap.add_argument("--correct-table", default=None,
                    help="遗留 correct_table.json;默认不用(专名真源是 glossary 第 3 列)")
    ap.add_argument("--glossary", default=G.GLOSSARY_PATH)
    ap.add_argument("--protect", default=G.PROTECT_PATH,
                    help="保护名单(每行一个常用词,不参与错法替换)")
    ap.add_argument("--names", help="本期专名 JSON:list[str] 或 "
                                    'list[{"term":..., "seen_as":[错法...]}],用于回写 glossary')
    ap.add_argument("--out", help="输出 turns.clean.json(finalize 模式必填)")
    ap.add_argument("--scan", metavar="TRANSCRIPT",
                    help="扫描模式:用 transcript 反查 glossary 全表,输出命中专名 JSON,供 PREP Step 1 brief 用")
    ap.add_argument("--check-glossary", action="store_true",
                    help="体检模式:列出被拒收的短键、冲突、与保护名单的碰撞")
    a = ap.parse_args(argv)

    entries = G.parse_glossary(a.glossary)
    if not entries:
        print(f"WARN: glossary 读不到或为空 → {a.glossary}(专名硬映射本轮不生效)",
              file=sys.stderr)

    if a.check_glossary:
        return _print_lint(G.lint(entries, a.protect))

    if a.scan:
        hits = G.scan_glossary(open(a.scan, encoding="utf-8").read(), entries)
        print(json.dumps(hits, ensure_ascii=False, indent=1))
        print(f"glossary {len(entries)} 条 → 本期命中 {len(hits)} 条", file=sys.stderr)
        return 0

    missing = [n for n in ("turns", "raw", "out") if not getattr(a, n)]
    if missing:
        ap.error("finalize 模式缺参数: " + ", ".join("--" + m for m in missing))

    turns = json.load(open(a.turns, encoding="utf-8"))
    raw = open(a.raw, encoding="utf-8").read()
    windows = json.load(open(a.windows, encoding="utf-8")) if a.windows else None

    # 专名硬映射:glossary 第 3 列为真源;--correct-table 仅遗留兼容,glossary 优先。
    corr = G.build_corrections(entries, a.protect)
    if a.correct_table:
        if os.path.exists(a.correct_table):
            legacy = load_mappings(a.correct_table)
            legacy.update(corr.mappings)          # glossary 优先
            corr = G.Corrections(legacy, corr.protected, corr.warnings)
        else:
            print(f"WARN: --correct-table 指向的文件不存在 → {a.correct_table}",
                  file=sys.stderr)

    for w in corr.warnings:
        print(f"WARN glossary: {w}", file=sys.stderr)

    if not corr.mappings:
        print("WARN: 专名硬映射为空,替换本轮等于空转 —— "
              "确认 glossary 第 3 列(错法)是否已维护", file=sys.stderr)
    else:
        print(f"专名硬映射 {len(corr.mappings)} 条(来自 glossary 第 3 列)· "
              f"保护名单 {len(corr.protected)} 项")

    res = finalize(turns, raw, corr, windows=windows)
    json.dump(res["turns"], open(a.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    if a.names and os.path.exists(a.names):
        d = G.append_glossary_detail(json.load(open(a.names, encoding="utf-8")),
                                    a.glossary)
        print(f"glossary += {d['added']} 条专名 · 错法 += {d['variants_added']} 条"
              + (f" · 拒收 {len(d['rejected'])} 条" if d["rejected"] else ""))
        for r in d["rejected"]:
            print(f"  拒收错法 {r}", file=sys.stderr)

    print(f"coverage {res['coverage']:.3f}  ok={res['ok']}  "
          f"added_ratio {res['added_ratio']:.3f}")
    if res["added_ratio"] > ADDED_WARN:
        print(f"NOTE: 加译率 {res['added_ratio']:.3f} > {ADDED_WARN} —— "
              "输出里多出不少源稿没有的词,抽查是否有加译/复述(报告项,不拦)",
              file=sys.stderr)

    bad = [r for r in res["windows"] if not r["ok"]]
    if res["windows"]:
        w = res["worst_window"]
        print(f"逐窗覆盖:{len(res['windows'])} 窗,最差 #{w['index']} = {w['coverage']:.3f}")
    if bad:
        ids = ", ".join(f"#{r['index']}({r['coverage']:.3f})" for r in bad)
        print(f"WARN: 这些窗覆盖 < 0.98,回 Step 2 重派:{ids}", file=sys.stderr)
        return 1
    if not res["ok"]:
        print("WARN: 词覆盖 < 0.98,疑似丢句;未传 --windows 所以定位不到具体窗 —— "
              "补上 --windows 再跑一次就能拿到窗号", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
