from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader
from pathlib import Path


def process_all_pdfs(pdfdirectory: str = "app/data") -> list[Document]:
    """Process all PDF files in the given directory."""
    all_documents = []
    pdf_dir = Path(pdfdirectory)

    pdf_files = list(pdf_dir.glob("*.pdf"))

    #print(f"list of pdf files {pdf_files}")

    for pdf_file in pdf_files:
        print(f"\nProcessing file: {pdf_file}")
        try:
            loader = PyPDFLoader(str(pdf_file))
            documents = loader.load()

            for doc in documents:
                doc.metadata["source_file"] = pdf_file.name
                doc.metadata["file_type"] = "pdf"

            all_documents.extend(documents)
            print(f"Loaded {len(documents)} pages")
        except Exception as e:
            print(f"Error: {e}")

    #print(f"\nTotal documents loaded: {len(all_documents)}")
    return all_documents


def load_all_documents(pdfdirectory: str = "app/data") -> list[Document]:
    """Load all documents supported by the ingestion loader."""
    return process_all_pdfs(pdfdirectory)


# if __name__ == "__main__":
#     documents = process_all_pdfs("app/data")