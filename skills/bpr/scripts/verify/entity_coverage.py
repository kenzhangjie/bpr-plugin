#!/usr/bin/env python3
"""中文模式实体覆盖闸 —— 把 verify.md 那条「抽查数字/专名有没有丢」变成脚本。

## 为什么需要它

中文模式 CLEAN 会把逐字口语**书面重写**,句数比因此失效,英文那套句数覆盖闸用不了,
于是 verify.md 改成「实体级覆盖:底档里的数字/专名,书面版必须都在」——
但一直只是**人工抽查**一行字。抽查 ≠ 检索:漏掉的恰恰是没被抽到的那条。

## 必须按数值比,不能按字面比(2026-08-07 实测教训)

第一版按字面串比对,在两篇已发布的成品上报了 3 个「丢失」,人工复核**全是假警报**:

| 底档 | 书面版 | 第一版判定 |
|---|---|---|
| `百分之八十` | `80%` | ✗ 误报 |
| `1700万` | `一千七百万` | ✗ 误报 |
| `百分之一百二百` | `百分之一二百` | ✗ 误报 |

书面化本来就会在「30%」和「百分之三十」之间自由换写。所以数字一律**归一成数值**
再比;中文口语的范围说法(`一百二百` = 一百到二百,同量级单位重复出现)解析不了,
直接**不纳入硬闸** —— 宁可少拦,也不能让闸门天天喊狼来了,那等于没有闸门。

## 硬闸只管数值,专名只报告

数值几乎不会被合法吞掉 —— 少一个就是吞信息,**拦**。
拉丁专名会被 CLEAN 合法纠正(Aultimate→Altimeter),少一个可能是纠对了 —— **只报告**。

用法:
    # 对账渲染好的成品(最有用:验的是最终产物)
    python3 entity_coverage.py --html <reader.html>
    # 或分别给两侧
    python3 entity_coverage.py --raw transcript.txt --clean clean.txt

退出码:0 通过 · 1 有数值丢失 · 2 输入不合法
"""
from __future__ import annotations
import argparse
import html as htmllib
import re
import sys
from collections import Counter

# ── 数值抽取 ──────────────────────────────────────────────
CN_DIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
            "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_SMALL_UNIT = {"十": 10, "百": 100, "千": 1000}
CN_BIG_UNIT = {"万": 10 ** 4, "亿": 10 ** 8}
CN_RUN = re.compile(r"[〇零一二三四五六七八九十百千万亿两]{1,16}")
ARABIC = re.compile(r"(\d+(?:\.\d+)?)\s*(千万|百万|万|亿|k|K|M|B)?")
ARABIC_SCALE = {"千万": 10 ** 7, "百万": 10 ** 6, "万": 10 ** 4, "亿": 10 ** 8,
                "k": 10 ** 3, "K": 10 ** 3, "M": 10 ** 6, "B": 10 ** 9}

LATIN = re.compile(r"[A-Za-z][A-Za-z0-9.+\-]{2,}")

#: 拉丁噪音词,不当专名统计。
LATIN_STOP = {
    "the", "and", "for", "you", "that", "this", "with", "have", "not", "okay",
    "yeah", "just", "like", "what", "then", "they", "was", "are", "http",
    "https", "com", "www", "speaker", "part", "call", "fine", "shop", "seed",
    "scale", "local", "cloud", "feel", "favor", "beats", "million", "benefit",
}

#: 拉丁专名在底档里至少出现这么多次才进报告(一次性的多半是 ASR 噪音)。
LATIN_MIN_HITS = 2

#: 数值允许缺失的比例。0 = 一个都不许丢。
NUMERIC_TOLERANCE = 0.0


def cn2num(s: str) -> float | None:
    """中文数字串 → 数值。解析不了(含口语范围说法)返回 None。

    `一千七百万` → 17000000 · `八十` → 80 · `二零二六` → 2026
    `一百二百`(= 一百到二百,同量级单位重复)→ None,不纳入硬闸。
    """
    if not s:
        return None
    # 光有单位没有数字 = 「百分之」的百 / 「1700万」的万 这种残片,不是一个数。
    # 例外:以「十」开头(十万 / 十五 / 十亿),那个隐含的 1 是合法的。
    if not any(c in CN_DIGIT for c in s) and not (len(s) > 1 and s[0] == "十"):
        return None
    # 同一量级单位重复出现 = 口语范围/枚举(一百二百 / 三万五万),不猜
    for u in list(CN_SMALL_UNIT) + list(CN_BIG_UNIT):
        if s.count(u) > 1:
            return None
    # 纯数字连读(二零二六 / 一二三)当逐位读数
    if all(c in CN_DIGIT for c in s):
        if len(s) == 1:
            return float(CN_DIGIT[s])
        return float("".join(str(CN_DIGIT[c]) for c in s))

    total = 0.0        # 已结算的大单位部分
    section = 0.0      # 当前万/亿节内累计
    digit: float | None = None
    last_unit = 0      # 本节最近用过的小单位,给「一百九 = 190」那条规则用
    saw_zero = False
    for c in s:
        if c in CN_DIGIT:
            if c in ("〇", "零"):
                saw_zero = True
                continue
            digit = CN_DIGIT[c]
        elif c in CN_SMALL_UNIT:
            section += (digit if digit is not None else 1) * CN_SMALL_UNIT[c]
            last_unit = CN_SMALL_UNIT[c]
            digit = None
        elif c in CN_BIG_UNIT:
            section += _tail(digit, last_unit, saw_zero)
            if section == 0:
                section = 1
            total += section * CN_BIG_UNIT[c]
            section, digit, last_unit, saw_zero = 0.0, None, 0, False
        else:
            return None
    section += _tail(digit, last_unit, saw_zero)
    val = total + section
    return val if val else None


