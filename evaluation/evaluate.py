"""Offline scoring and an opt-in adapter for the existing RAG app.

Run from the repository root: python -m evaluation.evaluate --help
Only `run` imports the application; validation needs the existing pypdf dependency.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "dataset.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalize(text):
    """Normalize extraction whitespace and Unicode, preserving punctuation/case."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prediction_hash(row):
    payload = json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def load_dataset(path=DEFAULT_DATASET):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    require(data.get("schema_version") == 1, "Unsupported dataset schema_version")
    require(nonempty(data.get("dataset_id")), "Missing dataset_id")
    source = data.get("source", {})
    require(nonempty(source.get("path")), "Missing source path")
    require(nonempty(source.get("filename")), "Missing source filename")
    require(
        type(source.get("pages")) is int and source["pages"] > 0, "Invalid page count"
    )
    require(
        bool(re.fullmatch(r"[0-9a-f]{64}", source.get("sha256", ""))),
        "Invalid source SHA256",
    )
    cases = data.get("cases")
    require(isinstance(cases, list) and cases, "Dataset has no cases")
    ids, questions, topic_splits = set(), set(), {}
    for case in cases:
        label = case.get("id", "<missing id>")
        for field in ("id", "topic", "type", "user_input", "reference"):
            require(nonempty(case.get(field)), f"{label}: missing {field}")
        require(label not in ids, f"Duplicate case ID: {label}")
        ids.add(label)
        question = normalize(case["user_input"]).casefold()
        require(question not in questions, f"Duplicate question: {label}")
        questions.add(question)
        require(case.get("split") in {"dev", "test"}, f"{label}: invalid split")
        require(
            case.get("difficulty") in {"easy", "medium", "hard"},
            f"{label}: invalid difficulty",
        )
        require(
            case.get("expected_behavior") in {"answer", "abstain"},
            f"{label}: invalid behavior",
        )
        previous = topic_splits.setdefault(case["topic"], case["split"])
        require(
            previous == case["split"], f"Topic occurs in both splits: {case['topic']}"
        )
        points = case.get("reference_key_points")
        require(
            isinstance(points, list) and points and all(nonempty(x) for x in points),
            f"{label}: invalid key points",
        )
        contexts = case.get("reference_contexts")
        require(
            isinstance(contexts, list), f"{label}: reference_contexts must be a list"
        )
        if case["expected_behavior"] == "answer":
            require(bool(contexts), f"{label}: answerable case needs evidence")
        else:
            require(
                not contexts, f"{label}: abstention case must not claim answer evidence"
            )
            require(
                nonempty(case.get("unanswerable_reason")),
                f"{label}: missing abstention rationale",
            )
        for context in contexts:
            page = context.get("page")
            require(
                type(page) is int and 1 <= page <= source["pages"],
                f"{label}: invalid evidence page",
            )
            require(nonempty(context.get("text")), f"{label}: empty evidence")
    return data


def validate_pdf(data, pdf_path=None):
    from pypdf import PdfReader

    path = Path(pdf_path) if pdf_path else ROOT / data["source"]["path"]
    require(
        file_hash(path) == data["source"]["sha256"],
        "PDF fingerprint changed; review and version the dataset",
    )
    pages = PdfReader(path).pages
    require(len(pages) == data["source"]["pages"], "PDF page count changed")
    texts = [normalize(page.extract_text() or "") for page in pages]
    for case in data["cases"]:
        for context in case["reference_contexts"]:
            require(
                normalize(context["text"]) in texts[context["page"] - 1],
                f"{case['id']}: evidence not found on PDF page {context['page']}",
            )


def select_cases(data, split):
    return [case for case in data["cases"] if split == "all" or case["split"] == split]


def read_jsonl(path):
    rows = []
    for number, line in enumerate(
        Path(path).read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if line.strip():
            row = json.loads(line)
            require(isinstance(row, dict), f"{path}:{number}: expected an object")
            rows.append(row)
    require(bool(rows), f"{path}: no rows")
    return rows


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows
        ),
        encoding="utf-8",
    )


