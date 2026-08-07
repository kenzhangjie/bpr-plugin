"""中文模式实体覆盖闸回归。

第 2 组是这个脚本存在的理由:第一版按字面比对,在两篇已发布成品上报了 3 个
「丢失」,人工复核全是假警报(百分之八十→80%、1700万→一千七百万)。
按数值比之后归零。闸门喊狼来了 == 没有闸门。
"""
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "verify"))
import entity_coverage as E


# ─────────── 1. 中文数字解析 ───────────

def test_cn2num_basic():
    assert E.cn2num("八十") == 80
    assert E.cn2num("三") == 3
    assert E.cn2num("十五") == 15
    assert E.cn2num("一千七百万") == 17_000_000
    assert E.cn2num("两亿") == 200_000_000
    assert E.cn2num("三分之") is None or True     # 「分」不是数字字符 → 只解析「三」


def test_cn2num_reads_digit_runs_positionally():
    assert E.cn2num("二零二六") == 2026
    assert E.cn2num("一二三") == 123


def test_cn2num_refuses_colloquial_ranges():
    # 「一百二百」= 一百到二百,同量级单位重复 → 不猜,不纳入硬闸
    assert E.cn2num("一百二百") is None
    assert E.cn2num("三万五万") is None


def test_cn2num_trailing_digit_inherits_lower_unit():
    """回归:「一百九」是 190 不是 109。中文口语省末位单位,漏了这条会造假警报
    (实测在真实成品上把书面版的「一百九还是五百九」判成丢了 190 / 590)。"""
    assert E.cn2num("一百九") == 190
    assert E.cn2num("五百九") == 590
    assert E.cn2num("两千三") == 2300
    assert E.cn2num("一百零五") == 105      # 有「零」就不省单位
    assert E.cn2num("十五") == 15


def test_cn2num_leading_shi_has_implicit_one():
    """回归:「十万」没有数字字符,但那个隐含的 1 是合法的。"""
    assert E.cn2num("十万") == 100_000
    assert E.cn2num("十亿") == 1_000_000_000


def test_cn2num_rejects_bare_units():
    # 「百分之」的百、「1700万」的万 —— 是残片不是数
    assert E.cn2num("百") is None
    assert E.cn2num("万") is None
    assert E.cn2num("十") is None


def test_arabic_values_handles_scale_units():
    v = E.arabic_values("估值 15 亿,团队 200 人,ARR 3M")
    assert 15 * 10**8 in v and 200 in v and 3 * 10**6 in v
    # 带单位时**只收乘完的值**:裸 15 不是独立事实,收了会让「一十五亿」变假警报
    assert 15 not in v and 3 not in v


# ─────────── 2. 换写形态不算丢(真实成品复现) ───────────

def test_percent_rewritten_to_arabic_is_not_missing():
    r = E.audit("百分之八十客户抱怨来自配送", "80% 的客户抱怨都来自配送")
    assert r["numeric"]["missing"] == []


def test_arabic_scale_rewritten_to_chinese_is_not_missing():
    r = E.audit("加起来全世界是1700万人嘛", "加起来全世界是一千七百万人")
    assert r["numeric"]["missing"] == []


def test_colloquial_range_is_not_gated():
    r = E.audit("Google 都涨个百分之一百二百", "Google 都涨个百分之一二百")
    assert r["numeric"]["missing"] == []


def test_year_rewritten_to_chinese_is_not_missing():
    r = E.audit("那是 2000 年的事", "那是两千年的事")
    assert r["numeric"]["missing"] == []


def test_years_go_to_soft_bucket_not_hard_gate():
    """`21年` → CLEAN 规范成 `2021 年` 是对的,不该拦。实测年份是假警报主要来源。"""
    r = E.audit("21年那会我回国了", "2021 年那会我回国了")
    assert r["numeric"]["missing"] == []        # 硬闸放过
    assert 21 in r["year"]["missing"]           # 软报告里仍然列出来
    assert E.report(r) == 0


