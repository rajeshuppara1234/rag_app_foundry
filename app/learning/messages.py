import os
from langchain.agents import create_agent
from dotenv import load_dotenv
from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from pathlib import Path
from langchain.messages import SystemMessage, HumanMessage, AIMessage


ROOT_DIR = Path(__file__).resolve().parents[2]
print("Root directory:", ROOT_DIR)
load_dotenv(ROOT_DIR / ".env", override=False)

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
model = init_chat_model(
    "gpt-4o-mini"
)

messages = [
    SystemMessage(content="You are expert in REST APIs and can provide information about weather."),
    HumanMessage(content="How do I create a REST API to get weather information?")
]

response = model.stream(messages)
for chunk in response:
    print(chunk.text, end="", flush=True)