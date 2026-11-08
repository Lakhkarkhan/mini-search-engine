"""An in-memory inverted index with BM25 ranking."""
import gzip
import html
import json
import math
import os
import tempfile
from dataclasses import dataclass
from threading import RLock

from minisearch.query import Phrase, parse_query
from minisearch.text import STOPWORDS, analyze, stem, tokenize


@dataclass
class Document:
    title: str
    text: str
    length: int  # number of indexed terms, used for BM25 length normalisation
    terms: list[str]  # unique terms, so removal doesn't need a full scan


@dataclass
class Hit:
    id: str
    title: str
    score: float
    snippet: str


@dataclass
class SearchResult:
    total: int
    hits: list[Hit]


class InvertedIndex:
    """Maps each term to the documents (and positions) where it appears."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: dict[str, Document] = {}
        self.postings: dict[str, dict[str, list[int]]] = {}
        self.total_length = 0
        self._lock = RLock()

    def __len__(self) -> int:
        return len(self.docs)

    def __contains__(self, doc_id: str) -> bool:
        return doc_id in self.docs

    # ---------- writing ----------

    def add(self, doc_id: str, text: str, title: str = "") -> None:
        """Add a document, replacing any existing one with the same id."""
        with self._lock:
            if doc_id in self.docs:
                self._remove(doc_id)

            by_term: dict[str, list[int]] = {}
            analyzed = analyze(f"{title}\n{text}")
            for term, position in analyzed:
                by_term.setdefault(term, []).append(position)

            for term, positions in by_term.items():
                self.postings.setdefault(term, {})[doc_id] = positions

            self.docs[doc_id] = Document(title, text, len(analyzed), list(by_term))
            self.total_length += len(analyzed)

    def remove(self, doc_id: str) -> bool:
        with self._lock:
            if doc_id not in self.docs:
                return False
            self._remove(doc_id)
            return True

    def _remove(self, doc_id: str) -> None:
        doc = self.docs.pop(doc_id)
        for term in doc.terms:
            posting = self.postings[term]
            del posting[doc_id]
            if not posting:
                del self.postings[term]
        self.total_length -= doc.length

    # ---------- searching ----------

    def search(self, query: str, limit: int = 10, offset: int = 0) -> SearchResult:
        parsed = parse_query(query)
        with self._lock:
            if parsed.is_empty or not self.docs:
                return SearchResult(0, [])

            candidates = self._candidates(parsed)
            candidates = {d for d in candidates if all(self._has_phrase(d, p) for p in parsed.phrases)}
            if parsed.not_phrases:
                candidates = {d for d in candidates if not any(self._has_phrase(d, p) for p in parsed.not_phrases)}

            scores = self._score(candidates, parsed.scoring_terms)
            ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
            page = ranked[offset : offset + limit]

            highlight = set(parsed.scoring_terms)
            hits = [
                Hit(doc_id, self.docs[doc_id].title, round(score, 4),
                    make_snippet(self.docs[doc_id].text, highlight))
                for doc_id, score in page
            ]
            return SearchResult(len(ranked), hits)

    def _candidates(self, parsed) -> set[str]:
        required = list(parsed.must) + [t for phrase in parsed.phrases for t, _ in phrase]
        if required:
            # Intersect, starting with the rarest term to keep the work small.
            lists = sorted((self.postings.get(t, {}) for t in set(required)), key=len)
            result = set(lists[0])
            for posting in lists[1:]:
                result &= posting.keys()
                if not result:
                    break
        else:
            result = set()
            for term in parsed.should:
                result.update(self.postings.get(term, {}))

        for term in parsed.must_not:
            result -= self.postings.get(term, {}).keys()
        return result

    def _score(self, candidates: set[str], terms: list[str]) -> dict[str, float]:
        n = len(self.docs)
        avg_len = self.total_length / n if n else 0.0
        scores = dict.fromkeys(candidates, 0.0)
        for term in terms:
            posting = self.postings.get(term)
            if not posting:
                continue
            df = len(posting)
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            # Loop over whichever side is smaller.
            if len(candidates) < len(posting):
                matching = [d for d in candidates if d in posting]
            else:
                matching = [d for d in posting if d in candidates]
            for doc_id in matching:
                tf = len(posting[doc_id])
                norm = 1 - self.b + self.b * (self.docs[doc_id].length / avg_len if avg_len else 1)
                scores[doc_id] += idf * tf * (self.k1 + 1) / (tf + self.k1 * norm)
        return scores

    def _has_phrase(self, doc_id: str, phrase: Phrase) -> bool:
        starts = self.postings.get(phrase[0][0], {}).get(doc_id)
        if not starts:
            return False
        rest = []
        for term, offset in phrase[1:]:
            positions = self.postings.get(term, {}).get(doc_id)
            if not positions:
                return False
            rest.append((set(positions), offset))
        return any(all((start + offset) in positions for positions, offset in rest) for start in starts)

    # ---------- info ----------

    def stats(self) -> dict:
        n = len(self.docs)
        return {
            "documents": n,
            "unique_terms": len(self.postings),
            "total_postings": sum(len(p) for p in self.postings.values()),
            "average_document_length": round(self.total_length / n, 2) if n else 0.0,
        }

    # ---------- persistence ----------

    def save(self, path: str) -> None:
        """Write the index to a gzipped JSON file (atomically)."""
        with self._lock:
            payload = {
                "version": 1,
                "k1": self.k1,
                "b": self.b,
                "docs": {i: {"title": d.title, "text": d.text} for i, d in self.docs.items()},
            }
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb") as f:
                f.write(json.dumps(payload).encode("utf-8"))
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    @classmethod
    def load(cls, path: str) -> "InvertedIndex":
        """Load a saved index. Postings are rebuilt from the stored documents."""
        with gzip.open(path, "rb") as f:
            payload = json.loads(f.read().decode("utf-8"))
        index = cls(k1=payload["k1"], b=payload["b"])
        for doc_id, doc in payload["docs"].items():
            index.add(doc_id, doc["text"], doc["title"])
        return index


def make_snippet(text: str, terms: set[str], width: int = 180) -> str:
    """Return a short HTML-safe excerpt with matching words wrapped in <mark>."""
    tokens = tokenize(text)
    matches = [(s, e) for tok, s, e in tokens if tok not in STOPWORDS and stem(tok) in terms]

    if not matches:
        excerpt = text[:width].strip()
        return html.escape(excerpt) + ("…" if len(text) > width else "")

    start = max(0, matches[0][0] - width // 3)
    start = text.rfind(" ", 0, start) + 1 if start > 0 else 0
    end = min(len(text), start + width)
    next_space = text.find(" ", end)
    if next_space != -1 and next_space - end < 20:
        end = next_space

    pieces, cursor = [], start
    for s, e in matches:
        if s < start or e > end:
            continue
        pieces.append(html.escape(text[cursor:s]))
        pieces.append(f"<mark>{html.escape(text[s:e])}</mark>")
        cursor = e
    pieces.append(html.escape(text[cursor:end]))

    body = "".join(pieces).strip()
    return ("…" if start > 0 else "") + body + ("…" if end < len(text) else "")
