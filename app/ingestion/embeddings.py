"""Azure embeddings shared by ingestion and serving."""

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
from app.config import BackendSettings


class EmbeddingManager:
    def __init__(self, settings: BackendSettings | None = None):
        self.settings = settings or BackendSettings()
        self.model_name = self.settings.azure_openai_embedding_deployment
        if not self.model_name or not self.settings.azure_openai_endpoint:
            raise ValueError("Configure the Azure embedding endpoint and deployment")
        self.credential = None
        auth = {}
        if self.settings.azure_openai_api_key:
            auth["api_key"] = self.settings.azure_openai_api_key.get_secret_value()
        else:
            self.credential = DefaultAzureCredential(
                managed_identity_client_id=self.settings.azure_client_id
            )
            auth["azure_ad_token_provider"] = get_bearer_token_provider(
                self.credential, "https://cognitiveservices.azure.com/.default"
            )
        self.model = AzureOpenAI(
            azure_endpoint=self.settings.azure_openai_endpoint,
            api_version=self.settings.azure_openai_api_version,
            timeout=self.settings.model_timeout_seconds,
            max_retries=self.settings.model_max_retries,
            **auth,
        )

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.model.embeddings.create(model=self.model_name, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in ordered] != list(range(len(texts))):
            raise RuntimeError("Embedding response does not match the requested inputs")
        return [item.embedding for item in ordered]

    def close(self):
        self.model.close()
        if self.credential:
            self.credential.close()
