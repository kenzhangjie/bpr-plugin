from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts" / "prep"))
import clean_en as ce


def test_parse_blocks_splits_on_marker_and_unescapes():
    raw = "90% use Codex. &gt;&gt; Yeah. &gt;&gt;   That's true."
    assert ce.parse_blocks(raw) == ["90% use Codex.", "Yeah.", "That's true."]


def test_parse_blocks_drops_empty():
    assert ce.parse_blocks(">> >>  >> hi") == ["hi"]


def test_split_windows_chunks_by_size():
    blocks = [str(i) for i in range(53)]
    w = ce.split_windows(blocks, size=25)
    assert [len(x) for x in w] == [25, 25, 3]


def test_apply_correct_table_longest_key_first():
    m = {"Hockey Stick": "X", "Hockey Sticky Gross": "Hockey Stick Growth"}
    assert ce.apply_correct_table("we saw Hockey Sticky Gross here",
                                  m) == "we saw Hockey Stick Growth here"


def test_apply_correct_table_bilingual():
    m = {"Opening Eye": "OpenAI", "克洛蔻": "Claude"}
    assert ce.apply_correct_table("克洛蔻 vs Opening Eye", m) == "Claude vs OpenAI"


def test_apply_correct_table_noop_when_no_match():
    assert ce.apply_correct_table("nothing here", {"X": "Y"}) == "nothing here"


def test_word_coverage_full():
    assert ce.word_coverage("OpenAI makes Codex", "OpenAI makes Codex") == 1.0


def test_word_coverage_detects_drop():
    # 输出丢了一整句 → 覆盖明显 < 1
    cov = ce.word_coverage("a b c d e f g h i j", "a b c d e")
    assert cov == 0.5


def test_word_coverage_ignores_case_and_punct():
    assert ce.word_coverage("Hello, world!", "hello world") == 1.0


def test_append_glossary_dedups_and_appends(tmp_path):
    g = tmp_path / "glossary.txt"
    g.write_text("OpenAI|6\nClaude|7\n", encoding="utf-8")
    added = ce.append_glossary(["openai", "Codex", "Anthropic"], str(g))
    assert added == 2  # openai 已存在(大小写不敏感),Codex/Anthropic 新增
    lines = g.read_text(encoding="utf-8").splitlines()
    assert "OpenAI|6" in lines and "Claude|7" in lines
    assert "Codex|5" in lines and "Anthropic|5" in lines


def test_append_glossary_creates_file(tmp_path):
    g = tmp_path / "new.txt"
    added = ce.append_glossary(["Vercel"], str(g))
    assert added == 1
    assert g.read_text(encoding="utf-8").strip() == "Vercel|5"


def test_append_glossary_handles_missing_trailing_newline(tmp_path):
    g = tmp_path / "glossary.txt"
    # Write without trailing newline — tests the corruption bug
    g.write_bytes(b"OpenAI|6\nClaude|7")
    added = ce.append_glossary(["Codex"], str(g))
    assert added == 1
    lines = g.read_text(encoding="utf-8").splitlines()
    assert "Claude|7" in lines and "Codex|5" in lines
    # Regression: if missing newline bug exists, we'd see "Claude|7Codex|5" as one line


def test_finalize_applies_table_and_reports_coverage():
    turns = [{"speaker": "Lenny", "sents": ["Opening Eye ships Codeex."]},
             {"speaker": "Andrew", "sents": ["Yeah, Codeex is great."]}]
    raw = "OpenAI ships Codex. >> Yeah, Codex is great."
    m = {"Opening Eye": "OpenAI", "Codeex": "Codex"}
    r = ce.finalize(turns, raw, m)
    assert r["turns"][0]["sents"][0] == "OpenAI ships Codex."
    assert r["turns"][1]["sents"][0] == "Yeah, Codex is great."
    assert r["ok"] is True and r["coverage"] >= 0.98


def test_finalize_flags_dropped_content():
    turns = [{"speaker": "Lenny", "sents": ["only one sentence kept"]}]
    raw = ("only one sentence kept >> a whole second turn that the agent "
           "dropped entirely with many distinct words here")
    r = ce.finalize(turns, raw, {})
    assert r["ok"] is False and r["coverage"] < 0.98


