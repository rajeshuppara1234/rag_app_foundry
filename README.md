# Run a query locally

Configuration is loaded from `.env` in the repository root. The values previously in `app/.env` have been moved there. Environment variables already set in your terminal take precedence.

From the project root, start the server once:

```powershell
uv run uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs** in your browser. Expand **POST /query**, click **Try it out**, enter your question, and click **Execute**:

```json
{"query": "What is LangChain?"}
```

The result is `{"answer": "..."}` from the same RAG flow as `uv run python -m app.retrieval.augument_gen`. Keep the server running and send more queries from the page. Stop it with Ctrl+C.

To send a request from PowerShell instead:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/query" `
  -ContentType "application/json" `
  -Body (@{ query = "What is LangChain?" } | ConvertTo-Json)
```

The root `.env` must contain the existing Foundry chat settings (`FOUNDRY_OPENAI_ENDPOINT`, `FOUNDRY_CHAT_MODEL`), Azure embedding settings (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`), and Chroma settings (`CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_SSL`, `CHROMA_COLLECTION`). `FOUNDRY_API_KEY` is optional; without it, the chat model uses your Azure identity, so run `az login` if needed.

Use the same embedding deployment that populated your Chroma collection. Blank queries return HTTP 422. A database or model failure returns HTTP 503 with details in the server terminal.

The configured Chroma collection must already contain your documents. If the server has no collections, document ingestion is required before a query can return an answer; this endpoint does not create or populate collections.

The browser interface is FastAPI's [built-in interactive documentation](https://fastapi.tiangolo.com/tutorial/first-steps/#interactive-api-docs).
