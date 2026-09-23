import numpy as np
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import uuid
from pathlib import Path
import sys
from typing import Dict, List, Any, Tuple
from sklearn.metrics.pairwise import cosine_similarity
from langchain_core.documents import Document

from app.ingestion.embeddings import EmbeddingManager
from app.ingestion.splitter import load_and_split_documents

class VectorStore:
    def __init__(self, collection_name: str = "pdf_documents", 
                 persist_directory: str = "app/data/vector_store"):
        self.collection_name = collection_name
        self.collection = None
        self.persist_directory = persist_directory
        self.client = None
        self.initialize_vector_store()
        #self.client = chromadb.Client(Settings(chroma_db_impl="duckdb+parquet", persist_directory="./chroma_db"))
        
    
    def initialize_vector_store(self):
        """Initialize the Chroma vector store."""
        try:
            # create a persistent directory for the vector store if it doesn't exist
            print(f"Persist directory: {self.persist_directory}")
            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
            # self.client = chromadb.PersistentClient(path=self.persist_directory)

            self.client = chromadb.HttpClient(
                host="chroma-db.happymeadow-76a7f72e.southindia.azurecontainerapps.io",
                port=443,
                ssl=True)

            print(self.client.heartbeat())

            # get or create the collection for storing embeddings
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "Collection for storing PDF document embeddings"}
            )
            print(f"Initialized vector store with collection: {self.collection_name}")
            print(f"Existing collections: {self.collection.count()}")
        except Exception as e:
            print(f"Error initializing vector store: {e}")
            raise

    def add_embeddings(self, documents: List[Document], embeddings: List[List[float] | np.ndarray]):
        """Add embeddings and their corresponding documents to the vector store.
        
        Args:
            documents (List[Document]): A list of Document objects to be added to the vector store
            embeddings (List[List[float] | np.ndarray]): Embeddings as float lists or NumPy arrays, one per document.
        
        """
        try:
            if len(documents) != len(embeddings):
                raise ValueError("The number of documents must match the number of embeddings.")

            print(f"Adding {len(documents)} documents to the vector store.")
            
            ids = []
            metadatas = []
            documents_text = []
            embeddings_list = []

            for i, (doc, emb) in enumerate(zip(documents, embeddings)):
                doc_id = f"doc_{uuid.uuid4().hex[:8]}_{i}"  # Generate a unique ID for each document
                ids.append(doc_id)

                #prepare metadata and text for storage
                metadata = dict(doc.metadata)  # Ensure metadata is a dictionary
                metadata['doc_index'] = i  # Add an index to the metadata for reference
                metadata['content_length'] = len(doc.page_content)  # Add content length to metadata
                metadatas.append(metadata)

                #Document Content and Embeddings
                documents_text.append(doc.page_content)
                embeddings_list.append(emb.tolist() if isinstance(emb, np.ndarray) else emb)

            try:
                self.collection.add(
                    ids=ids,
                    metadatas=metadatas,
                    documents=documents_text,
                    embeddings=embeddings_list
                )
                print(f"Successfully added {len(documents)} documents to the vector store.")
                print(f"Total documents in collection '{self.collection_name}': {self.collection.count()}")
            except Exception as e:
                print(f"Error adding embeddings to vector store: {e}")
                raise

        except Exception as e:
            print(f"Error adding embeddings to vector store: {e}")
            raise

if __name__ == "__main__":
    vector_store = VectorStore()
    embedding_manager = EmbeddingManager()
    final_split_docs = load_and_split_documents()
    generated_embeddings = embedding_manager.generate_embeddings([doc.page_content for doc in final_split_docs])

    vector_store.add_embeddings(final_split_docs, generated_embeddings)

    print(f"New collections: {vector_store.collection.count()}")
    # print("Generated embeddings:")
    # for i, emb in enumerate(generated_embeddings)[:1]:  # Print only the first 2 for brevity
    #     print(f"Text: {[doc.page_content for doc in final_split_docs][i]}")
    #     print(f"Embedding: {emb}\n")

    
