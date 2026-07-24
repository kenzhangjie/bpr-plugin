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
