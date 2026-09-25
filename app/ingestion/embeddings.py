"""Generate Azure embeddings for documents and queries."""

from openai import AzureOpenAI

from app.config import required_env


class EmbeddingManager:
    def __init__(self):
        self.model_name = required_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        self.model = AzureOpenAI(
            azure_endpoint=required_env("AZURE_OPENAI_ENDPOINT"),
            api_key=required_env("AZURE_OPENAI_API_KEY"),
            api_version="2024-02-01",
            timeout=60,
            max_retries=2,
        )

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.model.embeddings.create(model=self.model_name, input=texts)
        return [
            item.embedding
            for item in sorted(response.data, key=lambda item: item.index)
        ]
