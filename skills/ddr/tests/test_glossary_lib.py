"""glossary_lib 回归 —— 核心是 2026-08-07 那个静默改错。

背景:`肖弘|20|小红,小宏,小虹` 这一行,配上无词边界的字符串替换,会把
「小红书」改成「肖弘书」、「小红帽」改成「肖弘帽」。而且改在 ASR 输出那一刻,
CLEAN 之后所有环节都以为那是原话。下面第一组测试就是这个 bug 的钉子。
"""
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "lib"))
import glossary_lib as G


def _g(tmp_path, text, protect=""):
    g = tmp_path / "glossary.txt"
    g.write_text(text, encoding="utf-8")
    p = tmp_path / "protect.txt"
    p.write_text(protect, encoding="utf-8")
    return str(g), str(p)


# ─────────── 1. 原始 bug:短 CJK 键误伤常用词 ───────────

def test_short_cjk_variant_does_not_corrupt_xiaohongshu(tmp_path):
    gp, pp = _g(tmp_path, "肖弘|20|小红,小宏,小虹\n")
    c = G.build_corrections(G.parse_glossary(gp), pp)
    for s in ["我们看小红书的增长曲线", "小红书 DAU 涨了", "戴小红帽的人", "这个小红点一直亮着"]:
        assert c.apply(s) == s, f"{s} 被改坏了 → {c.apply(s)}"


def test_short_cjk_variants_are_rejected_loudly(tmp_path):
    gp, pp = _g(tmp_path, "肖弘|20|小红,小宏,小虹\n潘乱|4|潘乐\n张涛|15|涛哥\n")
    c = G.build_corrections(G.parse_glossary(gp), pp)
    assert len(c.mappings) == 0                      # 5 个键全部拒收
    assert len(c.warnings) == 5
    assert all(w.startswith("拒收错法") for w in c.warnings)
    assert "小红" in c.warnings[0]


def test_safe_three_char_cjk_variant_still_works(tmp_path):
    gp, pp = _g(tmp_path, "高继扬|8|高季阳\n乱翻书|4|乐凡说,乱翻说\n")
    c = G.build_corrections(G.parse_glossary(gp), pp)
    assert c.apply("高季阳在乐凡说聊了") == "高继扬在乱翻书聊了"


# ─────────── 2. 保护名单层(独立于长度闸) ───────────

def test_protect_file_shields_common_word(tmp_path):
    # 错法「小明王」够 3 字过了长度闸,但它是保护词「小明王子」的子串
    gp, pp = _g(tmp_path, "王小明|5|小明王\n", protect="小明王子\n")
    c = G.build_corrections(G.parse_glossary(gp), pp)
    assert c.apply("小明王子的故事") == "小明王子的故事"
    assert c.apply("小明王说") == "王小明说"        # 不在保护词里的照旧纠


def test_glossary_terms_are_self_protecting(tmp_path):
    # 第 1 列的正确名自动进保护名单:阶跃星辰 不会被 3 字错法「阶跃星」啃掉前缀
    gp, pp = _g(tmp_path, "阶跃星辰|9|街月星辰\nX公司|5|阶跃星\n")
    c = G.build_corrections(G.parse_glossary(gp), pp)
    assert c.apply("阶跃星辰发布了") == "阶跃星辰发布了"


def test_protect_comments_and_blanks_ignored(tmp_path):
    gp, pp = _g(tmp_path, "王小明|5|小明王\n", protect="# 注释\n\n小明王子\n")
    assert "小明王子" in G.load_protected(G.parse_glossary(gp), pp)
    assert "# 注释" not in G.load_protected(G.parse_glossary(gp), pp)


# ─────────── 3. 拉丁键词边界 ───────────

def test_latin_variant_requires_word_boundary(tmp_path):
    gp, pp = _g(tmp_path, "Codex|8|Codeex\n")
    c = G.build_corrections(G.parse_glossary(gp), pp)
    assert c.apply("they ship Codeex daily") == "they ship Codex daily"
    assert c.apply("Codeexes and Codeexy") == "Codeexes and Codeexy"   # 不咬词内
    assert c.apply("preCodeex") == "preCodeex"


def test_latin_variant_with_space_still_matches(tmp_path):
    gp, pp = _g(tmp_path, "OpenAI|9|Opening Eye\n")
    c = G.build_corrections(G.parse_glossary(gp), pp)
    assert c.apply("at Opening Eye, we") == "at OpenAI, we"


