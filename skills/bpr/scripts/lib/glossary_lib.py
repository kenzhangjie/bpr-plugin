#!/usr/bin/env python3
"""glossary.txt 的单一实现 —— 解析 / 构映射 / 套用 / 体检 / 回写。

## 为什么要有这个模块(2026-08-07)

同一份「错法 → 正确名」替换逻辑过去在两处各写了一遍:

- `~/.config/volc/volc_asr.py` —— `text.replace(wrong, right)`
- `skills/bpr/scripts/prep/clean_en.py` —— `apply_correct_table()` 逐字符匹配

**两处都没有词边界**,于是 `肖弘|20|小红,小宏,小虹` 这一行把「小红书」改成
「肖弘书」、「小红帽」改成「肖弘帽」。而且它发生在 ASR 输出那一刻(CLEAN 之前),
CLEAN 的 prompt 又写着「专名与 glossary 不一致时信 glossary」,VERIFY 的覆盖闸
只查「有没有丢」不查「有没有被改错」—— 三道网全穿。

修一处漏一处,所以合到这里。两个调用方都 import 本模块,不许再各写一份。

## 三层防护

1. **保护名单优先**(`protected`)—— 单次扫描的正则里,保护项分支排在错法分支
   前面,同一起点上保护项永远赢。保护名单 = glossary 第 1 列全部正确名
   + `~/.config/volc/protect.txt` 里的常用词(小红书 / 小红帽 …)。
2. **拉丁键强制词边界** —— `Codex` 不会命中 `Codexes`。CJK 没有词边界可用,
   靠第 1 层和第 3 层。
3. **长度闸** —— CJK 键 < 3 字、拉丁键 < 4 字直接拒收并 WARN。2 字 CJK 键
   本质上不安全(未知碰撞防不住),`confidently wrong 比留错更坏`。
"""
from __future__ import annotations

import html
import os
import re

GLOSSARY_PATH = os.path.expanduser("~/.config/volc/glossary.txt")
PROTECT_PATH = os.path.expanduser("~/.config/volc/protect.txt")

#: 键长下限。CJK 按字数,拉丁/混合按字符数。见模块 docstring「三层防护」第 3 条。
MIN_CJK_KEY = 3
MIN_LATIN_KEY = 4

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_ASCII_WORD = re.compile(r"[0-9A-Za-z]")


def parse_glossary(path: str = GLOSSARY_PATH) -> list[tuple[str, str, list[str]]]:
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


def load_protected(entries: list, path: str = PROTECT_PATH) -> set[str]:
    """保护名单:这些串一旦在正文里出现,整段原样保留,不参与错法替换。

    = glossary 第 1 列全部正确名(正确的写法不该被改)
    + protect.txt 每行一个的常用词(不是专名、但会被短错法误伤的,如 小红书)。
    """
    protected = {term for term, _w, _v in entries if term}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    protected.add(line)
    return protected


def key_rejection(key: str) -> str | None:
    """键太短就返回拒收原因,安全则返回 None。"""
    if not key:
        return "空键"
    if _CJK.search(key):
        n = len(key)
        if n < MIN_CJK_KEY:
            return f"CJK 键仅 {n} 字(下限 {MIN_CJK_KEY}),会误伤含它的常用词"
    elif len(key) < MIN_LATIN_KEY:
        return f"拉丁键仅 {len(key)} 字符(下限 {MIN_LATIN_KEY})"
    return None


class Corrections:
    """一次装配好的纠错器:映射 + 保护名单 + 编译好的正则 + 装配期告警。"""

    def __init__(self, mappings: dict, protected: set, warnings: list):
        self.mappings = mappings
        self.protected = protected
        self.warnings = warnings
        self._re = _build_regex(mappings, protected)

    def __len__(self) -> int:
        return len(self.mappings)

    def apply(self, text: str) -> str:
        """套用纠错。保护名单优先,拉丁键带词边界。"""
        if not self._re or not text:
            return text

        def repl(m: re.Match) -> str:
            if m.groupdict().get("keep") is not None:
                return m.group(0)          # 保护项:原样吐回
            return self.mappings[m.group(0)]

        return self._re.sub(repl, text)


def _key_pattern(key: str) -> str:
    """键的正则:两端是 ASCII 字母数字时加词边界(CJK 无边界可加)。"""
    pat = re.escape(key)
    if _ASCII_WORD.match(key[0]):
        pat = r"(?<![0-9A-Za-z])" + pat
    if _ASCII_WORD.match(key[-1]):
        pat = pat + r"(?![0-9A-Za-z])"
    return pat


