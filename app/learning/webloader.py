# from langchain_community.document_loaders import WebBaseLoader
from bs4 import BeautifulSoup
import requests
from langchain_core.documents import Document

def main():
    print("Hello from rag-app-foundry!")

    # loader = WebBaseLoader("https://www.bbc.com/news/world-66879428")
    # docs = loader.load()
    # print(docs[0].page_content)

    url = "https://www.bbc.com/news/world-66879428"
    response = requests.get(url)

    soup = BeautifulSoup(response.content, "html.parser")

    document = Document(
        page_content=soup.get_text(separator="\n", strip=True),
        metadata={"source": url}
    )

    print(document.page_content[:500])  # Print the first 500 characters of the document content


if __name__ == "__main__":
    main()
