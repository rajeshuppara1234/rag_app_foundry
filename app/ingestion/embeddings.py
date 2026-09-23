import os
import numpy as np
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import uuid
from pathlib import Path
from typing import Dict, List, Any, Tuple
from sklearn.metrics.pairwise import cosine_similarity
from langchain_core.documents import Document
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

try:
    from app.ingestion.splitter import load_and_split_documents
except ModuleNotFoundError:
    from splitter import load_and_split_documents

class EmbeddingManager:
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        cache_folder: str = "app/models/sentence-transformers",
    ):
        self.model_name = None
        self.cache_folder = cache_folder
        self.model = None
        self.load_LLM_model()

    def load_LLM_model(self):
        """Load the sentence transformer embedding model."""
        try:
            Path(self.cache_folder).mkdir(parents=True, exist_ok=True)
            # self.model = SentenceTransformer(
            #     self.model_name,
            #     cache_folder=self.cache_folder,
            # )
            self.model = AzureOpenAI(
                azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                api_key=os.environ["AZURE_OPENAI_API_KEY"],
                api_version="2024-02-01"
            )

            self.model_name = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]
            # print(f"Loaded embedding model: {self.model_name}")
            # print(f"embedding dimension: {self.model.get_embedding_dimension()}")
        except Exception as e:
            print(f"Error loading model {self.model_name}: {e}")
            raise


    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts using the specified model.
        
        Args: 
            texts (List[str]): A list of strings to generate embeddings for.

        Returns:
            List[List[float]]: A list of float lists representing the embeddings for each text.
        
        """
        try:
            #embedding_manager = EmbeddingManager()
            #split_documents = load_and_split_documents()
            #embeddings = self.model.encode(texts, show_progress_bar=True)
            response = self.model.embeddings.create(
                 model=self.model_name,
                 input=texts
                 )

            embeddings = [
                item.embedding
                for item in response.data
            ]
            # print(f"Embedding shape: {embeddings.shape}")
            return embeddings
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            raise



# if __name__ == "__main__":
#     # embedding_manager = EmbeddingManager()
#     embedding_manager = EmbeddingManager()
#     # generated_embeddings = embedding_manager.generate_embeddings(["Hello world", "How are you?"])
#     # # generated_embeddings = generate_embeddings(load_and_split_documents())
#     # print("Generated embeddings:")
#     # for i,emb in enumerate(generated_embeddings):
#     #     print(f"Text: {['Hello world', 'How are you?'][i]}")
#     #     #print(f"Text: {load_and_split_documents()[i].page_content}")
#     #     print(f"Embedding: {emb}\n")






























    # def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
    #     return self.model.encode(texts)

    # def add_embeddings(self, texts: List[str], metadatas: List[Dict[str, Any]]):
    #     embeddings = self.embed_texts(texts)
    #     ids = [str(uuid.uuid4()) for _ in range(len(texts))]
    #     self.collection.add(
    #         documents=texts,
    #         metadatas=metadatas,
    #         embeddings=embeddings.tolist(),
    #         ids=ids
    #     )

    # def query_embeddings(self, query: str, top_k: int = 5) -> List[Tuple[str, Dict[str, Any], float]]:
    #     query_embedding = self.embed_texts([query])[0]
    #     results = self.collection.query(
    #         query_embeddings=[query_embedding.tolist()],
    #         n_results=top_k
    #     )
        
    #     # Extracting the results
    #     retrieved_texts = results['documents'][0]
    #     retrieved_metadatas = results['metadatas'][0]
    #     retrieved_embeddings = results['embeddings'][0]

    #     # Calculate cosine similarity scores
    #     similarities = cosine_similarity([query_embedding], retrieved_embeddings)[0]

    #     return list(zip(retrieved_texts, retrieved_metadatas, similarities))