def _build_regex(mappings: dict, protected: set):
    """单次扫描的正则。`keep` 分支排在 `fix` 前面 —— 同一起点上保护项赢;
    各分支内部长键优先,避免短键抢先命中长专名。"""
    parts = []
    keep = sorted((p for p in protected if p), key=len, reverse=True)
    fix = sorted(mappings, key=len, reverse=True)
    if keep:
        parts.append("(?P<keep>" + "|".join(_key_pattern(k) for k in keep) + ")")
    if fix:
        parts.append("(?P<fix>" + "|".join(_key_pattern(k) for k in fix) + ")")
    return re.compile("|".join(parts)) if parts else None


def build_corrections(entries: list, protect_path: str = PROTECT_PATH) -> Corrections:
    """从 glossary 条目装配纠错器。过长度闸、查冲突,拒收的都进 warnings。"""
    mappings: dict[str, str] = {}
    warnings: list[str] = []
    for term, _w, variants in entries:
        for v in variants:
            why = key_rejection(v)
            if why:
                warnings.append(f"拒收错法 {v!r}→{term!r}:{why}")
                continue
            if v == term:
                warnings.append(f"跳过错法 {v!r}→{term!r}:错法与正确名相同")
                continue
            if v in mappings and mappings[v] != term:
                # 与 volc_asr.py 的历史行为一致:先到者胜,后者告警丢弃。
                warnings.append(
                    f"错法 {v!r} 同时映射到 {mappings[v]!r} 和 {term!r},跳过后者")
                continue
            mappings[v] = term
    return Corrections(mappings, load_protected(entries, protect_path), warnings)


def lint(entries: list, protect_path: str = PROTECT_PATH) -> dict:
    """glossary 体检。给 `--check-glossary` 用,把会咬人的键提前抓出来。

    返回 {"rejected": [...], "conflicts": [...], "collisions": [...], "stats": {...}}
    """
    c = build_corrections(entries, protect_path)
    rejected = [w for w in c.warnings if w.startswith("拒收")]
    conflicts = [w for w in c.warnings if "同时映射到" in w]

    # 碰撞:错法与某个保护项互为子串 —— 任一方向都危险。
    #   错法 ⊂ 保护项 → 保护项被误伤(小红 ⊂ 小红书)
    #   保护项 ⊂ 错法 → 该错法永远纠不动(保护分支先吃掉前缀)
    collisions = []
    for v, term in c.mappings.items():
        for p in c.protected:
            if p == v or p == term:
                continue
            if v in p:
                collisions.append(f"错法 {v!r}→{term!r} 是保护项 {p!r} 的子串 "
                                  f"(已被保护名单挡住,但说明这个键太泛)")
            elif p in v:
                collisions.append(f"保护项 {p!r} 是错法 {v!r} 的子串 "
                                  f"(该错法会纠不动 → 改长保护项或删这条错法)")
    return {
        "rejected": rejected,
        "conflicts": conflicts,
        "collisions": collisions,
        "stats": {"terms": len(entries), "mappings": len(c.mappings),
                  "protected": len(c.protected)},
    }


def normalize_names(names: list) -> list[tuple[str, list[str]]]:
    """把 --names 的两种形态统一成 [(term, [seen_as...])]。

    - 老形态:`["OpenAI", "Codex"]`(只回写第 1 列)
    - 新形态:`[{"term": "Codex", "seen_as": ["Codeex"]}]`(顺带回写第 3 列)
    """
    out = []
    for n in names:
        if isinstance(n, dict):
            term = str(n.get("term", "")).strip()
            seen = [str(s).strip() for s in (n.get("seen_as") or []) if str(s).strip()]
        else:
            term, seen = str(n).strip(), []
        if term:
            out.append((term, seen))
    return out


