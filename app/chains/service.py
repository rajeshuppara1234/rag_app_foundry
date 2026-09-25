"""One shared, read-only knowledge base for all authenticated users."""

from contextlib import ExitStack
from app.config import Settings
from app.ingestion.embeddings import EmbeddingManager
from app.retrieval.augument_gen import AugmentGen
from app.retrieval.chroma_http import ChromaReader


class RAGService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.resources = ExitStack()
        try:
            self.embeddings = EmbeddingManager(settings)
            self.resources.callback(self.embeddings.close)
            self.generator = AugmentGen(settings)
            self.resources.callback(self.generator.close)
            self.store = ChromaReader(settings)
            self.resources.callback(self.store.close)
        except Exception:
            self.resources.close()
            raise

    def ready(self):
        return self.store.ready()

    def answer(self, question: str, top_k: int) -> dict:
        embedding = self.embeddings.generate_embeddings([question])[0]
        retrieved = self.store.retrieve(embedding, top_k)
        contexts, sources = [], []
        remaining = self.settings.max_context_chars
        for row in retrieved:
            if remaining <= 0:
                break
            content = row["content"][:remaining]
            remaining -= len(content)
            contexts.append({**row, "content": content})
            metadata = row["metadata"]
            source = str(
                metadata.get("source_file") or metadata.get("source") or "Document"
            )
            page = metadata.get("page")
            sources.append(
                {
                    "citation": len(sources) + 1,
                    "source": source.replace("\\", "/").rsplit("/", 1)[-1],
                    "page": page + 1 if type(page) is int and page >= 0 else None,
                }
            )
        return {"answer": self.generator.answer(question, contexts), "sources": sources}

    def close(self):
        self.resources.close()