def _tail(digit: float | None, last_unit: int, saw_zero: bool) -> float:
    """结尾那个光秃秃的数字该按哪一档算。

    中文口语省略末位单位:`一百九` = 190(九继承百的下一档十),`两千三` = 2300。
    但有「零」时不省略:`一百零五` = 105。
    """
    if digit is None:
        return 0.0
    if saw_zero or last_unit <= 10:
        return digit
    return digit * (last_unit // 10)


#: 时间戳 / 说话人编号 —— 版面元数据,不是内容里的数字。
#: 底档每句都带时间戳、书面版只在 turn 头带,不剔掉会造出一堆假警报
#: (`1:26:23` 会被读成 1 / 26 / 23,实测污染出 25 个「丢失」里的大半)。
NOISE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?"
                   r"|Speaker\s*\d+", re.I)


def denoise(text: str) -> str:
    return NOISE.sub(" ", text)


def arabic_values(text: str) -> set[float]:
    """阿拉伯数字(含量级单位)→ 数值集合。"""
    vals: set[float] = set()
    for m in ARABIC.finditer(denoise(text)):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        # 带量级单位时只收**乘完的值**:`1700万` 要跟 `一千七百万` 对得上,
        # 裸的 1700 不是一个独立事实,收进来就会变成假警报。
        vals.add(v * ARABIC_SCALE[m.group(2)] if m.group(2) else v)
    return vals


def cn_values(text: str) -> set[float]:
    """中文数字串 → 数值集合。"""
    vals: set[float] = set()
    for m in CN_RUN.finditer(denoise(text)):
        v = cn2num(m.group(0))
        if v is not None:
            vals.add(v)
    return vals


#: 紧跟「年」的数字。ASR 把年份读得很随意(`21年` / `1819年` / `2024 205 25年`),
#: CLEAN 规范成 `2021 年` / `2018、2019 年` 是**对的**,不是吞信息 ——
#: 实测这一类占了假警报的多数,所以移出硬闸,单独软报告。
YEARISH = re.compile(r"(\d{1,4})\s*年")


def year_values(text: str) -> set[float]:
    return {float(m.group(1)) for m in YEARISH.finditer(denoise(text))}


def source_values(text: str) -> set[float]:
    """**被考核的**数值:只取阿拉伯数字。

    为什么不把中文数字也当来源(2026-08-07 实测定):中文里 一 / 二 / 三 同时是
    普通词(一个 / 第二 / 三分之一),`CN_RUN` 会把相邻字连成「二三四五六」这种
    根本不是数的串,在真实成品上造出 16-26 个假「丢失」。ASR 输出量词绝大多数
    是阿拉伯数字,所以只考核这一侧,拿到的是高信噪比的闸门。

    同理排除紧跟「年」的数字(见 `YEARISH`)。

    **代价说明白**:底档里用中文数字表达的量(「百分之八十」)、以及年份,都不进
    硬闸。宁可少拦几个,也不能让闸门天天喊狼来了 —— 那等于没有闸门。
    """
    return arabic_values(text) - year_values(text)


def target_values(text: str) -> set[float]:
    """**用来兑账的**数值:阿拉伯 + 中文数字都认。

    这一侧故意放宽 —— 书面化把 `1700万` 写成「一千七百万」、`80%` 写成
    「百分之八十」都是合法换写,不该判成丢。
    """
    return arabic_values(text) | cn_values(text)


def strip_tags(s: str) -> str:
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s, flags=re.S | re.I)
    return htmllib.unescape(re.sub(r"<[^>]+>", " ", s))