def test_short_latin_variant_rejected(tmp_path):
    gp, pp = _g(tmp_path, "OpenAI|9|OAI\n")
    c = G.build_corrections(G.parse_glossary(gp), pp)
    assert c.mappings == {} and "拉丁键仅 3 字符" in c.warnings[0]


# ─────────── 4. 长键优先 / 冲突 ───────────

def test_longest_key_wins(tmp_path):
    gp, pp = _g(tmp_path, "Hockey Stick Growth|5|Hockey Sticky Gross\nXXXX|5|Hockey Stick\n")
    c = G.build_corrections(G.parse_glossary(gp), pp)
    assert c.apply("we saw Hockey Sticky Gross here") == "we saw Hockey Stick Growth here"


def test_conflicting_variant_warns_and_keeps_first(tmp_path):
    gp, pp = _g(tmp_path, "Alpha|5|Wrongword\nBeta|5|Wrongword\n")
    c = G.build_corrections(G.parse_glossary(gp), pp)
    assert c.mappings["Wrongword"] == "Alpha"
    assert any("同时映射到" in w for w in c.warnings)


def test_variant_equal_to_term_skipped(tmp_path):
    gp, pp = _g(tmp_path, "Codex|5|Codex\n")
    c = G.build_corrections(G.parse_glossary(gp), pp)
    assert c.mappings == {}


# ─────────── 5. lint / --check-glossary ───────────

def test_lint_reports_rejected_and_collisions(tmp_path):
    gp, pp = _g(tmp_path, "肖弘|20|小红\n王小明|5|小明王\n", protect="小明王子\n")
    r = G.lint(G.parse_glossary(gp), pp)
    assert any("小红" in x for x in r["rejected"])
    assert any("小明王" in x for x in r["collisions"])
    assert r["stats"]["terms"] == 2


# ─────────── 6. 飞轮:回写第 3 列(P4) ───────────

def test_append_merges_variants_into_existing_line(tmp_path):
    gp, _ = _g(tmp_path, "# 头部注释\nCodex|8\nOpenAI|9|Opening Eye\n")
    r = G.append_glossary_detail([{"term": "Codex", "seen_as": ["Codeex"]}], gp)
    assert r["added"] == 0 and r["variants_added"] == 1
    lines = pathlib.Path(gp).read_text(encoding="utf-8").split("\n")
    assert "Codex|8|Codeex" in lines
    assert "# 头部注释" in lines                      # 注释行没被挪动
    assert "OpenAI|9|Opening Eye" in lines


def test_append_new_term_with_variants(tmp_path):
    gp, _ = _g(tmp_path, "OpenAI|9\n")
    r = G.append_glossary_detail([{"term": "Legora", "seen_as": ["Lagora"]}], gp)
    assert r["added"] == 1 and r["variants_added"] == 1
    assert "Legora|5|Lagora" in pathlib.Path(gp).read_text(encoding="utf-8")


def test_append_refuses_unsafe_variant(tmp_path):
    gp, _ = _g(tmp_path, "肖弘|20\n")
    r = G.append_glossary_detail([{"term": "肖弘", "seen_as": ["小红"]}], gp)
    assert r["variants_added"] == 0
    assert any("小红" in x for x in r["rejected"])
    assert "小红" not in pathlib.Path(gp).read_text(encoding="utf-8")


def test_append_dedups_variants(tmp_path):
    gp, _ = _g(tmp_path, "Codex|8|Codeex\n")
    r = G.append_glossary_detail([{"term": "Codex", "seen_as": ["Codeex"]}], gp)
    assert r["variants_added"] == 0
    assert pathlib.Path(gp).read_text(encoding="utf-8").count("Codeex") == 1


def test_append_plain_string_list_back_compat(tmp_path):
    gp, _ = _g(tmp_path, "OpenAI|6\nClaude|7\n")
    assert G.append_glossary(["openai", "Codex", "Anthropic"], gp) == 2
    txt = pathlib.Path(gp).read_text(encoding="utf-8")
    assert "Codex|5" in txt and "Anthropic|5" in txt


def test_append_variants_become_live_mappings(tmp_path):
    """飞轮真的转起来了:回写的错法下一轮能被 build_corrections 读出来纠错。"""
    gp, pp = _g(tmp_path, "Higgsfield|8\n")
    G.append_glossary_detail([{"term": "Higgsfield", "seen_as": ["Hicksfield"]}], gp)
    c = G.build_corrections(G.parse_glossary(gp), pp)
    assert c.apply("we used Hicksfield") == "we used Higgsfield"
