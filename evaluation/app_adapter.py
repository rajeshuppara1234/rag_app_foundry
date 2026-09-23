"""Capture the existing RAG pipeline's real contexts without changing app code."""

from pathlib import Path
from types import SimpleNamespace


def to_context(result):
    metadata = result.get("metadata") or {}
    source = metadata.get("source_file") or metadata.get("source")
    page = metadata.get("page")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Retrieved document is missing source/source_file metadata")
    if type(page) is not int or page < 0:
        raise ValueError(
            "Retrieved document needs PyPDFLoader's zero-based integer page metadata"
        )
    content = result.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Retrieved document has empty content")
    return {
        "content": content,
        "source": source.replace("\\", "/").rsplit("/", 1)[-1],
        "page": page + 1,
    }


class RecordingRetriever:
    def __init__(self, retriever):
        self.retriever = retriever
        self.contexts = []
        self.calls = 0

    def retrieve(self, query, top_k=5):
        self.calls += 1
        results = self.retriever.retrieve(query, top_k=top_k)
        self.contexts = [to_context(row) for row in results]
        return results


class AppAdapter:
    def __init__(self, persist_directory, collection_name, retrieval_only=False):
        # Avoid VectorStore(): it creates missing collections as a side effect.
        import chromadb
        from app.retrieval.retriever import RAGRetriever

        directory = Path(persist_directory)
        if not (directory / "chroma.sqlite3").is_file():
            raise ValueError(
                f"No existing Chroma database at {directory}. Ingest rag.pdf first."
            )
        self.client = chromadb.PersistentClient(path=str(directory))
        collection = self.client.get_collection(collection_name)
        if collection.count() == 0:
            raise ValueError(
                "The existing Chroma collection is empty; ingest rag.pdf first"
            )
        # Check the full collection in bounded batches, not only the first result.
        for offset in range(0, collection.count(), 1000):
            batch = collection.get(limit=1000, offset=offset, include=["metadatas"])
            for metadata in batch["metadatas"]:
                context = to_context(
                    {"metadata": metadata, "content": "metadata validation"}
                )
                if context["source"] != "rag.pdf" or context["page"] > 20:
                    raise ValueError(
                        "Use a collection containing only the 20-page rag.pdf for this evaluation"
                    )
        self.retriever = RAGRetriever(SimpleNamespace(collection=collection))
        self.retrieval_only = retrieval_only
        self.generator = None
        self.settings = {
            "collection": collection_name,
            "persist_directory": str(directory.resolve()),
            "collection_count": collection.count(),
            "collection_metadata": collection.metadata,
            "retriever": "app.retrieval.retriever.RAGRetriever",
            "score_threshold": 0.0,
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "mode": "retrieval" if retrieval_only else "rag",
        }
        if not retrieval_only:
            from app.retrieval.augument_gen import AugmentGen

            self.generator = AugmentGen()
            self.settings.update(
                {
                    "generator": "app.retrieval.augument_gen.AugmentGen.rag_simple",
                    "model": self.generator.llm.model_name,
                    "temperature": self.generator.llm.temperature,
                    "max_tokens": self.generator.llm.max_tokens,
                }
            )

    def predict(self, question, top_k):
        recorder = RecordingRetriever(self.retriever)
        answer = None
        if self.retrieval_only:
            recorder.retrieve(question, top_k=top_k)
        else:
            answer = self.generator.rag_simple(
                question, recorder, self.generator.llm, top_k=top_k
            )
            if not isinstance(answer, str):
                raise ValueError(
                    "Expected a string answer from the existing rag_simple method"
                )
        if recorder.calls != 1:
            raise ValueError(
                "Expected exactly one retrieval call; update the adapter if the app changes"
            )
        return {"answer": answer, "abstained": None, "contexts": recorder.contexts}
