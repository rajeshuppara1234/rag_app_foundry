import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

ROOT_DIR = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT_DIR / ".env")  # Load environment variables from project root
    openai_api_key = os.getenv("OPENAI_API_KEY")

    llm = ChatOpenAI(
        model_name="gpt-4o-mini",
        openai_api_key=openai_api_key,
        temperature=0.7,
        max_tokens=150
    )
    response = llm.invoke("Suggest a good name for a company that makes colorful socks.")
    #print("API Key:", openai_api_key)  # Print the API key to verify it's loaded correctly
    print("Response:", response.content)


if __name__ == "__main__":
    main()
