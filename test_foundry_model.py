import os
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

project = AIProjectClient(
    endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

client = project.get_openai_client()

response = client.responses.create(
    model=os.environ["FOUNDRY_CHAT_MODEL"],
    input="Explain RAG in two sentences."
)

print(response.output_text)
