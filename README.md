# Mini Search Engine

A full-text search engine built from scratch in Python: an **inverted index**, **BM25 ranking**, **phrase and boolean queries**, highlighted snippets, persistence to disk, a **REST API** and a command-line tool. There is no search library behind it. The indexing and ranking code is all in this repo.

![CI](https://github.com/Lakhkarkhan/mini-search-engine/actions/workflows/ci.yml/badge.svg)

## What it does

- **Inverted index with word positions**, so exact phrase queries work
- **BM25 ranking**: rare words count more, repeated words help with diminishing returns, and long documents are not unfairly favored
- **Query syntax**: `+required`, `-excluded`, and `"exact phrases"`
- **Stopword-aware phrases**: `"state of the art"` matches even though "of" and "the" are not indexed
- **Light stemmer**: `running`, `runs` and `run` all match each other
- **Snippets** with `<mark>` highlights around the matching words (HTML-escaped, so safe to display)
- **Live updates**: add, replace and delete documents without rebuilding the index
- **Thread-safe** reads and writes
- **Persistence**: gzipped JSON, written atomically so a crash cannot corrupt the file
- **REST API** (FastAPI with automatic Swagger docs), **CLI**, **Docker** and **GitHub Actions CI**
- **69 tests**, about 98% coverage

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Git Bash on Windows: source .venv/Scripts/activate
pip install -r requirements-dev.txt
```

### Command line

```bash
python -m minisearch index sample_docs --out index.json.gz
python -m minisearch search index.json.gz "inverted index"
python -m minisearch search index.json.gz '"exact phrase" -java'
```

### REST API

```bash
uvicorn minisearch.api:app --reload
```

Open **http://localhost:8000/docs** to try every endpoint in the browser.

```bash
# Add documents
curl -X POST localhost:8000/documents/bulk -H "Content-Type: application/json" -d '{
  "documents": [
    {"id": "1", "title": "BM25", "text": "BM25 ranks documents by relevance."},
    {"id": "2", "title": "Pasta", "text": "Boil pasta for ten minutes."}
  ]}'

# Search
curl "localhost:8000/search?q=ranking+relevance"
```

### Docker

```bash
docker compose up --build
```

The index is stored in a Docker volume. It is saved on shutdown and reloaded on start.

## Query syntax

| Query | Meaning |
|---|---|
| `python tutorial` | documents matching either word, best matches first |
| `+python +tutorial` | both words are required |
| `python -java` | exclude documents containing "java" |
| `"machine learning"` | the exact phrase |
| `-"machine learning"` | exclude documents containing the phrase |

## API

| Method | Endpoint | Description |
|---|---|---|
| PUT | `/documents/{id}` | Add or replace a document (`title`, `text`) |
| POST | `/documents/bulk` | Index up to 1,000 documents at once |
| GET | `/documents/{id}` | Fetch a document |
| DELETE | `/documents/{id}` | Remove a document |
| GET | `/search?q=&limit=&offset=` | Ranked search with pagination |
| GET | `/stats` | Index size and statistics |
| POST | `/save` | Write the index to disk (needs `INDEX_PATH`) |
| GET | `/health` | Health check |

Set the `INDEX_PATH` environment variable to load an index on startup and save it on shutdown.

## How it works

**1. Analysis.** Text is split into words, lowercased, stripped of stopwords and stemmed. Each word keeps its original position, even when stopwords are dropped, which is what makes phrase queries accurate.

**2. Inverted index.** Instead of storing "document → words", the index stores "word → documents (and positions)". Looking up a query means reading a few short lists instead of scanning every document.

```
"index"  -> { doc1: [2, 9],  doc7: [0] }
"search" -> { doc1: [4],     doc3: [1, 5], doc7: [3] }
```

**3. Candidate selection.** Required terms and phrases are intersected, starting with the rarest term so the work stays small. Excluded terms are subtracted.

**4. BM25 ranking.** Each matching term contributes:

```
idf(term) * tf * (k1 + 1) / (tf + k1 * (1 - b + b * doc_length / avg_length))
```

`idf` rewards rare terms, `tf` is how often the term appears in the document, `k1` (1.5) controls how quickly repeats stop helping, and `b` (0.75) controls the length penalty.

**5. Snippets.** The excerpt is centered on the first match, the text is HTML-escaped, and every matching word in the window is wrapped in `<mark>`.

## Benchmark

```bash
python scripts/benchmark.py 20000
```

On a 20,000-document synthetic corpus (150 words each), indexed search ran about 45 times faster than rescanning every document. Run it yourself to see numbers for your machine.

## Design decisions and limitations

- **Everything is in memory.** Fast, but the index must fit in RAM. Saving writes the documents, and loading rebuilds the postings, which keeps the file format simple and robust.
- **The stemmer is rule-based and small.** It handles common English endings but is not a full Porter stemmer, so some irregular words will not match.
- **Single process.** The lock makes one process safe, but running several API workers would give each its own separate index.
- **Possible next steps:** field boosting (title vs. body), fuzzy matching for typos, a compressed on-disk index format, and incremental index segments.

## Project structure

```
minisearch/
  text.py      # tokenizer, stopwords, stemmer
  query.py     # query parser (+, -, "phrases")
  index.py     # inverted index, BM25, snippets, persistence
  api.py       # FastAPI application
  __main__.py  # command-line interface
tests/         # pytest suite
scripts/       # benchmark
sample_docs/   # small corpus for trying the CLI
```

## Running the tests

```bash
pytest --cov=minisearch --cov-report=term-missing
```

## License

MIT
