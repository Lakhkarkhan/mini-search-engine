"""REST API around the search index."""
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from minisearch.index import InvertedIndex


class DocumentIn(BaseModel):
    title: str = Field(default="", max_length=500)
    text: str = Field(min_length=1, max_length=1_000_000)


class BulkDocument(DocumentIn):
    id: str = Field(min_length=1, max_length=200)


class BulkIn(BaseModel):
    documents: list[BulkDocument] = Field(min_length=1, max_length=1000)


class HitOut(BaseModel):
    id: str
    title: str
    score: float
    snippet: str = Field(description="HTML-safe excerpt; matches are wrapped in <mark>")


class SearchOut(BaseModel):
    query: str
    total: int
    limit: int
    offset: int
    took_ms: float
    hits: list[HitOut]


def create_app(index: InvertedIndex | None = None, index_path: str | None = None) -> FastAPI:
    idx = index if index is not None else InvertedIndex()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if index_path and os.path.exists(index_path):
            app.state.index = InvertedIndex.load(index_path)
        yield
        if index_path:
            app.state.index.save(index_path)

    app = FastAPI(
        title="Mini Search Engine",
        description="Full-text search with an inverted index and BM25 ranking, built from scratch.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.index = idx
    app.state.index_path = index_path

    def get_index(request: Request) -> InvertedIndex:
        return request.app.state.index

    def maybe_save(request: Request):
        path = request.app.state.index_path
        if path:
            try:
                get_index(request).save(path)
            except Exception:
                pass

    @app.get("/", include_in_schema=False)
    def web_ui():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    @app.get("/stats", tags=["meta"])
    def stats(request: Request):
        s = get_index(request).stats()
        s["index_path"] = request.app.state.index_path
        return s

    @app.get("/terms", tags=["meta"])
    def terms(
        request: Request,
        prefix: str = Query(default="", max_length=100),
        limit: int = Query(default=50, ge=1, le=500),
    ):
        index = get_index(request)
        with index._lock:
            p = prefix.lower().strip()
            matching = [
                {"term": term, "docs_count": len(postings)}
                for term, postings in index.postings.items()
                if not p or term.startswith(p)
            ]
            matching.sort(key=lambda x: (-x["docs_count"], x["term"]))
            return {"total": len(matching), "terms": matching[:limit]}

    @app.get("/export", tags=["meta"])
    def export_documents(request: Request):
        index = get_index(request)
        with index._lock:
            docs = [
                {"id": k, "title": v.title, "text": v.text, "length": v.length}
                for k, v in index.docs.items()
            ]
            return {"total": len(docs), "documents": docs}

    @app.get("/documents", tags=["documents"])
    def list_documents(
        request: Request,
        limit: int = Query(default=50, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        q: str | None = Query(default=None),
    ):
        index = get_index(request)
        with index._lock:
            items = []
            for doc_id, doc in index.docs.items():
                if q:
                    q_lower = q.lower()
                    if (
                        q_lower not in doc_id.lower()
                        and q_lower not in doc.title.lower()
                        and q_lower not in doc.text.lower()
                    ):
                        continue
                items.append({
                    "id": doc_id,
                    "title": doc.title,
                    "length": doc.length,
                    "preview": doc.text[:160] + ("…" if len(doc.text) > 160 else ""),
                })
            total = len(items)
            page = items[offset : offset + limit]
            return {"total": total, "limit": limit, "offset": offset, "documents": page}

    @app.delete("/documents", tags=["documents"])
    def clear_documents(request: Request):
        index = get_index(request)
        with index._lock:
            index.docs.clear()
            index.postings.clear()
            index.total_length = 0
        maybe_save(request)
        return {"cleared": True, "total_documents": 0}

    @app.post("/documents/samples", tags=["documents"])
    def load_samples(request: Request):
        index = get_index(request)
        sample_dir = Path(__file__).resolve().parent.parent / "sample_docs"
        loaded = 0
        if sample_dir.is_dir():
            for path in sorted(sample_dir.rglob("*")):
                if path.suffix.lower() in {".txt", ".md"} and path.is_file():
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    title = path.stem.replace("_", " ").title()
                    index.add(path.name, text, title=title)
                    loaded += 1
        if loaded == 0:
            samples = [
                ("inverted-index", "The Inverted Index", "An inverted index maps every word to the documents that contain it. A search engine looks up the query words and reads only those short lists, instead of scanning every document."),
                ("ranking-bm25", "Ranking with BM25", "BM25 scores how relevant a document is. Rare words count more, repeated words help with diminishing returns, and long documents are not unfairly favoured."),
                ("phrase-search", "Phrase Search", "Positional indexes remember where each word appears, so an exact phrase like machine learning only matches when the words sit side by side."),
                ("pytest-basics", "Testing with pytest", "Automated tests catch bugs before users do. Fixtures provide reusable setup and continuous integration runs the suite on every push."),
            ]
            for doc_id, title, text in samples:
                index.add(doc_id, text, title)
            loaded = len(samples)
        maybe_save(request)
        return {"loaded": loaded, "total_documents": len(index)}

    @app.put("/documents/{doc_id}", tags=["documents"])
    def upsert_document(doc_id: str, doc: DocumentIn, request: Request):
        index = get_index(request)
        existed = doc_id in index
        index.add(doc_id, doc.text, doc.title)
        maybe_save(request)
        return {"id": doc_id, "status": "updated" if existed else "created"}

    @app.post("/documents/bulk", tags=["documents"])
    def bulk_index(payload: BulkIn, request: Request):
        index = get_index(request)
        for doc in payload.documents:
            index.add(doc.id, doc.text, doc.title)
        maybe_save(request)
        return {"indexed": len(payload.documents), "total_documents": len(index)}

    @app.get("/documents/{doc_id}", tags=["documents"])
    def get_document(doc_id: str, request: Request):
        doc = get_index(request).docs.get(doc_id)
        if doc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
        return {
            "id": doc_id,
            "title": doc.title,
            "text": doc.text,
            "length": doc.length,
            "terms": doc.terms,
        }

    @app.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["documents"])
    def delete_document(doc_id: str, request: Request):
        if not get_index(request).remove(doc_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
        maybe_save(request)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/search", response_model=SearchOut, tags=["search"])
    def search(
        request: Request,
        q: str = Query(min_length=1, description='Supports +required, -excluded and "exact phrases"'),
        limit: int = Query(default=10, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ):
        started = time.perf_counter()
        result = get_index(request).search(q, limit=limit, offset=offset)
        took = (time.perf_counter() - started) * 1000
        return SearchOut(
            query=q,
            total=result.total,
            limit=limit,
            offset=offset,
            took_ms=round(took, 3),
            hits=[HitOut(id=h.id, title=h.title, score=h.score, snippet=h.snippet) for h in result.hits],
        )

    @app.post("/save", tags=["meta"])
    def save(request: Request):
        path = request.app.state.index_path
        if not path:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No INDEX_PATH configured")
        get_index(request).save(path)
        return {"saved_to": path}

    return app


default_index_path = os.getenv("INDEX_PATH")
if not default_index_path and os.path.exists("index.json.gz"):
    default_index_path = "index.json.gz"

app = create_app(index_path=default_index_path)
