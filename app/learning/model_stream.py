import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
print("Root directory:", ROOT_DIR)
load_dotenv(ROOT_DIR / ".env") 

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
model = init_chat_model(
    "gpt-4o-mini"
)

# response = model.invoke("write a 200 words poem about the beauty of nature.");
# print(response)

response = model.stream("write a 200 words poem about the beauty of nature.");

for chunk in response:
    print(chunk.text, end="", flush=True)