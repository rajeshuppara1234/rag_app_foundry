"""Manual, billable Foundry smoke test. Run explicitly, never during test discovery."""

import os
from foundry_client import create_project_client


def main():
    with create_project_client() as project:
        with project.get_openai_client() as client:
            response = client.responses.create(
                model=os.environ["FOUNDRY_CHAT_MODEL"],
                input="Explain RAG in two sentences.",
            )
            print(response.output_text)


if __name__ == "__main__":
    main()
