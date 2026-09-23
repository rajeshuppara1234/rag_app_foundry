from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import Dict, List, Any, Tuple

try:
    from app.ingestion.loader import load_all_documents
except ModuleNotFoundError:
    from loader import load_all_documents


def split_documents(
    documents: list[Document],
    chunk_size: int = 250,
    chunk_overlap: int = 100,
) -> list[Document]:
    """Split documents into smaller chunks for better RAG performance."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )

    split_docs = text_splitter.split_documents(documents)
    #print(f"\nSplit {len(documents)} documents into {len(split_docs)} chunks")

    return split_docs


def load_and_split_documents(
    pdfdirectory: str = "app/data",
    chunk_size: int = 250,
    chunk_overlap: int = 100,
) -> List[Document]:
    """Load documents from loader.py and split them into chunks."""
    documents = load_all_documents(pdfdirectory)
    return split_documents(
        documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


if __name__ == "__main__":
    final_split_docs = load_and_split_documents("app/data")

    if final_split_docs:
        chunk = final_split_docs[min(5, len(final_split_docs) - 1)]
        print("\nExample chunk")
        print(f"Chunk content: {chunk.page_content[:100]}...")
        print(f"Chunk metadata: {chunk.metadata}")
