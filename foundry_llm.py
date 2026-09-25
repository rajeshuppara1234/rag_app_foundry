"""Manual model smoke test; importing this module does not call Azure."""

from app.retrieval.augument_gen import AugmentGen


if __name__ == "__main__":
    generator = AugmentGen()
    try:
        print(
            generator.llm.invoke("Explain vector embeddings in one sentence.").content
        )
    finally:
        generator.close()
