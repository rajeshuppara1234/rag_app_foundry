"""Read-only Chroma v2 REST adapter with bounded HTTP waits.

The installed Chroma SDK uses httpx timeout=None. Serving uses the small read
surface here; the separate ingestion command uses the SDK for writes.
"""

from urllib.parse import quote
import httpx
from app.config import BackendSettings


class ChromaReader:
    def __init__(self, settings: BackendSettings, client: httpx.Client | None = None):
        self.settings = settings
        headers = {}
        if settings.chroma_auth_token:
            headers[settings.chroma_auth_header] = (
                settings.chroma_auth_token.get_secret_value()
            )
        self.client = client or httpx.Client(
            base_url=settings.chroma_url.rstrip("/") + "/",
            headers=headers,
            timeout=httpx.Timeout(settings.chroma_timeout_seconds, connect=5),
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        )
        self.path = (
            f"api/v2/tenants/{quote(settings.chroma_tenant, safe='')}/databases/"
            f"{quote(settings.chroma_database, safe='')}/collections"
        )

    def _get(self, path):
        response = self.client.get(path)
        response.raise_for_status()
        return response.json()

    def _collection(self):
        return self._get(
            f"{self.path}/{quote(self.settings.chroma_collection, safe='')}"
        )

    def ready(self) -> bool:
        collection = self._collection()
        return self._get(f"{self.path}/{quote(collection['id'], safe='')}/count") > 0

    def retrieve(self, embedding: list[float], top_k: int) -> list[dict]:
        collection = self._collection()
        path = f"{self.path}/{quote(collection['id'], safe='')}"
        count = self._get(path + "/count")
        if count == 0:
            return []
        response = self.client.post(
            path + "/query",
            json={
                "query_embeddings": [embedding],
                "n_results": min(top_k, count),
                "include": ["documents", "metadatas", "distances"],
            },
        )
        response.raise_for_status()
        data = response.json()
        rows = []
        for doc_id, text, metadata, distance in zip(
            data["ids"][0],
            data["documents"][0],
            data["metadatas"][0],
            data["distances"][0],
            strict=True,
        ):
            if not text or (
                self.settings.max_distance is not None
                and distance > self.settings.max_distance
            ):
                continue
            rows.append(
                {
                    "id": doc_id,
                    "content": text,
                    "metadata": metadata or {},
                    "distance": distance,
                }
            )
        return rows

    def close(self):
        self.client.close()
