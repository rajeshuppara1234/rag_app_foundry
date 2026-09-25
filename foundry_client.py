"""Explicit factory for development scripts using the Foundry project SDK."""

import os
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


def create_project_client():
    load_dotenv()
    return AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )


if __name__ == "__main__":
    with create_project_client():
        print("Foundry project client initialized.")
