from langchain.agents import create_agent
from dotenv import load_dotenv
from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
print("Root directory:", ROOT_DIR)
load_dotenv(ROOT_DIR / ".env") 


@tool
def getWeather(city: str) -> str:
    """Get weather for a given city."""
    return f"The weather in {city} is sunny with a high of 25°C."


model = init_chat_model("gpt-4o-mini")

model_with_tools = model.bind_tools([getWeather])

model_response = model_with_tools.invoke("What's the weather like in New York?")

#print(model_response)
for tool_call in model_response.tool_calls:
    print(f"Tool: {tool_call['name']}")
    print(f"Args: {tool_call['args']}")