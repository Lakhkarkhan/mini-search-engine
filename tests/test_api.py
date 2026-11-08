import pytest
from fastapi.testclient import TestClient

from minisearch import InvertedIndex
from minisearch.api import create_app


@pytest.fixture()
def client():
    return TestClient(create_app(InvertedIndex()))


def put(client, doc_id, text, title=""):
    return client.put(f"/documents/{doc_id}", json={"title": title, "text": text})


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_then_update_document(client):
    assert put(client, "a", "first version").json()["status"] == "created"
    assert put(client, "a", "second version").json()["status"] == "updated"
    assert client.get("/documents/a").json()["text"] == "second version"


def test_get_missing_document(client):
    assert client.get("/documents/nope").status_code == 404


def test_delete_document(client):
    put(client, "a", "hello world")
    assert client.delete("/documents/a").status_code == 204
    assert client.delete("/documents/a").status_code == 404
    assert client.get("/search", params={"q": "hello"}).json()["total"] == 0


def test_search_returns_ranked_hits_with_snippets(client):
    put(client, "a", "Search engines use an inverted index.", "Index")
    put(client, "b", "Cooking pasta takes ten minutes.", "Pasta")
    body = client.get("/search", params={"q": "inverted index"}).json()
    assert body["total"] == 1
    hit = body["hits"][0]
    assert hit["id"] == "a" and hit["title"] == "Index"
    assert "<mark>" in hit["snippet"]
    assert body["took_ms"] >= 0


def test_search_operators_via_api(client):
    put(client, "a", "python web framework")
    put(client, "b", "python data science")
    body = client.get("/search", params={"q": "python -web"}).json()
    assert [h["id"] for h in body["hits"]] == ["b"]
    body = client.get("/search", params={"q": '"data science"'}).json()
    assert [h["id"] for h in body["hits"]] == ["b"]


def test_search_pagination(client):
    for i in range(5):
        put(client, f"d{i}", "common word here")
    body = client.get("/search", params={"q": "common", "limit": 2, "offset": 2}).json()
    assert body["total"] == 5 and len(body["hits"]) == 2


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "x", "limit": 0}, {"q": "x", "limit": 101}, {"q": "x", "offset": -1}])
def test_search_validation(client, params):
    assert client.get("/search", params=params).status_code == 422


def test_bulk_index(client):
    docs = [{"id": f"d{i}", "title": "", "text": f"document number {i} about cats"} for i in range(3)]
    body = client.post("/documents/bulk", json={"documents": docs}).json()
    assert body == {"indexed": 3, "total_documents": 3}
    assert client.get("/stats").json()["documents"] == 3


def test_bulk_index_rejects_empty_list(client):
    assert client.post("/documents/bulk", json={"documents": []}).status_code == 422


def test_empty_text_rejected(client):
    assert put(client, "a", "").status_code == 422


def test_save_requires_index_path(client):
    assert client.post("/save").status_code == 400


def test_save_and_reload_with_lifespan(tmp_path):
    path = str(tmp_path / "idx.json.gz")
    with TestClient(create_app(index_path=path)) as c:
        put(c, "a", "persistent data survives restarts")
        assert c.post("/save").json() == {"saved_to": path}
    # a brand-new app loads the file on startup
    with TestClient(create_app(index_path=path)) as c:
        assert c.get("/search", params={"q": "persistent"}).json()["total"] == 1


def test_index_saved_on_shutdown(tmp_path):
    path = str(tmp_path / "idx.json.gz")
    with TestClient(create_app(index_path=path)) as c:
        put(c, "a", "saved on shutdown")
    with TestClient(create_app(index_path=path)) as c:
        assert c.get("/documents/a").status_code == 200