def test_parse_glossary_three_columns(tmp_path):
    g = tmp_path / "glossary.txt"
    g.write_text("OpenAI|9|Opening Eye\n"
                 "Codex|8|Codeex\n"
                 "Higgsfield|4|Hicksfield,Hixfield\n"
                 "PlainTerm\n"
                 "WeightOnly|6\n"
                 "# comment line\n"
                 "\n", encoding="utf-8")
    e = ce.parse_glossary(str(g))
    assert ("OpenAI", "9", ["Opening Eye"]) in e
    assert ("Higgsfield", "4", ["Hicksfield", "Hixfield"]) in e
    assert ("PlainTerm", "", []) in e
    assert ("WeightOnly", "6", []) in e
    assert len(e) == 5  # 注释行和空行被丢掉


def test_parse_glossary_missing_file_returns_empty():
    assert ce.parse_glossary("/definitely/not/here.txt") == []


def test_glossary_mappings_builds_variant_to_term():
    e = [("OpenAI", "9", ["Opening Eye"]), ("Higgsfield", "4", ["Hicksfield", "Hixfield"])]
    assert ce.glossary_mappings(e) == {"Opening Eye": "OpenAI",
                                       "Hicksfield": "Higgsfield",
                                       "Hixfield": "Higgsfield"}


def test_glossary_mappings_feed_finalize_end_to_end(tmp_path):
    # 回归 2026-08-01:correct_table.json 已删,映射必须能从 glossary 第 3 列构出来。
    g = tmp_path / "glossary.txt"
    g.write_text("OpenAI|9|Opening Eye\nCodex|8|Codeex\n", encoding="utf-8")
    m = ce.glossary_mappings(ce.parse_glossary(str(g)))
    turns = [{"speaker": "Sam", "sents": ["Opening Eye ships Codeex."]}]
    r = ce.finalize(turns, "OpenAI ships Codex.", m)
    assert r["turns"][0]["sents"][0] == "OpenAI ships Codex."


def test_scan_glossary_finds_terms_and_seen_misspellings():
    e = [("OpenAI", "9", ["Opening Eye"]),
         ("Codex", "8", ["Codeex"]),
         ("Higgsfield", "4", ["Hicksfield"]),
         ("Pi", "9", [])]
    hits = ce.scan_glossary("we use OpenAI and Codeex daily", e)
    by = {h["term"]: h for h in hits}
    assert set(by) == {"OpenAI", "Codex"}          # Higgsfield 没出现;Pi 太短被跳过
    assert by["OpenAI"]["seen_in_source"] == []    # 正确拼写命中,没见到错法
    assert by["Codex"]["seen_in_source"] == ["Codeex"]  # 只见到错法 → 必须点名


def test_scan_glossary_is_case_insensitive():
    e = [("OpenAI", "9", [])]
    assert ce.scan_glossary("openai rocks", e)[0]["term"] == "OpenAI"


def test_finalize_per_window_localizes_the_dropped_window():
    """回归 2026-08-07:全局 coverage 说不出「哪一窗」,硬规则就执行不了。"""
    windows = ["alpha bravo charlie delta echo",
               "foxtrot golf hotel india juliett",     # ← 这一窗整个被丢
               "kilo lima mike november oscar"]
    raw = " >> ".join(windows)
    turns = [{"speaker": "A", "sents": [windows[0]]},
             {"speaker": "B", "sents": [windows[2]]}]
    r = ce.finalize(turns, raw, {}, windows=windows)
    assert r["ok"] is False
    assert r["worst_window"]["index"] == 1
    assert [w["ok"] for w in r["windows"]] == [True, False, True]


def test_finalize_per_window_all_ok_when_nothing_dropped():
    windows = ["alpha bravo charlie", "delta echo foxtrot"]
    turns = [{"speaker": "A", "sents": windows}]
    r = ce.finalize(turns, " >> ".join(windows), {}, windows=windows)
    assert r["ok"] is True and all(w["ok"] for w in r["windows"])
    assert r["worst_window"]["index"] in (0, 1)


def test_finalize_without_windows_keeps_old_shape():
    turns = [{"speaker": "A", "sents": ["one two three"]}]
    r = ce.finalize(turns, "one two three", {})
    assert r["windows"] == [] and r["worst_window"] is None and r["ok"] is True


def test_added_ratio_catches_insertion():
    # 覆盖率满分但凭空多出一整句 → added_ratio 抓得到
    assert ce.word_coverage("a b c d", "a b c d e f g h") == 1.0
    assert ce.added_ratio("a b c d", "a b c d e f g h") == 1.0
    assert ce.added_ratio("a b c d", "a b c d") == 0.0