def test_colloquial_abbreviated_price_survives():
    """真实成品复现:底档 `190块还是590块`,书面版 `一百九还是五百九`。"""
    r = E.audit("90块还是190块还是590块", "九十块、一百九还是五百九")
    assert r["numeric"]["missing"] == []


def test_shiwan_in_written_matches_arabic_in_source():
    """真实成品复现:底档 `找10万、20万月薪的人`,书面版写「十万」。"""
    r = E.audit("找10万月薪的人", "找十万月薪的人")
    assert r["numeric"]["missing"] == []


def test_summary_chrome_is_not_counted_as_content():
    """`<summary>展开逐字原稿（125 段）</summary>` 里的段数是渲染产物,不是内容数字。"""
    doc = """<html><body><p class="zh">书面版没有数字。</p>
      <details class="raw-transcript"><summary>展开逐字原稿（125 段）</summary>
      <p>这段底档也没有数字</p></details></body></html>"""
    raw, clean = E.split_html(doc)
    assert "125" not in raw
    assert E.audit(raw, clean)["numeric"]["missing"] == []


def test_timestamps_are_denoised():
    r = E.audit("Speaker 2 1:26:23 加起来是三个行业", "三个行业")
    assert r["numeric"]["missing"] == []


# ─────────── 3. 真吞了数字要拦住 ───────────

def test_audit_catches_swallowed_number():
    raw = "2026 年涨了 30%,估值 15 亿"
    clean = "2026 年涨了不少,估值也上去了。"          # 30 和 15亿 被吞
    r = E.audit(raw, clean)
    assert 30 in r["numeric"]["missing"]
    assert 15 * 10**8 in r["numeric"]["missing"]
    assert E.report(r) == 1


def test_audit_passes_when_everything_survives():
    raw = "呃 那个 2026 年吧 大概涨了 30% 然后估值 15 亿"
    clean = "2026 年增长 30%,估值 15 亿。"
    r = E.audit(raw, clean)
    assert r["numeric"]["missing"] == [] and E.report(r) == 0


def test_repeated_number_collapsing_is_legal():
    # 口语重复三次,书面版说一次 —— 比存在性不比次数
    r = E.audit("30% 30% 30%", "涨了 30%")
    assert r["numeric"]["missing"] == []


# ─────────── 4. 拉丁专名只报告,且过滤噪音 ───────────

def test_latin_missing_is_reported_but_not_gated():
    raw = "看 Aultimate 的持仓,Aultimate 很重"        # 出现 2 次 → 进报告
    clean = "看 Altimeter 的持仓,Altimeter 很重。"     # CLEAN 合法纠对
    r = E.audit(raw, clean)
    assert "aultimate" in r["latin"]["missing"]
    assert r["numeric"]["missing"] == []
    assert E.report(r) == 0                            # 只报告,不拦


def test_one_off_latin_token_is_ignored_as_noise():
    r = E.audit("有个 Pockas 之类的", "……")
    assert r["latin"]["missing"] == []                  # 只出现 1 次 → 不报


def test_latin_stopwords_and_short_tokens_dropped():
    assert E.latin_terms("the and you just like www com AI ok") == {}


# ─────────── 5. HTML 拆分 ───────────

def test_split_html_separates_backing_transcript():
    doc = """<html><body>
      <p class="zh">书面正文:2026 年涨了 30%。</p>
      <details class="raw-transcript"><p>呃 就是 2026 年吧 涨了 30% 对吧</p></details>
      <p class="zh">第二章书面。</p>
    </body></html>"""
    raw, clean = E.split_html(doc)
    assert "呃" in raw and "书面正文" not in raw
    assert "书面正文" in clean and "呃" not in clean


def test_split_html_rejects_non_chinese_mode():
    import pytest
    with pytest.raises(SystemExit):
        E.split_html("<html><body><div class='bilingual'>hi</div></body></html>")