def validate_predictions(rows, cases, allow_partial=False):
    require(bool(rows), "No prediction rows")
    require(bool(cases), "Selected split has no cases")
    expected = {case["id"] for case in cases}
    seen = set()
    for row in rows:
        label = row.get("id")
        require(label in expected, f"Unexpected prediction ID for this split: {label}")
        require(label not in seen, f"Duplicate prediction ID: {label}")
        seen.add(label)
        require(
            row.get("mode") in {"rag", "retrieval"},
            f"{label}: mode must be rag or retrieval",
        )
        require(
            row.get("error") is None or nonempty(row["error"]),
            f"{label}: invalid error",
        )
        if row["mode"] == "rag" and not row.get("error"):
            require(
                isinstance(row.get("answer"), str),
                f"{label}: answer must be a string (empty is scored as failure)",
            )
        else:
            require(
                row.get("answer") is None,
                f"{label}: retrieval/error rows need answer=null",
            )
        abstained = row.get("abstained")
        require(
            abstained is None or type(abstained) is bool,
            f"{label}: abstained must be boolean or null",
        )
        if row["mode"] == "retrieval" or row.get("error"):
            require(
                abstained is None,
                f"{label}: abstained must be null for retrieval/error rows",
            )
        contexts = row.get("contexts")
        require(isinstance(contexts, list), f"{label}: contexts must be a list")
        for context in contexts:
            require(isinstance(context, dict), f"{label}: context must be an object")
            require(nonempty(context.get("content")), f"{label}: empty context content")
            require(nonempty(context.get("source")), f"{label}: context source missing")
            require(
                type(context.get("page")) is int and context["page"] >= 1,
                f"{label}: context page must be a one-based positive integer",
            )
        latency = row.get("latency_ms")
        require(
            latency is None
            or (
                type(latency) in {int, float}
                and math.isfinite(latency)
                and latency >= 0
            ),
            f"{label}: invalid latency_ms",
        )
    require(
        len({row["mode"] for row in rows}) == 1,
        "Cannot combine retrieval and rag modes in one report",
    )
    missing = sorted(expected - seen)
    require(
        allow_partial or not missing,
        f"Missing prediction IDs: {', '.join(missing)}. Use --allow-partial only for a smoke run.",
    )
    return missing


def answer_tokens(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"(?<=\d),(?=\d)", "", value)
    return re.findall(r"\w+", value)


def token_f1(answer, reference):
    predicted, gold = Counter(answer_tokens(answer)), Counter(answer_tokens(reference))
    if not predicted or not gold:
        return 0.0
    common = sum((predicted & gold).values())
    return 2 * common / (sum(predicted.values()) + sum(gold.values()))


def explicit_abstention(row):
    """Only recognize whole-response refusals; never match embedded disclaimers."""
    if row.get("error") or row["mode"] != "rag":
        return None
    if row.get("abstained") is not None:
        return row["abstained"]
    text = normalize(row["answer"]).casefold().replace("’", "'").strip(". !\"'")
    return text in {
        "i don't know",
        "i do not know",
        "not enough information",
        "insufficient information",
    }


def score_case(case, row, source, k):
    contexts = row["contexts"][:k]
    result = {
        "id": case["id"],
        "split": case["split"],
        "type": case["type"],
        "difficulty": case["difficulty"],
        "expected_behavior": case["expected_behavior"],
        "error": row.get("error"),
        "latency_ms": row.get("latency_ms"),
    }
    # Evaluate annotated source/page pairs; arbitrary vector-store IDs are unstable.
    target_pages = {c["page"] for c in case["reference_contexts"]}
    relevant = [c["source"] == source and c["page"] in target_pages for c in contexts]
    found = {c["page"] for c, match in zip(contexts, relevant) if match}
    answerable = case["expected_behavior"] == "answer"
    result.update(
        {
            "page_hit_at_k": float(any(relevant)) if answerable else None,
            "annotated_page_recall_at_k": len(found) / len(target_pages)
            if answerable
            else None,
            "page_mrr_at_k": next(
                (1 / i for i, match in enumerate(relevant, 1) if match), 0.0
            )
            if answerable
            else None,
            # Fixed denominator penalizes returning fewer than k and duplicate pages.
            "unique_relevant_pages_per_k": len(found) / k if answerable else None,
            "answer_token_f1": token_f1(row.get("answer") or "", case["reference"])
            if answerable and row["mode"] == "rag"
            else None,
            "abstention_accuracy": float(
                bool((row.get("answer") or "").strip())
                and explicit_abstention(row) == (not answerable)
            )
            if row["mode"] == "rag"
            else None,
        }
    )
    return result