def test_finalize_reports_added_ratio():
    turns = [{"speaker": "A", "sents": ["one two three plus a fabricated tail here"]}]
    r = ce.finalize(turns, "one two three", {})
    assert r["added_ratio"] > ce.ADDED_WARN
    assert r["ok"] is True          # 报告项,不拦


def test_finalize_proper_noun_correction_does_not_lower_coverage():
    # Regression: proper noun corrections should not artificially lower coverage.
    # The sub-agent has already corrected the turns output ("OpenAI", "Ambrosino", "Codex"),
    # but raw source has uncorrected variants ("Opening Eye", "Ambercino", "Codeex").
    # Before fix: word_coverage(raw_uncorrected, joined_corrected) would falsely report coverage < 0.98
    # After fix: canonicalize raw through mappings so proper-noun variants collapse before comparison.
    turns = [
        {"speaker": "Lenny", "sents": ["90% at OpenAI use Codex."]},
        {"speaker": "Andrew", "sents": ["Yeah, Ambrosino leads Codex."]}
    ]
    raw = "90% at Opening Eye use Codeex. >> Yeah, Ambercino leads Codeex."
    mappings = {"Opening Eye": "OpenAI", "Codeex": "Codex", "Ambercino": "Ambrosino"}
    r = ce.finalize(turns, raw, mappings)
    assert r["ok"] is True and r["coverage"] >= 0.98

def test_norm_words_drops_bracketed_caption_markers():
    """`[music]` / `[ __ ]` 是字幕噪声标记,不参与覆盖率计数。"""
    assert ce.norm_words("we [music] shipped [ __ ] it") == ["we", "shipped", "it"]


def test_finalize_noise_markers_do_not_lower_coverage():
    """回归:PREP 明令删掉 `[music]`,照做不该掉分。

    修复前:源侧 `[music]` 被算成一个词 "music",子代理按规矩删掉它,覆盖率就往下掉。
    一个 151 词的片头删 4 个 `[music]` = 0.974,卡在 0.98 闸下,而正文一个字没丢。
    """
    raw = "[music] we shipped it [music] and it worked [music]"
    turns = [{"speaker": "A", "sents": ["we shipped it", "and it worked"]}]
    r = ce.finalize(turns, raw, {})
    assert r["coverage"] == 1.0 and r["ok"] is True


def test_finalize_per_window_catches_drop_despite_shared_vocabulary():
    """回归:逐窗覆盖必须比**同位输出片段**,不能比整份输出。

    上面那个 `localizes_the_dropped_window` 用的是互不重叠的词表(alpha/bravo vs
    foxtrot/golf),所以比整篇也能发现丢失 —— 真实稿子不长那样。

    真实形态是中间态:一段话的用词,**近邻里没有、远处别的段落里有**。这里照这个
    形态造 —— 每窗 = 大量共享虚词 + 一块专题词,专题词块 i 同时出现在第 i 窗和第
    i+4 窗。丢掉第 4 窗:它的专题词在第 0 窗仍在,比整篇时全部命中、分数接近 1
    (旧实现放行);比同位片段时,近邻第 3/5 窗没有这些词,立刻掉下来。

    窗必须是**真实尺度**(远大于 WINDOW_MARGIN_WORDS),否则局部片段会被余量撑成
    整篇,测试退化成永远为真 —— 第一版(22 词的窗)就踩了这个坑。
    """
    filler = ("the fund manager is going to look at that data and say it does not "
              "move the number so we will not pay for it this quarter").split()
    windows = []
    for i in range(8):
        block = " ".join([f"topic{i % 4}alpha topic{i % 4}beta topic{i % 4}gamma"] * 30)
        windows.append(" ".join(filler * 16) + " " + block)
    assert len(windows[0].split()) > 3 * ce.WINDOW_MARGIN_WORDS, "窗要远大于余量才有意义"
    raw = " >> ".join(windows)
    kept = [w for i, w in enumerate(windows) if i != 4]      # ← 第 5 窗整个丢掉
    turns = [{"speaker": "A", "sents": [w]} for w in kept]
    r = ce.finalize(turns, raw, {}, windows=windows)
    assert r["ok"] is False, "共享词表下的丢窗必须被抓到"
    assert r["worst_window"]["index"] == 4, f"应指向第 4 窗,实际 {r['worst_window']}"
