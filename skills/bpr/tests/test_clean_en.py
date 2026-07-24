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