def split_html(doc: str) -> tuple[str, str]:
    """拆渲染好的中文 reader:`<details class="raw-transcript">` 里是底档,外面是书面正文。"""
    raws = re.findall(r'<details[^>]*class="[^"]*raw-transcript[^"]*"[^>]*>(.*?)</details>',
                      doc, flags=re.S | re.I)
    if not raws:
        raise SystemExit('✗ 这个 HTML 里没有 <details class="raw-transcript">,'
                         "不是中文模式产物(英文双语走句数闸,见 verify.md)")
    clean = re.sub(r'<details[^>]*class="[^"]*raw-transcript[^"]*"[^>]*>.*?</details>',
                   " ", doc, flags=re.S | re.I)
    # `<summary>` 是版面文案(「展开逐字原稿（125 段）」),那个段数是渲染产物,
    # 不是内容里的数字 —— 不剔掉会被当成「书面版丢了 125」。
    raw_body = re.sub(r"<summary\b.*?</summary>", " ",
                      "\n".join(raws), flags=re.S | re.I)
    return strip_tags(raw_body), strip_tags(clean)


def latin_terms(text: str) -> Counter:
    return Counter(t for t in (m.lower() for m in LATIN.findall(text))
                   if t not in LATIN_STOP and len(t) >= 4)


def audit(raw: str, clean: str) -> dict:
    src_vals, out_vals = source_values(raw), target_values(clean)
    missing_vals = sorted(src_vals - out_vals)

    src_years = year_values(raw)
    missing_years = sorted(src_years - out_vals)

    src_latin = latin_terms(raw)
    clean_low = clean.lower()
    missing_latin = sorted(t for t, n in src_latin.items()
                           if n >= LATIN_MIN_HITS and t not in clean_low)

    return {
        "numeric": {"total": len(src_vals), "missing": missing_vals,
                    "ratio": len(missing_vals) / len(src_vals) if src_vals else 0.0},
        "year": {"total": len(src_years), "missing": missing_years},
        "latin": {"total": sum(1 for n in src_latin.values() if n >= LATIN_MIN_HITS),
                  "missing": missing_latin},
    }


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def _list(rows: list, fmt=str, cap: int = 40) -> None:
    for x in rows[:cap]:
        print(f"    缺 · {fmt(x)}")
    if len(rows) > cap:
        print(f"    …… 另有 {len(rows) - cap} 个")


def report(res: dict) -> int:
    n, y, l = res["numeric"], res["year"], res["latin"]
    print(f"数值(硬闸):底档 {n['total']} 个不同数值,书面版缺 {len(n['missing'])} 个"
          f"(缺失率 {n['ratio']:.3f},容忍 {NUMERIC_TOLERANCE})")
    _list(n["missing"], _fmt)

    print(f"\n年份(软报告):底档 {y['total']} 个,书面版对不上 {len(y['missing'])} 个"
          f" —— ASR 常把年份读碎(`21年` / `1819年`),CLEAN 规范化是对的,逐条扫一眼即可")
    _list(y["missing"], _fmt)

    print(f"\n拉丁专名(软报告,底档出现 ≥{LATIN_MIN_HITS} 次的):"
          f"共 {l['total']} 个,书面版缺 {len(l['missing'])} 个")
    _list(l["missing"])

    print()
    if n["ratio"] > NUMERIC_TOLERANCE:
        print(f"✗ 有 {len(n['missing'])} 个数值在书面版里对不上,逐条复核:")
        print("   · 真被吞了 → 回 CLEAN 补那一窗(书面化 ≠ 概括,数字必须保下来)")
        print("   · 底档本身是 ASR 读碎的(如「拿了大概7000」下一句才是「8千万美金」)"
              "→ 属预期,放过")
        print("   实测基线:两篇已发布的长中文成品各剩 1 条,都是后者。"
              "非空≠一定有 bug,但也别不看。")
        return 1
    if l["missing"]:
        print("✓ 数值全在。拉丁专名有缺,多半是 CLEAN 纠对了拼写 —— "
              "扫一眼上面的清单,确认不是漏掉整段。")
    else:
        print("✓ 数值与拉丁专名都无缺失")
    return 0


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", help="渲染好的中文 reader(自动拆底档 / 书面正文)")
    ap.add_argument("--raw", help="底档 / ASR 逐字稿")
    ap.add_argument("--clean", help="CLEAN 书面正文")
    a = ap.parse_args(argv)

    if a.html:
        raw, clean = split_html(open(a.html, encoding="utf-8", errors="replace").read())
    elif a.raw and a.clean:
        raw = open(a.raw, encoding="utf-8", errors="replace").read()
        clean = open(a.clean, encoding="utf-8", errors="replace").read()
    else:
        ap.error("要么给 --html,要么给 --raw 和 --clean")
        return 2

    return report(audit(raw, clean))


if __name__ == "__main__":
    raise SystemExit(_main())
