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
from app.retrieval.vector_store import VectorStore


class RAGRetriever:
    def __init__(self, vector_store):
        self.vector_store = vector_store

    def retrieve(self, query: str, top_k: int = 5, score_threshold: float = 0.0) -> List[Dict[str, Any]]:
        """Retrieve the top_k most relevant documents for the given query."""
        try:
            # Generate embedding for the query
            embedding_manager = EmbeddingManager()
            query_embedding = embedding_manager.generate_embeddings([query])[0]

            # Retrieve documents from the vector store
            results = self.vector_store.collection.query(
                query_embeddings=[
                    query_embedding.tolist()
                    if isinstance(query_embedding, np.ndarray)
                    else query_embedding
                ],
                n_results=top_k,
            )

            retrieved_docs = []

            print(f"Retrieved {len(results['documents'][0]) if results['documents'] and results['documents'][0] else 0} documents for query: '{query}'")

            for doc in results['documents'][0]:
                print(f"\n\n{doc}")

            if results['documents'] and results['documents'][0]:
                documents = results['documents'][0]
                metadatas = results['metadatas'][0]
                distances = results['distances'][0]
                ids = results['ids'][0]

                for i, (doc, metadata, distance, doc_id) in enumerate(zip(documents, metadatas, distances, ids)):
                    #convert distance to similarity score (assuming distance is cosine distance)
                    similarity_score = 1 - distance  # Convert cosine distance to similarity score

                    print(f"Similarity score for document {i + 1}: {similarity_score:.4f}, Distance: {distance:.4f}, ID: {doc_id}")
                    if similarity_score >= score_threshold:
                        retrieved_docs.append({
                            "content": doc,
                            "metadata": metadata,
                            "similarity_score": similarity_score,
                            "id": doc_id,
                            "distance": distance,
                            'rank': i + 1
                        })

                    # print(f"{retrieved_docs[0] if retrieved_docs else 'No document retrieved above threshold'}")

            return retrieved_docs
            
        except Exception as e:
            print(f"Error during retrieval: {e}")
            return []

if __name__ == "__main__":
    # Example usage of RAGRetriever
    vector_store = VectorStore()
    retriever = RAGRetriever(vector_store)

    query = "Why Not Use a Regular Database?"
    top_k = 3
    retrieved_documents = retriever.retrieve(query, top_k)

    print(f"Retrieved {len(retrieved_documents)} documents for query: '{query}'")
   # print(f"Retrieved documents: {retrieved_documents[0].content if retrieved_documents else 'No documents retrieved'}")
    # for i, doc in enumerate(retrieved_documents):
    #     print(f"\nDocument {i + 1}:")
    #     print(f"Content: {doc.page_content[:500]}...")  # Print first 500 characters
    #     print(f"Metadata: {doc.metadata}")
