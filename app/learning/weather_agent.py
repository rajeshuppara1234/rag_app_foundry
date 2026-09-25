"""Original weather learning example, separate from the web application."""

from dotenv import load_dotenv
from langchain.agents import create_agent


def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"The weather in {city} is sunny with a high of 25°C."


if __name__ == "__main__":
    load_dotenv()
    agent = create_agent(
        model="gpt-4o-mini",
        tools=[get_weather],
        system_prompt="You are a helpful assistant that provides weather information.",
    )
    result = agent.invoke(
        {
            "messages": [
                {"role": "user", "content": "What's the weather like in New York?"}
            ]
        }
    )
    print(result["messages"][-1].content_blocks)
