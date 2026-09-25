"""Chroma SDK access for trusted ingestion and local evaluation."""

from hashlib import sha256
import json
import logging
import math
from urllib.parse import urlsplit

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_core.documents import Document

from app.config import BackendSettings

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(
        self,
        collection_name: str | None = None,
        *,
        create_collection: bool = False,
        settings: BackendSettings | None = None,
    ):
        self.settings = settings or BackendSettings()
        self.collection_name = collection_name or self.settings.chroma_collection
        parsed = urlsplit(self.settings.chroma_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Set CHROMA_URL to your Chroma server URL")
        headers = {}
        if self.settings.chroma_auth_token:
            headers[self.settings.chroma_auth_header] = (
                self.settings.chroma_auth_token.get_secret_value()
            )
        self.client = chromadb.HttpClient(
            host=self.settings.chroma_url,
            port=parsed.port or (443 if parsed.scheme == "https" else 80),
            ssl=parsed.scheme == "https",
            headers=headers,
            tenant=self.settings.chroma_tenant,
            database=self.settings.chroma_database,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        if create_collection:
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=None,
                configuration={"hnsw": {"space": "cosine"}},
            )
        else:
            self.collection = self.client.get_collection(
                name=self.collection_name, embedding_function=None
            )

    def add_embeddings(self, documents: list[Document], embeddings):
        if len(documents) != len(embeddings):
            raise ValueError(
                "The number of documents must match the number of embeddings."
            )
        if not documents:
            return
        ids, metadatas, texts, vectors = [], [], [], []
        dimension = None
        for i, (doc, vector) in enumerate(zip(documents, embeddings, strict=True)):
            vector = [float(value) for value in vector]
            if not vector or not all(math.isfinite(value) for value in vector):
                raise ValueError("Embeddings must be nonempty finite vectors")
            dimension = dimension or len(vector)
            if len(vector) != dimension:
                raise ValueError("All embeddings must have the same dimension")
            metadata = dict(doc.metadata)
            metadata.update(doc_index=i, content_length=len(doc.page_content))
            identity = json.dumps(
                [doc.page_content, doc.metadata], sort_keys=True, default=str
            )
            ids.append(sha256(identity.encode()).hexdigest())
            metadatas.append(metadata)
            texts.append(doc.page_content)
            vectors.append(vector)
        # Stable IDs make retries safe for the same chunks. Changed files need
        # a versioned collection and an explicit cutover to remove old chunks.
        self.collection.upsert(
            ids=ids, metadatas=metadatas, documents=texts, embeddings=vectors
        )


if __name__ == "__main__":
    import argparse
    from app.ingestion.embeddings import EmbeddingManager
    from app.ingestion.splitter import load_and_split_documents

    parser = argparse.ArgumentParser(
        description="Trusted, offline ingestion into Chroma"
    )
    parser.add_argument("--data-dir", default="app/data")
    parser.add_argument("--create-collection", action="store_true")
    args = parser.parse_args()
    store = VectorStore(create_collection=args.create_collection)
    manager = EmbeddingManager()
    try:
        documents = load_and_split_documents(args.data_dir)
        if not documents:
            raise SystemExit("No PDF chunks were loaded; nothing was written.")
        for offset in range(0, len(documents), 32):
            batch = documents[offset : offset + 32]
            vectors = manager.generate_embeddings([doc.page_content for doc in batch])
            store.add_embeddings(batch, vectors)
        print(f"Collection contains {store.collection.count()} chunks.")
    finally:
        manager.close()