METRICS = (
    "page_hit_at_k",
    "annotated_page_recall_at_k",
    "page_mrr_at_k",
    "unique_relevant_pages_per_k",
    "answer_token_f1",
    "abstention_accuracy",
    "correctness",
    "faithfulness",
    "relevance",
    "latency_ms",
)


def aggregate(rows):
    values = {}
    for metric in METRICS:
        observed = [row[metric] for row in rows if row.get(metric) is not None]
        values[metric] = {
            "mean": statistics.mean(observed) if observed else None,
            "n": len(observed),
        }
    return {
        "cases": len(rows),
        "errors": sum(bool(row.get("error")) for row in rows),
        "metrics": values,
    }


def load_reviews(path, predictions):
    reviews = {}
    for review in read_jsonl(path):
        label = review.get("id")
        require(label in predictions, f"Review has unknown ID: {label}")
        require(label not in reviews, f"Duplicate review: {label}")
        require(
            review.get("prediction_sha256") == prediction_hash(predictions[label]),
            f"{label}: review belongs to a different prediction",
        )
        require(nonempty(review.get("reviewer")), f"{label}: reviewer is required")
        require(
            predictions[label]["mode"] == "rag" and not predictions[label].get("error"),
            f"{label}: cannot review retrieval-only or failed predictions",
        )
        for metric in ("correctness", "faithfulness", "relevance"):
            require(
                type(review.get(metric)) is int and review[metric] in {0, 1, 2},
                f"{label}: {metric} must be 0, 1, or 2; remove unreviewed rows",
            )
        reviews[label] = review
    return reviews


def verify_run_metadata(
    predictions_path, dataset_path, data, k=None, allow_partial=False
):
    """App-generated predictions are bound to the dataset and source used in the run."""
    sidecar = Path(predictions_path).with_suffix(".run.json")
    if not sidecar.exists():
        return  # Externally collected predictions use the documented JSONL contract.
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    require(
        metadata.get("dataset_sha256") == file_hash(dataset_path),
        "Dataset differs from prediction run",
    )
    require(
        metadata.get("source_sha256") == data["source"]["sha256"],
        "Source differs from prediction run",
    )
    require(
        metadata.get("complete") or allow_partial,
        "Run was interrupted; use --allow-partial to inspect it",
    )
    if metadata.get("complete"):
        require(
            metadata.get("predictions_sha256") == file_hash(predictions_path),
            "Predictions changed after the run",
        )
    if k is not None:
        require(
            k <= metadata["top_k"],
            "Scoring k exceeds the top_k used to collect predictions",
        )


