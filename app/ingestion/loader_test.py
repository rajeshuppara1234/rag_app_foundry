import os
from langchain_core.documents import Document
# from langchain.document_loaders import TextLoader
from langchain_community.document_loaders import TextLoader

doc = Document(
    page_content="This is main text document content.",
    metadata = 
    { 
        "source": "main.py", 
        "author": "Rajesh",
        "pages": 1
    }
)


loader = TextLoader(file_path="app/data/text_files/python_intro.txt", encoding="utf-8")
document = loader.load()

print(document)



























































# os.makedirs("/app/data", exist_ok=True)

# sample_texts = {
#     "../data/text_files/python_intro.txt": """Python is a high-level, 
#     interpreted programming language known for its simplicity and readability.""",

#     "../data/text_files/machine_learning.txt": """Machine learning is a 
#     subset of artificial intelligence that focuses on building systems 
#     that can learn from and make decisions based on data."""
# }

# for filepath, content in sample_texts.items():
#     with open(filepath, "w", encoding="utf-8") as f:
#         print(f)
#         f.write(content)

# print("Sample text files created successfully.")