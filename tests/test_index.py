import pytest

from minisearch import InvertedIndex
from minisearch.index import make_snippet


@pytest.fixture()
def index():
    idx = InvertedIndex()
    idx.add("1", "Python is a popular programming language for data science.", "Python intro")
    idx.add("2", "Java is a programming language used for enterprise software.", "Java intro")
    idx.add("3", "Python python python snakes are reptiles, not programming.", "Snakes")
    idx.add("4", "State of the art machine learning models need lots of data.", "ML")
    idx.add("5", "The art of state management in modern web applications.", "Web")
    return idx


def ids(result):
    return [h.id for h in result.hits]


def test_basic_search_finds_matching_documents(index):
    assert set(ids(index.search("python"))) == {"1", "3"}


def test_no_match_returns_empty(index):
    result = index.search("kubernetes")
    assert result.total == 0 and result.hits == []


def test_empty_index_and_empty_query():
    assert InvertedIndex().search("anything").total == 0
    idx = InvertedIndex()
    idx.add("a", "hello world")
    assert idx.search("").total == 0
    assert idx.search("the of").total == 0


def test_higher_term_frequency_ranks_higher(index):
    # Doc 3 repeats "python" three times in a similar-length text.
    assert ids(index.search("python"))[0] == "3"


def test_rare_terms_outweigh_common_terms(index):
    # "programming" is in 3 docs; "enterprise" only in doc 2.
    assert ids(index.search("programming enterprise"))[0] == "2"


def test_shorter_documents_get_length_boost():
    idx = InvertedIndex()
    idx.add("short", "bm25 ranking")
    idx.add("long", "bm25 ranking " + "filler " * 200)
    assert ids(idx.search("bm25"))[0] == "short"


def test_matching_more_query_terms_ranks_higher(index):
    result = index.search("python data science")
    assert ids(result)[0] == "1"


def test_required_terms(index):
    assert ids(index.search("+programming +java")) == ["2"]


def test_required_term_missing_everywhere_returns_nothing(index):
    assert index.search("+python +kubernetes").total == 0


def test_excluded_terms(index):
    result = index.search("programming -python")
    assert ids(result) == ["2"]


def test_phrase_requires_adjacent_words(index):
    result = index.search('"machine learning"')
    assert ids(result) == ["4"]
    assert index.search('"learning machine"').total == 0


def test_phrase_respects_stopword_gaps(index):
    # Doc 4 has "state of the art"; doc 5 has "art of state" (reversed order).
    assert ids(index.search('"state of the art"')) == ["4"]


def test_excluded_phrase(index):
    result = index.search('programming -"popular programming"')
    assert "1" not in ids(result)
    assert "2" in ids(result)


def test_stemming_matches_word_forms():
    idx = InvertedIndex()
    idx.add("a", "She was running quickly")
    # "running", "runs" and "run" all reduce to the same stem
    assert idx.search("run").total == 1
    assert idx.search("runs").total == 1
    assert idx.search("running").total == 1


def test_pagination(index):
    full = index.search("programming", limit=10)
    page1 = index.search("programming", limit=1, offset=0)
    page2 = index.search("programming", limit=1, offset=1)
    assert page1.total == page2.total == full.total == 3
    assert ids(page1) + ids(page2) == ids(full)[:2]


def test_update_replaces_old_content(index):
    index.add("2", "Rust is a systems language.", "Rust intro")
    assert "2" not in ids(index.search("java"))
    assert ids(index.search("rust")) == ["2"]
    assert len(index) == 5


def test_remove_cleans_up_postings(index):
    assert index.remove("2") is True
    assert index.remove("2") is False
    assert index.search("enterprise").total == 0
    assert "enterprise" not in index.postings
    assert len(index) == 4


def test_removing_everything_resets_state(index):
    for doc_id in list(index.docs):
        index.remove(doc_id)
    assert len(index) == 0
    assert index.postings == {}
    assert index.total_length == 0


def test_stats(index):
    stats = index.stats()
    assert stats["documents"] == 5
    assert stats["unique_terms"] > 10
    assert stats["average_document_length"] > 0


def test_save_and_load_roundtrip(index, tmp_path):
    path = tmp_path / "index.json.gz"
    index.save(str(path))
    loaded = InvertedIndex.load(str(path))
    assert len(loaded) == len(index)
    for query in ["python", '"machine learning"', "programming -java"]:
        before, after = index.search(query), loaded.search(query)
        assert ids(before) == ids(after)
        assert [h.score for h in before.hits] == [h.score for h in after.hits]


def test_save_leaves_no_temp_files(index, tmp_path):
    index.save(str(tmp_path / "index.json.gz"))
    assert [p.name for p in tmp_path.iterdir()] == ["index.json.gz"]


# ---------- snippets ----------


def test_snippet_highlights_matches():
    snippet = make_snippet("Search engines rank pages by relevance.", {"rank"})
    assert "<mark>rank</mark>" in snippet


def test_snippet_escapes_html():
    snippet = make_snippet("<script>alert(1)</script> python rocks", {"python"})
    assert "<script>" not in snippet
    assert "&lt;script&gt;" in snippet
    assert "<mark>python</mark>" in snippet


def test_snippet_without_match_falls_back_to_start():
    text = "word " * 100
    snippet = make_snippet(text, {"missing"})
    assert snippet.startswith("word") and snippet.endswith("…")


def test_snippet_centers_on_late_match():
    text = ("filler " * 100) + "needle appears here " + ("filler " * 100)
    snippet = make_snippet(text, {"needle"})
    assert "<mark>needle</mark>" in snippet
    assert snippet.startswith("…") and snippet.endswith("…")
    assert len(snippet) < 300
