import os
from langchain.agents import create_agent
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.memory import InMemorySaver

ROOT_DIR = Path(__file__).resolve().parents[1]
print("Root directory:", ROOT_DIR)
load_dotenv(ROOT_DIR / ".env") 


agent = create_agent(
    model="gpt-4o-mini",
    checkpointer=InMemorySaver(),
    middleware=[SummarizationMiddleware(
        model="gpt-4o-mini",
        trigger=("messages", 10),
        keep=("messages", 5),
    )]
)

config = {
    "configurable":
    {
        "thread_id": "test-1"
    }
}

#questions
questions = [
    "what is 2+2?",
    "what is 3+3?",
    "what is 4+4?",
    "what is 5+5?",
    "what is 6+6?",
    "what is 7+7?",
]

for q in questions:
    response = agent.invoke({"messages": [HumanMessage(content=q)]}, config=config)
    print(f"Messages: {response}")
    print(f"Messages Length : {len(response['messages'])}")