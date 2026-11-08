from pathlib import Path

from minisearch.__main__ import main

SAMPLES = Path(__file__).resolve().parent.parent / "sample_docs"


def test_index_then_search(tmp_path, capsys):
    out = str(tmp_path / "idx.json.gz")
    assert main(["index", str(SAMPLES), "--out", out]) == 0
    assert "Indexed 4 documents" in capsys.readouterr().out

    assert main(["search", out, "BM25 ranking"]) == 0
    text = capsys.readouterr().out
    assert "ranking_with_bm25.md" in text
    assert "[" in text  # highlighted match


def test_search_missing_index(tmp_path, capsys):
    assert main(["search", str(tmp_path / "nope.json.gz"), "x"]) == 1
    assert "not found" in capsys.readouterr().err


def test_index_missing_directory(tmp_path, capsys):
    assert main(["index", str(tmp_path / "nope"), "--out", str(tmp_path / "i.gz")]) == 1
