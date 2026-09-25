"""Offline checks for the query endpoint and its existing RAG path."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
import pytest

from app.main import app
from app.retrieval.augument_gen import AugmentGen
from app.retrieval.retriever import RAGRetriever


def test_docs_open_without_initializing_external_services():
    with patch("app.api.routes.get_rag_components") as components:
        with TestClient(app) as client:
            assert client.get("/docs").status_code == 200
            schema = client.get("/openapi.json").json()
    assert "/query" in schema["paths"]
    components.assert_not_called()


@pytest.mark.parametrize(
    "body", [{}, {"query": ""}, {"query": "  "}, {"query": None}, {"query": 12}]
)
def test_invalid_query_is_rejected_without_model_calls(body):
    with (
        patch("app.api.routes.get_rag_components") as components,
        TestClient(app) as client,
    ):
        assert client.post("/query", json=body).status_code == 422
    components.assert_not_called()


def test_query_runs_rag_and_preserves_braces():
    retriever = Mock()
    retriever.retrieve.return_value = [
        {"content": 'JSON example: {"name": "LangChain"}'}
    ]
    generator = AugmentGen.__new__(AugmentGen)
    generator.llm = Mock()
    generator.llm.invoke.return_value = AIMessage(content="The name is LangChain.")
    with (
        patch("app.api.routes.get_rag_components", return_value=(retriever, generator)),
        TestClient(app) as client,
    ):
        response = client.post("/query", json={"query": " Explain {name}. "})
    assert response.status_code == 200
    assert response.json() == {"answer": "The name is LangChain."}
    retriever.retrieve.assert_called_once_with("Explain {name}.", top_k=5)
    prompt = generator.llm.invoke.call_args.args[0][1][1]
    assert '{"name": "LangChain"}' in prompt
    assert "{name}" in prompt


def test_service_failure_returns_503_without_internal_details():
    with (
        patch(
            "app.api.routes.get_rag_components",
            side_effect=ConnectionError("private upstream details"),
        ),
        TestClient(app) as client,
    ):
        response = client.post("/query", json={"query": "test"})
    assert response.status_code == 503
    assert "private upstream details" not in response.text


def test_no_context_skips_generation():
    retriever, model = Mock(), Mock()
    retriever.retrieve.return_value = []
    generator = AugmentGen.__new__(AugmentGen)
    assert generator.rag_simple("test", retriever, model) == "I don't know."
    model.invoke.assert_not_called()


def test_empty_model_answer_is_an_error():
    retriever, model = Mock(), Mock()
    retriever.retrieve.return_value = [{"content": "context"}]
    model.invoke.return_value = AIMessage(content="")
    with pytest.raises(RuntimeError, match="empty answer"):
        AugmentGen.__new__(AugmentGen).rag_simple("test", retriever, model)


def test_small_l2_collection_is_not_filtered_as_cosine():
    collection = Mock()
    collection.count.return_value = 1
    collection.configuration = {"hnsw": {"space": "l2"}}
    collection.metadata = None
    collection.query.return_value = {
        "documents": [["context"]],
        "metadatas": [[None]],
        "distances": [[2.0]],
        "ids": [["doc-1"]],
    }
    embeddings = Mock()
    embeddings.generate_embeddings.return_value = [[1.0, 0.0]]
    retriever = RAGRetriever(SimpleNamespace(collection=collection), embeddings)
    result = retriever.retrieve("test")
    assert collection.query.call_args.kwargs["n_results"] == 1
    assert result[0]["content"] == "context"
    assert result[0]["similarity_score"] == pytest.approx(1 / 3)


def test_retrieval_errors_propagate_to_api():
    collection = Mock()
    collection.count.side_effect = ConnectionError("database unavailable")
    retriever = RAGRetriever(SimpleNamespace(collection=collection), Mock())
    with pytest.raises(ConnectionError):
        retriever.retrieve("test")
