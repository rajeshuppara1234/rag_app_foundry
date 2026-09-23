# Evaluation for rag.pdf

Use the supplied golden candidate dataset to measure retrieval and answer quality separately. Start with local scoring and human review; add an automated semantic judge once you have reviewed examples to calibrate it. The production app and its dependencies are unchanged.

## Dataset

`dataset.json` contains **50 manually authored, source-checked candidate cases**: 40 answerable and 10 unanswerable. There are 28 development cases and 22 held-out test cases. Topic groups stay in one split; related concepts and evidence pages can still overlap because this is a single introductory document. This is a starter regression benchmark, not a statistically representative production benchmark.

The source is `app/data/rag.pdf`, the 20-page presentation *Harness Proprietary Data with Foundational Models and RAG* by Marian Veteanu. Cases cover definitions, lists, comparisons, workflows, code reading, scenarios, numerical facts, four questions requiring evidence from multiple pages, and missing-information questions. Every answerable case includes:

- `user_input`: the question submitted to the app.
- `reference`: the expected answer, allowing equivalent wording.
- `reference_key_points`: the points a reviewer should check.
- `reference_contexts`: supporting excerpts with **one-based PDF page numbers**.
- `id`, `split`, `topic`, `type`, `difficulty`, and `expected_behavior`.

Unanswerable cases have `expected_behavior: "abstain"`, empty answer evidence, and an `unanswerable_reason`. A useful refusal explains that the document does not contain the requested information. Never fill gaps using web knowledge or this repository's configuration: the benchmark scope is the PDF alone.

The source SHA256 is stored with the dataset. `validate` checks the fingerprint, all evidence excerpts against their stated pages (after whitespace/Unicode normalization), unique IDs/questions, and basic schema/split rules. This verifies source provenance, not semantic correctness of every annotation or the absence of an answer elsewhere. Human review of references and unanswerability is still required before treating the candidate as approved gold.

Some slide examples are historical. Questions about API calls, model names, database capabilities, and provider lists ask what **the slides say**; the answers are not current implementation advice. The short dataset intentionally avoids treating the old context-window and training-cutoff examples as current facts.

## Run locally

Run from the repository root. In PowerShell, use the existing interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate validate
.\.venv\Scripts\python.exe -m unittest evaluation.test_evaluate -v
```

Offline scoring uses the Python standard library. PDF validation uses `pypdf`, already in this project. The unit tests exercise synthetic predictions; their scores are **not measurements of your RAG app**.

### Collect real predictions from the current app

The adapter uses `RAGRetriever.retrieve` and `AugmentGen.rag_simple` from the existing application. It records exactly the retrieval call used for generation, including rank order, and converts the loader's zero-based page metadata to one-based pages. It never sends references or evidence labels to the app.

You need an existing, populated Chroma collection containing **only this rag.pdf**, built from the fingerprinted PDF, and the app's embedding model/dependencies. This repository's default collection is `pdf_documents` at `app/data/vector_store`. The adapter fails on an empty/missing collection or missing source/page metadata. It does not ingest or insert records. Chroma may still perform its normal local database maintenance when opened. Existing metadata cannot prove which PDF bytes were indexed; verify that the index was built from the unchanged source.

Retrieval-only evaluation calls no answer-generation API; the existing embedding manager may download its model if it is not cached:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate run --split dev --retrieval-only --k 5 --output evaluation/results/dev-retrieval.jsonl
.\.venv\Scripts\python.exe -m evaluation.evaluate score --split dev --k 5 --predictions evaluation/results/dev-retrieval.jsonl --output-dir evaluation/results/dev-retrieval-report
```

