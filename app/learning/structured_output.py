import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from pathlib import Path
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[1]
print("Root directory:", ROOT_DIR)
load_dotenv(ROOT_DIR / ".env") 

model = init_chat_model("gpt-4o-mini")

class Movie(BaseModel):
    title: str = Field(..., description="The title of the movie")
    year: int = Field(..., description="The year the movie was released")
    director: str = Field(..., description="The director of the movie")
    hero: str = Field(..., description="The main hero of the movie")
    budget: float | None = Field(None, description="The budget of the movie in USD")


model_with_structured_output = model.with_structured_output(Movie)

structured_response = model_with_structured_output.invoke("Provide details for the movie 'Indra'")

print(structured_response)