def make_report(data, cases, predictions, k, allow_partial=False, reviews=None):
    require(type(k) is int and k > 0, "k must be positive")
    missing = validate_predictions(predictions, cases, allow_partial)
    by_id = {row["id"]: row for row in predictions}
    results = []
    for case in cases:
        if case["id"] not in by_id:
            continue
        result = score_case(case, by_id[case["id"]], data["source"]["filename"], k)
        if reviews and case["id"] in reviews:
            result.update(
                {
                    m: reviews[case["id"]][m]
                    for m in ("correctness", "faithfulness", "relevance")
                }
            )
        results.append(result)
    grouped = {}
    for field in ("split", "type", "difficulty", "expected_behavior"):
        grouped[field] = {
            value: aggregate([row for row in results if row[field] == value])
            for value in sorted({row[field] for row in results})
        }
    return {
        "dataset_id": data["dataset_id"],
        "source_sha256": data["source"]["sha256"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "k": k,
        "mode": predictions[0]["mode"],
        "expected_cases": len(cases),
        "prediction_coverage": len(predictions) / len(cases),
        "missing_ids": missing,
        "human_reviewed_cases": len(reviews or {}),
        "limitations": [
            "Page metrics use annotated evidence pages, not exhaustive passage relevance labels.",
            "Same-page irrelevant chunks may count as hits. Review actual context content.",
            "Token F1 is lexical overlap, not semantic correctness or faithfulness.",
            "Automatic abstention uses explicit labels or exact short refusal phrases; review other wording.",
            "Semantic review scores use a 0-2 scale and apply only to reviewed cases.",
            "Unanswerable questions are excluded from retrieval and token-F1 metrics.",
        ],
        "overall": aggregate(results),
        "by_group": grouped,
        "per_case": results,
    }


def run_app(args, data, cases):
    from evaluation.app_adapter import AppAdapter

    validate_pdf(data)
    adapter = AppAdapter(args.persist_directory, args.collection, args.retrieval_only)
    if args.limit:
        cases = cases[: args.limit]
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "dataset_id": data["dataset_id"],
        "dataset_sha256": file_hash(args.dataset),
        "source_sha256": data["source"]["sha256"],
        "split": args.split,
        "case_ids": [case["id"] for case in cases],
        "top_k": args.k,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "settings": adapter.settings,
        "complete": False,
    }
    write_json(path.with_suffix(".run.json"), metadata)
    failures = 0
    with path.open("w", encoding="utf-8") as stream:
        for case in cases:
            start = time.perf_counter()
            row = {
                "id": case["id"],
                "mode": "retrieval" if args.retrieval_only else "rag",
                "answer": None,
                "abstained": None,
                "contexts": [],
                "error": None,
            }
            try:
                row.update(adapter.predict(case["user_input"], args.k))
            except Exception as error:
                failures += 1
                row["error"] = f"{type(error).__name__}: {error}"
                print(f"{case['id']}: {row['error']}", file=sys.stderr)
            row["latency_ms"] = round((time.perf_counter() - start) * 1000, 3)
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
    metadata.update(
        {
            "complete": True,
            "predictions_sha256": file_hash(path),
            "failed_cases": failures,
        }
    )
    write_json(path.with_suffix(".run.json"), metadata)
    print(f"Saved {len(cases)} predictions to {path}; {failures} failed.")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in (
        "validate",
        "template",
        "run",
        "score",
        "review-template",
        "export-ragas",
    ):
        part = sub.add_parser(command)
        part.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
        part.add_argument("--split", choices=("dev", "test", "all"), default="dev")
        if command == "validate":
            part.add_argument("--pdf", type=Path)
        if command in {"template", "run", "review-template", "export-ragas"}:
            part.add_argument("--output", type=Path, required=True)
        if command in {"score", "review-template", "export-ragas"}:
            part.add_argument("--predictions", type=Path, required=True)
            part.add_argument("--allow-partial", action="store_true")
        if command in {"run", "score"}:
            part.add_argument("--k", type=int, default=5)
        if command == "run":
            part.add_argument("--retrieval-only", action="store_true")
            part.add_argument(
                "--persist-directory", type=Path, default=ROOT / "app/data/vector_store"
            )
            part.add_argument("--collection", default="pdf_documents")
            part.add_argument("--limit", type=int)
        if command == "score":
            part.add_argument("--reviews", type=Path)
            part.add_argument(
                "--output-dir", type=Path, default=ROOT / "evaluation/results/report"
            )
    args = parser.parse_args(argv)
    try:
        if hasattr(args, "k"):
            require(args.k > 0, "--k must be positive")
        if getattr(args, "limit", None) is not None:
            require(args.limit > 0, "--limit must be positive")
        data = load_dataset(args.dataset)
        cases = select_cases(data, args.split)
        require(bool(cases), "Selected split has no cases")
        if args.command == "validate":
            validate_pdf(data, args.pdf)
            print(
                json.dumps(
                    {
                        "valid": True,
                        "dataset_id": data["dataset_id"],
                        "cases": len(data["cases"]),
                        "splits": dict(Counter(c["split"] for c in data["cases"])),
                        "behaviors": dict(
                            Counter(c["expected_behavior"] for c in data["cases"])
                        ),
                    },
                    indent=2,
                )
            )
        elif args.command == "template":
            write_jsonl(
                args.output,
                [
                    {
                        "id": c["id"],
                        "mode": "rag",
                        "answer": "",
                        "abstained": None,
                        "contexts": [],
                        "latency_ms": None,
                        "error": None,
                    }
                    for c in cases
                ],
            )
            print(
                f"Wrote {len(cases)} blank rows. Fill real answers and ranked contexts before scoring."
            )
        elif args.command == "run":
            return run_app(args, data, cases)
        else:
            verify_run_metadata(
                args.predictions,
                args.dataset,
                data,
                getattr(args, "k", None),
                args.allow_partial,
            )
            predictions = read_jsonl(args.predictions)
            validate_predictions(predictions, cases, args.allow_partial)
            by_id = {row["id"]: row for row in predictions}
            if args.command == "score":
                reviews = load_reviews(args.reviews, by_id) if args.reviews else None
                report = make_report(
                    data, cases, predictions, args.k, args.allow_partial, reviews
                )
                report["dataset_sha256"] = file_hash(args.dataset)
                report["predictions_sha256"] = file_hash(args.predictions)
                write_json(args.output_dir / "report.json", report)
                with (args.output_dir / "per_case.csv").open(
                    "w", newline="", encoding="utf-8"
                ) as stream:
                    fields = list(
                        dict.fromkeys(key for row in report["per_case"] for key in row)
                    )
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(report["per_case"])
                print(
                    json.dumps(
                        {
                            "coverage": report["prediction_coverage"],
                            **report["overall"],
                        },
                        indent=2,
                    )
                )
            elif args.command == "review-template":
                rows = []
                for case in cases:
                    prediction = by_id.get(case["id"])
                    if (
                        not prediction
                        or prediction["mode"] != "rag"
                        or prediction.get("error")
                    ):
                        continue
                    rows.append(
                        {
                            "id": case["id"],
                            "prediction_sha256": prediction_hash(prediction),
                            "reviewer": "",
                            "correctness": None,
                            "faithfulness": None,
                            "relevance": None,
                            "notes": "",
                            "user_input": case["user_input"],
                            "reference": case["reference"],
                            "reference_key_points": case["reference_key_points"],
                            "reference_contexts": case["reference_contexts"],
                            "answer": prediction["answer"],
                            "contexts": prediction["contexts"],
                        }
                    )
                require(bool(rows), "No successful RAG predictions available to review")
                write_jsonl(args.output, rows)
            elif args.command == "export-ragas":
                # Reference-based metrics are meaningful here only for answerable, successful rows.
                rows = [
                    {
                        "user_input": c["user_input"],
                        "response": by_id[c["id"]]["answer"],
                        "retrieved_contexts": [
                            x["content"] for x in by_id[c["id"]]["contexts"]
                        ],
                        "reference": c["reference"],
                        "reference_contexts": [
                            x["text"] for x in c["reference_contexts"]
                        ],
                    }
                    for c in cases
                    if c["expected_behavior"] == "answer"
                    and c["id"] in by_id
                    and by_id[c["id"]]["mode"] == "rag"
                    and not by_id[c["id"]].get("error")
                ]
                require(
                    bool(rows), "No successful answerable RAG predictions to export"
                )
                write_jsonl(args.output, rows)
                print(
                    f"Exported {len(rows)} rows; excluded abstention, retrieval-only, and failed cases."
                )
    except (ValueError, OSError, ImportError) as error:
        print(f"Evaluation error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
