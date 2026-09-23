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

@tool
def getString(city: str) -> str:
    """Get a string for a given city."""
    return f"String for {city}."


model = init_chat_model("gpt-4o-mini")
model_with_tools = model.bind_tools([getWeather, getString])


#Model generates tool calls
messages = [
    {"role": "user", "content": "What's the weather like in New York?"},
    {"role": "user", "content": "What is the string for New York?"}]
ai_msg = model_with_tools.invoke(messages);
messages.append(ai_msg)


#execute tools and collect results
for tool_call in ai_msg.tool_calls:
    print(f"Tool: {tool_call['name']}")
    tool_name = tool_call['name']
    tool_args = tool_call['args']
    if tool_name == "getWeather":
        result = getWeather.invoke(tool_call)
        messages.append(result)
    if tool_name == "getString":
        result = getString.invoke(tool_call)
        messages.append(result)


#pass results back to model for final response
final_response = model_with_tools.invoke(messages)


print(final_response.text)