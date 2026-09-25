import os
from langchain.agents import create_agent
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.memory import InMemorySaver


ROOT_DIR = Path(__file__).resolve().parents[2]
print("Root directory:", ROOT_DIR)
load_dotenv(ROOT_DIR / ".env", override=False)