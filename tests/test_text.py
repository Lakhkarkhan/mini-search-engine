import pytest

from minisearch.text import analyze, stem, tokenize


@pytest.mark.parametrize(
    "word, expected",
    [
        ("running", "run"),
        ("stopped", "stop"),
        ("falling", "fall"),
        ("queries", "query"),
        ("boxes", "box"),
        ("searches", "search"),
        ("cats", "cat"),
        ("glass", "glass"),
        ("class", "class"),
        ("bus", "bus"),
        ("sing", "sing"),  # too short to strip "ing"
        ("go", "go"),
    ],
)
def test_stem(word, expected):
    assert stem(word) == expected


def test_stem_makes_word_forms_match():
    assert stem("indexing") == stem("indexed") == stem("index")


def test_tokenize_offsets_point_into_original_text():
    text = "Hello, World!"
    tokens = tokenize(text)
    assert [t[0] for t in tokens] == ["hello", "world"]
    for token, start, end in tokens:
        assert text[start:end].lower() == token


def test_analyze_drops_stopwords_but_keeps_positions():
    # "state of the art": state=0, of=1, the=2, art=3
    assert analyze("state of the art") == [("state", 0), ("art", 3)]


def test_analyze_handles_empty_and_punctuation():
    assert analyze("") == []
    assert analyze("!!! ... ???") == []