Full evaluation invokes the app's configured model and can incur API charges. Set `OPENAI_API_KEY` in the environment or where the app already loads it. The adapter preserves the existing prompt, model, temperature, retrieval settings, and score threshold.

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate run --split dev --k 5 --output evaluation/results/dev.jsonl
.\.venv\Scripts\python.exe -m evaluation.evaluate score --split dev --k 5 --predictions evaluation/results/dev.jsonl --output-dir evaluation/results/dev-report
```

Use `--persist-directory PATH --collection NAME` to select another existing index. Use `--limit 3` for a smoke run and `--allow-partial` when scoring that run; otherwise missing predictions are errors. Duplicate/unknown IDs, invalid pages, and mixed retrieval/full modes are rejected. Cases that fail remain in the denominator with zero automated quality scores and an error count; a failed run exits with code 1. Configuration/validation errors exit with code 2.

Each run writes a `.run.json` sidecar with dataset/source hashes, settings, selected IDs, timestamps, and a predictions hash. Scoring checks an available sidecar and rejects changed datasets/predictions or a scoring `k` larger than the collected `top_k`. Preserve it alongside the JSONL. Keep separate paths for each experiment; output paths are overwritten if reused. Reports are `report.json` and `per_case.csv`, with aggregate counts and breakdowns by type, difficulty, expected behavior, and split. `evaluation/results/` is git-ignored.

The current retriever catches internal errors and returns an empty list. Consequently a swallowed retrieval exception appears as zero retrieval coverage, not a raised evaluation error; inspect its logs. It also computes `1 - distance` under a cosine assumption, while the vector-store setup does not explicitly select cosine distance. These are existing app behaviors to investigate if the retrieval baseline is poor. The evaluator intentionally measures that behavior. Generation failures currently count as failed whole requests, including zero retrieval credit.

### Score predictions collected elsewhere

Create empty rows, then replace them with **real** answers and ranked retrieved chunks:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate template --split dev --output evaluation/results/predictions.jsonl
```

Each line follows this contract (the values below are illustrative):

```json
{"id":"rag-001","mode":"rag","answer":"Marian Veteanu.","abstained":false,"contexts":[{"content":"by Marian Veteanu","source":"rag.pdf","page":1}],"latency_ms":120.0,"error":null}
```

`contexts` must be ordered best-first; `source` is the PDF filename, not its full path. `page` is one-based. A retrieval-only row uses `mode: "retrieval"`, `answer: null`, and `abstained: null`. An error row has a nonempty `error` and null answer/abstention. Do not set `abstained` from the expected label: it must describe the actual response. Leave it null for the conservative phrase detector, or label it after inspecting the response. Blank template answers receive zero answer/abstention scores and are not valid application results.

## Metrics and interpretation

| Metric | Definition and limitations |
| --- | --- |
| `page_hit_at_k` | 1 if any of the first k chunks matches an annotated source/page pair; otherwise 0. Answerable cases only. |
| `annotated_page_recall_at_k` | Number of distinct annotated pages retrieved / number of distinct annotated evidence pages. Duplicates do not increase recall. |
| `page_mrr_at_k` | Reciprocal rank of the first annotated page match; zero when no match. |
| `unique_relevant_pages_per_k` | Distinct annotated pages retrieved / k. A page-diversity diagnostic, **not standard context precision**. It is intentionally low when only one page is needed. |
| `answer_token_f1` | Bag-of-word token overlap with the reference, with case and number-comma normalization. Answerable full-RAG cases only. It cannot establish correctness, handle every paraphrase, or detect contradictions reliably. |
| `abstention_accuracy` | Agreement between actual abstention and expected behavior. Empty/failed responses score 0. An explicit boolean is used if supplied; otherwise only exact short refusals such as "I don't know" are recognized. Inspect answerable and unanswerable groups separately. |
| `correctness`, `faithfulness`, `relevance` | Human-review scores, 0-2, with the rubric below. Null until reviewed; denominators show review coverage. |
| `latency_ms` | Wall time for retrieval plus generation, or retrieval alone in retrieval mode. Includes model initialization occurring inside retrieval; excludes adapter initialization. |

