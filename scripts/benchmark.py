"""Benchmark indexing speed and query latency against a naive linear scan.

    python scripts/benchmark.py            # 20,000 documents
    python scripts/benchmark.py 50000      # custom size
"""
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from minisearch import InvertedIndex  # noqa: E402
from minisearch.text import analyze  # noqa: E402

N_DOCS = int(sys.argv[1]) if len(sys.argv) > 1 else 20_000
WORDS_PER_DOC = 150
VOCAB_SIZE = 8_000
N_QUERIES = 100

rng = random.Random(42)
vocab = [f"word{i}" for i in range(VOCAB_SIZE)]
weights = [1 / (rank + 1) for rank in range(VOCAB_SIZE)]  # Zipf-like: a few common words, a long tail

print(f"Generating {N_DOCS:,} documents of {WORDS_PER_DOC} words...")
corpus = [" ".join(rng.choices(vocab, weights, k=WORDS_PER_DOC)) for _ in range(N_DOCS)]

index = InvertedIndex()
started = time.perf_counter()
for i, text in enumerate(corpus):
    index.add(str(i), text)
elapsed = time.perf_counter() - started
print(f"Indexed in {elapsed:.2f}s  ({N_DOCS / elapsed:,.0f} docs/s)")
print(f"Index stats: {index.stats()}")

queries = [" ".join(rng.choices(vocab, weights, k=3)) for _ in range(N_QUERIES)]

latencies = []
for q in queries:
    t = time.perf_counter()
    index.search(q, limit=10)
    latencies.append((time.perf_counter() - t) * 1000)
print(f"\nIndexed search over {N_QUERIES} queries:")
print(f"  median {statistics.median(latencies):.2f} ms | p95 {sorted(latencies)[int(0.95 * N_QUERIES)]:.2f} ms")

# Naive baseline: re-analyze and scan every document for every query.
sample = queries[:5]
naive = []
for q in sample:
    wanted = {term for term, _ in analyze(q)}
    t = time.perf_counter()
    [i for i, text in enumerate(corpus) if wanted & {term for term, _ in analyze(text)}]
    naive.append((time.perf_counter() - t) * 1000)
print(f"Naive linear scan (5 queries): median {statistics.median(naive):.0f} ms")
print(f"Speed-up: ~{statistics.median(naive) / statistics.median(latencies):,.0f}x")
