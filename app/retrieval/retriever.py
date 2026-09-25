"""Retrieval for local scripts and evaluation; failures propagate to callers."""

from app.ingestion.embeddings import EmbeddingManager


class RAGRetriever:
    def __init__(self, vector_store, embedding_manager=None):
        self.vector_store = vector_store
        self.embedding_manager = embedding_manager
        self._owns_embeddings = embedding_manager is None

    def retrieve(
        self, query: str, top_k: int = 5, score_threshold: float | None = None
    ) -> list[dict]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        count = self.vector_store.collection.count()
        if count == 0:
            return []
        if self.embedding_manager is None:
            self.embedding_manager = EmbeddingManager()
        embedding = self.embedding_manager.generate_embeddings([query])[0]
        if hasattr(embedding, "tolist"):
            embedding = embedding.tolist()
        results = self.vector_store.collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )
        configuration = self.vector_store.collection.configuration or {}
        metadata = self.vector_store.collection.metadata or {}
        space = (configuration.get("hnsw") or {}).get(
            "space", metadata.get("hnsw:space", "l2")
        )
        rows = []
        for text, meta, distance, doc_id in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
            results["ids"][0],
            strict=True,
        ):
            score = (
                1 - distance
                if space in ("cosine", "ip")
                else 1 / (1 + max(0, distance))
            )
            if text and (score_threshold is None or score >= score_threshold):
                rows.append(
                    {
                        "content": text,
                        "metadata": meta or {},
                        "id": doc_id,
                        "distance": distance,
                        "similarity_score": score,
                        "rank": len(rows) + 1,
                    }
                )
        return rows

    def close(self):
        if self._owns_embeddings and self.embedding_manager is not None:
            self.embedding_manager.close()


if __name__ == "__main__":
    from app.retrieval.vector_store import VectorStore

    retriever = RAGRetriever(VectorStore())
    try:
        print(retriever.retrieve("Why not use a regular database?", top_k=3))
    finally:
        retriever.close()
