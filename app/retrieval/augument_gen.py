import os
from dotenv import load_dotenv, main
from langchain_openai import ChatOpenAI
from pathlib import Path
from foundry_llm import llm
from app.retrieval.retriever import RAGRetriever  # Assuming you have a Retriever class defined elsewhere
from app.retrieval.vector_store import VectorStore

from azure.identity import (
    DefaultAzureCredential,
    get_bearer_token_provider
)

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]
print("Root directory:", ROOT_DIR)
token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default"
)


class AugmentGen:
    def __init__(self):
        load_dotenv(ROOT_DIR / ".env")  # Load environment variables from project root
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

        self.llm = ChatOpenAI(
            model=os.environ["FOUNDRY_CHAT_MODEL"],
            base_url=os.environ["FOUNDRY_OPENAI_ENDPOINT"],
            api_key=token_provider
)

        # self.llm = ChatOpenAI(
        #     model_name="gpt-4o-mini",
        #     openai_api_key=self.openai_api_key,
        #     temperature=0.7,
        #     max_tokens=1024
        # )

    def rag_simple(self, query: str, retriever, llm, top_k = 5):
        results = retriever.retrieve(query, top_k=top_k)
        context = "\n\n".join([result['content'] for result in results]) if results else "No relevant context found."

        # generate a response using the LLM with the retrieved context
        prompt = f""" Use the following contect to answer the question. If the context does not contain enough 
        information, respond with "I don't know".\n\n

        Context:\n{context}\n\nQuestion: {query}\n
        
        Answer: """
        response = llm.invoke([prompt.format(context=context, query=query)])

        return response.content
    
if __name__ == "__main__":
    vector_store = VectorStore()  # Assuming you have a VectorStore class defined elsewhere
    retriever = RAGRetriever(vector_store)  # Assuming you have a Retriever class defined elsewhere

    augment_gen = AugmentGen()
    query = "what is LangChain?"
    response = augment_gen.rag_simple(query, retriever, augment_gen.llm)
    print("Response:", response)
