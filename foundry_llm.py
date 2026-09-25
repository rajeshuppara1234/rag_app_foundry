import os
from pathlib import Path

from azure.identity import (
    DefaultAzureCredential,
    get_bearer_token_provider
)

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default"
)


llm = ChatOpenAI(
    model=os.environ["FOUNDRY_CHAT_MODEL"],
    base_url=os.environ["FOUNDRY_OPENAI_ENDPOINT"],
    api_key=token_provider
)

response = llm.invoke(
    "Explain vector embeddings in one sentence."
)

print(response.content)