def append_glossary_detail(names: list, path: str = GLOSSARY_PATH,
                           default_weight: int = 5) -> dict:
    """回写飞轮:新专名 append 第 1 列,本期真见过的错法 merge 进第 3 列。

    错法要过 `key_rejection` 的长度闸、且不能与保护名单碰撞、不能已映射到别的
    正确名 —— 拒收的进 `rejected`,**不写进真源**(污染 glossary 比漏记更贵)。

    返回 {"added": 新专名数, "variants_added": 新错法数, "rejected": [原因...]}
    """
    pairs = normalize_names(names)
    entries = parse_glossary(path)
    protected = load_protected(entries, PROTECT_PATH)
    known_variant = {v: term for term, _w, vs in entries for v in vs}

    # term(小写)→ 原始行号,用于 merge 第 3 列
    by_lower = {term.lower(): i for i, (term, _w, _v) in enumerate(entries)}

    rejected: list[str] = []

    def variant_ok(v: str, term: str) -> bool:
        why = key_rejection(v)
        if why:
            rejected.append(f"{v!r}→{term!r}:{why}")
            return False
        if v == term:
            return False
        if v in known_variant and known_variant[v] != term:
            rejected.append(f"{v!r}→{term!r}:已映射到 {known_variant[v]!r}")
            return False
        for p in protected:
            if p != v and v in p:
                rejected.append(f"{v!r}→{term!r}:是保护项 {p!r} 的子串")
                return False
        return True

    # ── 1. 已存在的专名:只 merge 新错法进第 3 列 ──
    variants_added = 0
    touched: dict[int, list[str]] = {}
    new_terms: list[tuple[str, list[str]]] = []
    for term, seen in pairs:
        idx = by_lower.get(term.lower())
        if idx is None:
            new_terms.append((term, seen))
            by_lower[term.lower()] = -1        # 占位,防同批重复
            continue
        if idx < 0:
            continue
        have = set(entries[idx][2])
        fresh = [v for v in seen if v not in have and variant_ok(v, entries[idx][0])]
        if fresh:
            touched.setdefault(idx, []).extend(fresh)
            have.update(fresh)
            known_variant.update({v: entries[idx][0] for v in fresh})
            variants_added += len(fresh)

    if touched:
        _rewrite_lines(path, entries, touched)
        entries = parse_glossary(path)          # 重读,行号可能已变

    # ── 2. 全新专名:append(带上安全的错法)──
    added = []
    for term, seen in new_terms:
        fresh = [v for v in seen if variant_ok(v, term)]
        variants_added += len(fresh)
        known_variant.update({v: term for v in fresh})
        added.append((term, fresh))

    if added:
        need_nl = False
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                content = f.read()
            need_nl = bool(content) and not content.endswith("\n")
        with open(path, "a", encoding="utf-8") as f:
            if need_nl:
                f.write("\n")
            for term, fresh in added:
                line = f"{term}|{default_weight}"
                if fresh:
                    line += "|" + ",".join(fresh)
                f.write(line + "\n")

    return {"added": len(added), "variants_added": variants_added,
            "rejected": rejected}


def _rewrite_lines(path: str, entries: list, touched: dict) -> None:
    """把 touched 里的新错法 merge 回原文件对应行(只碰这些行,注释/空行不动)。"""
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    # 重建 entry 序号 → 物理行号(parse_glossary 跳过注释和空行,序号会错位)
    entry_line = []
    for i, raw in enumerate(lines):
        s = raw.strip()
        if s and not s.startswith("#") and s.split("|")[0].strip():
            entry_line.append(i)

    for idx, fresh in touched.items():
        if idx >= len(entry_line):
            continue
        ln = entry_line[idx]
        term, weight, variants = entries[idx]
        merged = variants + [v for v in fresh if v not in variants]
        lines[ln] = f"{term}|{weight or 5}|" + ",".join(merged)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ─────────────────────────── 兼容层 ───────────────────────────
# clean_en.py 与既有测试沿用下面这些名字;实现全部落到上面。

def glossary_mappings(entries: list) -> dict:
    """{错法 → 正确名}(已过长度闸与冲突检查)。告警丢弃 —— 要看告警用
    `build_corrections(entries).warnings`。"""
    return build_corrections(entries).mappings


def apply_correct_table(text: str, mappings: dict, protected: set | None = None) -> str:
    """套用硬映射。**每句调一次会重编译正则**,批量场景请自己建
    `Corrections` 复用(见 clean_en.finalize)。"""
    return Corrections(mappings, protected or set(), []).apply(text)


def append_glossary(names: list, path: str = GLOSSARY_PATH,
                    default_weight: int = 5) -> int:
    """回写新专名,返回新增条数(兼容旧签名)。细节用 `append_glossary_detail`。"""
    return append_glossary_detail(names, path, default_weight)["added"]


def scan_glossary(text: str, entries: list) -> list[dict]:
    """用正文反查全表,返回命中的专名 + 它们的已知错法。
    给 PREP Step 1 的 brief 用 —— 取代「人眼扫前 20 行」的抽样判断。"""
    low = html.unescape(text).lower()
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
