"""Command-line interface.

    python -m minisearch index sample_docs --out index.json.gz
    python -m minisearch search index.json.gz "inverted index" -n 5
"""
import argparse
import html
import sys
import time
from pathlib import Path

from minisearch.index import InvertedIndex

EXTENSIONS = {".txt", ".md"}


def cmd_index(args) -> int:
    root = Path(args.directory)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 1
    index = InvertedIndex()
    started = time.perf_counter()
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() in EXTENSIONS and path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            index.add(path.relative_to(root).as_posix(), text, title=path.stem.replace("_", " "))
    index.save(args.out)
    stats = index.stats()
    print(f"Indexed {stats['documents']} documents ({stats['unique_terms']} unique terms) "
          f"in {time.perf_counter() - started:.2f}s -> {args.out}")
    return 0


def cmd_search(args) -> int:
    try:
        index = InvertedIndex.load(args.index)
    except FileNotFoundError:
        print(f"error: index file {args.index} not found. Build one with the 'index' command.", file=sys.stderr)
        return 1
    result = index.search(args.query, limit=args.limit)
    print(f"{result.total} result(s)\n")
    for rank, hit in enumerate(result.hits, start=1):
        snippet = html.unescape(hit.snippet.replace("<mark>", "[").replace("</mark>", "]"))
        print(f"{rank}. {hit.title or hit.id}  (score {hit.score}, id: {hit.id})")
        print(f"   {snippet}\n")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="minisearch", description="A small full-text search engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="index all .txt/.md files in a directory")
    p_index.add_argument("directory")
    p_index.add_argument("--out", default="index.json.gz")
    p_index.set_defaults(func=cmd_index)

    p_search = sub.add_parser("search", help="search a saved index")
    p_search.add_argument("index")
    p_search.add_argument("query")
    p_search.add_argument("-n", "--limit", type=int, default=5)
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
