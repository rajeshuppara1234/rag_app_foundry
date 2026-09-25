import json
from types import SimpleNamespace
from unittest.mock import Mock

import chromadb
import httpx
import numpy as np
import pytest
from chromadb.config import Settings as ChromaSettings
from langchain_core.documents import Document

from app.chains.service import RAGService
from app.ingestion.embeddings import EmbeddingManager
from app.retrieval.augument_gen import AugmentGen
from app.retrieval.chroma_http import ChromaReader
from app.retrieval.retriever import RAGRetriever
from app.retrieval.vector_store import VectorStore


def test_embeddings_are_ordered_by_input_index():
    manager = EmbeddingManager.__new__(EmbeddingManager)
    manager.model_name = "embed"
    manager.model = Mock()
    manager.model.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(index=1, embedding=[0.0, 1.0]),
            SimpleNamespace(index=0, embedding=[1.0, 0.0]),
        ]
    )
    assert manager.generate_embeddings(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert manager.generate_embeddings([]) == []
    with pytest.raises(RuntimeError):
        manager.generate_embeddings(["one"])


def test_ingestion_accepts_lists_and_arrays_without_duplicate_retries():
    client = chromadb.EphemeralClient(
        settings=ChromaSettings(anonymized_telemetry=False)
    )
    collection = client.create_collection(
        "test_prod_ingestion", embedding_function=None
    )
    store = VectorStore.__new__(VectorStore)
    store.collection = collection
    docs = [
        Document(page_content="first", metadata={"source": "a.pdf"}),
        Document(page_content="second", metadata={"source": "b.pdf"}),
    ]
    vectors = [[1.0, 0.0], [0.0, 1.0]]
    try:
        store.add_embeddings(docs, vectors)
        store.add_embeddings(docs, np.array(vectors))
        assert collection.count() == 2
        manager = Mock()
        manager.generate_embeddings.return_value = [vectors[0]]
        rows = RAGRetriever(store, manager).retrieve("first", top_k=10)
        assert rows[0]["content"] == "first"
        assert rows[0]["similarity_score"] == 1
        assert (
            len(rows) == 2
        )  # L2 distances > 1 are not dropped by a false cosine assumption.
        assert docs[0].metadata == {"source": "a.pdf"}
        for bad in ([vectors[0]], [[1, float("nan")], [1, 0]], [[1, 2], [1]]):
            with pytest.raises(ValueError):
                store.add_embeddings(docs, bad)
        assert collection.count() == 2
    finally:
        client.delete_collection("test_prod_ingestion")


def test_chroma_reader_uses_existing_collection_and_never_writes(settings):
    seen = []

    def handle(request):
        seen.append((request.method, request.url.path))
        assert request.url.path.startswith(
            "/api/v2/tenants/default_tenant/databases/default_database/collections/"
        )
        if request.url.path.endswith("/pdf_documents"):
            return httpx.Response(200, json={"id": "collection-id"})
        if request.url.path.endswith("/count"):
            return httpx.Response(200, json=1)
        assert request.url.path.endswith("/collection-id/query")
        assert json.loads(request.content)["n_results"] == 1
        return httpx.Response(
            200,
            json={
                "ids": [["id"]],
                "documents": [["text"]],
                "metadatas": [[None]],
                "distances": [[0.2]],
            },
        )

    with httpx.Client(
        base_url=settings.chroma_url, transport=httpx.MockTransport(handle)
    ) as client:
        store = ChromaReader(settings, client)
        assert store.ready()
        assert store.retrieve([1.0, 0.0], 5)[0]["metadata"] == {}
    assert all(method == "GET" or path.endswith("/query") for method, path in seen)


def test_chroma_errors_propagate(settings):
    with httpx.Client(
        base_url=settings.chroma_url,
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            ChromaReader(settings, client).retrieve([1], 1)


def test_generator_preserves_braces_and_separates_instructions():
    generator = AugmentGen.__new__(AugmentGen)
    generator.llm = Mock()
    generator.llm.invoke.return_value = SimpleNamespace(content="answer [1]")
    assert (
        generator.answer("Explain {value}", [{"content": 'JSON: {"key": 1}'}])
        == "answer [1]"
    )
    messages = generator.llm.invoke.call_args.args[0]
    assert messages[0][0] == "system"
    assert '{"key": 1}' in messages[1][1]
    generator.llm.reset_mock()
    assert "don't know" in generator.answer("question", [])
    generator.llm.invoke.assert_not_called()


def test_service_limits_context_and_hides_local_source_paths(settings):
    service = RAGService.__new__(RAGService)
    service.settings = settings.model_copy(update={"max_context_chars": 5})
    service.embeddings = Mock()
    service.embeddings.generate_embeddings.return_value = [[1.0]]
    service.store = Mock()
    service.store.retrieve.return_value = [
        {
            "id": "one",
            "content": "longer text",
            "metadata": {"source": r"D:\private\guide.pdf", "page": 0},
        }
    ]
    service.generator = Mock()
    service.generator.answer.return_value = "answer"
    result = service.answer("question", 5)
    assert result["sources"] == [{"citation": 1, "source": "guide.pdf", "page": 1}]
    assert service.generator.answer.call_args.args[1][0]["content"] == "longe"