Page metrics are coarse diagnostics. Retrieving irrelevant text from a labeled page can count as a hit, and an unannotated alternative passage can be useful. For multi-page questions recall expects every annotated page. This supports stable comparison when chunk sizes/IDs change, but does **not** replace passage relevance review. No retrieval score is assigned to unanswerable cases: retrieving something for such a question is not automatically a mistake.

There is no arbitrary overall pass/fail grade or fabricated faithfulness score. Compare runs on the same frozen split and `k`, inspect per-case failures, and decide targets from a reviewed baseline. A useful starting policy is to investigate every unsupported answer and every new regression, and approve release criteria only after reviewing the quality and representativeness of the cases.

## Review semantic quality

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate review-template --split dev --predictions evaluation/results/dev.jsonl --output evaluation/results/dev-reviews.jsonl
```

Fill `reviewer`, `correctness`, `faithfulness`, `relevance`, and optional `notes`. Remove rows you have not reviewed before importing; partial review is allowed and counted. Reviews include question, reference/key points, evidence, actual answer, and actual contexts. The prediction fingerprint prevents silently reusing a review for changed output.

| Score | Correctness against the PDF/reference | Faithfulness to actual retrieved context | Relevance to the question |
| --- | --- | --- | --- |
| 2 | All required points correct; no material false claims. For unanswerable cases, correctly declines without guessing. | Every substantive claim is supported by the retrieved text; an appropriate refusal with no factual invention also scores 2. | Directly answers the requested question, or explains why it cannot be answered. |
| 1 | Partially correct or incomplete, without a major contradiction. | Some claims have weak or missing support. | Partly addresses the request or adds substantial irrelevant material. |
| 0 | Incorrect, fabricated, empty, or refuses an answerable question. | Major unsupported/contradictory claims, or empty response. | Does not address the request, or is empty. |

Faithfulness alone does not guarantee correctness: an unjustified refusal on an answerable case can have no unsupported factual claims but still score 0 for correctness. Review both dimensions. An answer copied from the reference is not faithful if the actual retrieved context does not support it.

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate score --split dev --k 5 --predictions evaluation/results/dev.jsonl --reviews evaluation/results/dev-reviews.jsonl --output-dir evaluation/results/dev-reviewed
```

## Optional Ragas path

If you later want an automated semantic judge, I recommend Ragas for context precision/recall, response relevancy, faithfulness, and factual correctness. Its LLM-based metrics can make additional model calls; calibrate them against your human reviews. See the [official metric catalog](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/) and [evaluation dataset documentation](https://docs.ragas.io/en/latest/concepts/components/eval_dataset/).

The exporter prepares the documented single-turn fields `user_input`, `response`, `retrieved_contexts`, `reference`, and `reference_contexts`. It exports only successful answerable full-RAG cases; use this framework's separate abstention evaluation and error counts for the excluded cases.

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate export-ragas --split dev --predictions evaluation/results/dev.jsonl --output evaluation/results/dev-ragas.jsonl
```

This is a data export, not an executed Ragas evaluation. Ragas is not installed or added to the application's requirements by this change.

## Recommended workflow

1. Review and approve the source-checked candidate answers and abstention rationales; keep a versioned record of corrections.
2. Validate the PDF and dataset. Build the index from this PDF alone, excluding all dataset files and evaluation outputs.
3. Run development cases, inspect retrieval misses and refusal behavior, and human-review answers.
4. Change one parameter at a time (such as chunk size, overlap, top-k, or prompt) and compare the same development cases.
5. Freeze configuration, then run and score with `--split test`. Do not repeatedly tune on that split; repeated use turns it into another development set.
6. Expand with representative real user questions and additional documents before drawing production-wide conclusions.

The full 50-case dataset remains readable in one file for inspection. Holdout discipline is procedural, not access-controlled. Only index source PDFs, never golden questions, reference answers, or score reports.
