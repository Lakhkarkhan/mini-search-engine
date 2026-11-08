"""REST API around the search index."""
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
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

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    @app.get("/stats", tags=["meta"])
    def stats(request: Request):
        return get_index(request).stats()

    @app.put("/documents/{doc_id}", tags=["documents"])
    def upsert_document(doc_id: str, doc: DocumentIn, request: Request):
        index = get_index(request)
        existed = doc_id in index
        index.add(doc_id, doc.text, doc.title)
        return {"id": doc_id, "status": "updated" if existed else "created"}

    @app.post("/documents/bulk", tags=["documents"])
    def bulk_index(payload: BulkIn, request: Request):
        index = get_index(request)
        for doc in payload.documents:
            index.add(doc.id, doc.text, doc.title)
        return {"indexed": len(payload.documents), "total_documents": len(index)}

    @app.get("/documents/{doc_id}", tags=["documents"])
    def get_document(doc_id: str, request: Request):
        doc = get_index(request).docs.get(doc_id)
        if doc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
        return {"id": doc_id, "title": doc.title, "text": doc.text}

    @app.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["documents"])
    def delete_document(doc_id: str, request: Request):
        if not get_index(request).remove(doc_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
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


app = create_app(index_path=os.getenv("INDEX_PATH"))
