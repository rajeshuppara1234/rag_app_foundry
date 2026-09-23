"""Offline regression tests. Fixtures are synthetic, never application results."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation import evaluate as ev
from evaluation.app_adapter import AppAdapter, RecordingRetriever, to_context


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ev.load_dataset()

    def prediction(self, case, mode="rag"):
        return {
            "id": case["id"],
            "mode": mode,
            "answer": case["reference"] if mode == "rag" else None,
            "abstained": case["expected_behavior"] == "abstain"
            if mode == "rag"
            else None,
            "contexts": [
                {"content": c["text"], "source": "rag.pdf", "page": c["page"]}
                for c in case["reference_contexts"]
            ],
            "latency_ms": 1.0,
            "error": None,
        }

    def test_all_evidence_is_in_fingerprinted_pdf(self):
        ev.validate_pdf(self.data)
        self.assertEqual(len(self.data["cases"]), 50)
        self.assertEqual(
            sum(c["expected_behavior"] == "abstain" for c in self.data["cases"]), 10
        )

    def test_pdf_change_rejected(self):
        altered = deepcopy(self.data)
        altered["source"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            ev.validate_pdf(altered)

    def test_incorrect_evidence_rejected(self):
        altered = deepcopy(self.data)
        altered["cases"][0]["reference_contexts"][0]["page"] = 2
        with self.assertRaisesRegex(ValueError, "evidence not found"):
            ev.validate_pdf(altered)

    def test_duplicate_dataset_question_rejected(self):
        altered = deepcopy(self.data)
        altered["cases"][1]["user_input"] = altered["cases"][0]["user_input"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.json"
            ev.write_json(path, altered)
            with self.assertRaisesRegex(ValueError, "Duplicate question"):
                ev.load_dataset(path)

    def test_synthetic_oracle_and_failed_baseline_separate(self):
        cases = self.data["cases"]
        oracle = [self.prediction(c) for c in cases]
        report = ev.make_report(self.data, cases, oracle, 10)
        metrics = report["overall"]["metrics"]
        for metric in (
            "page_hit_at_k",
            "annotated_page_recall_at_k",
            "page_mrr_at_k",
            "answer_token_f1",
            "abstention_accuracy",
        ):
            self.assertEqual(metrics[metric]["mean"], 1)
        self.assertEqual(metrics["page_hit_at_k"]["n"], 40)
        self.assertEqual(metrics["abstention_accuracy"]["n"], 50)
        self.assertIsNone(metrics["faithfulness"]["mean"])
        failed = [
            {
                **p,
                "answer": None,
                "abstained": None,
                "contexts": [],
                "error": "test failure",
            }
            for p in oracle
        ]
        report = ev.make_report(self.data, cases, failed, 5)
        self.assertEqual(report["overall"]["errors"], 50)
        for metric in (
            "page_hit_at_k",
            "annotated_page_recall_at_k",
            "answer_token_f1",
            "abstention_accuracy",
        ):
            self.assertEqual(report["overall"]["metrics"][metric]["mean"], 0)

    def test_wrong_source_does_not_match(self):
        case = self.data["cases"][0]
        row = self.prediction(case)
        row["contexts"][0]["source"] = "unrelated.pdf"
        self.assertEqual(ev.score_case(case, row, "rag.pdf", 5)["page_hit_at_k"], 0)

    def test_multihop_ranking_duplicates_and_top_k(self):
        case = next(c for c in self.data["cases"] if c["id"] == "rag-037")
        row = self.prediction(case)
        first, second = row["contexts"]
        row["contexts"] = [
            {"source": "other.pdf", "page": 3, "content": "noise"},
            first,
            first,
            second,
        ]
        result = ev.score_case(case, row, "rag.pdf", 3)
        self.assertEqual(result["page_mrr_at_k"], 0.5)
        self.assertEqual(result["annotated_page_recall_at_k"], 0.5)
        self.assertEqual(result["unique_relevant_pages_per_k"], 1 / 3)
        result = ev.score_case(case, row, "rag.pdf", 4)
        self.assertEqual(result["annotated_page_recall_at_k"], 1)

    def test_empty_and_retrieval_only_predictions(self):
        case = self.data["cases"][0]
        row = self.prediction(case)
        row.update(answer="", abstained=None, contexts=[])
        result = ev.score_case(case, row, "rag.pdf", 5)
        self.assertEqual(result["answer_token_f1"], 0)
        self.assertEqual(result["abstention_accuracy"], 0)
        result = ev.score_case(case, self.prediction(case, "retrieval"), "rag.pdf", 5)
        self.assertIsNone(result["answer_token_f1"])
        self.assertIsNone(result["abstention_accuracy"])

    def test_unanswerable_excluded_from_retrieval(self):
        case = self.data["cases"][-1]
        result = ev.score_case(case, self.prediction(case), "rag.pdf", 5)
        self.assertIsNone(result["page_hit_at_k"])
        self.assertIsNone(result["answer_token_f1"])

    def test_refusal_with_fabrication_is_not_accepted_by_phrase_matching(self):
        row = self.prediction(self.data["cases"][-1])
        row["abstained"] = None
        row["answer"] = "I don't know. The measured latency is 42 ms."
        self.assertFalse(ev.explicit_abstention(row))
        row["answer"] = "I don't know."
        self.assertTrue(ev.explicit_abstention(row))

    def test_missing_duplicate_and_unknown_predictions_rejected(self):
        cases = self.data["cases"][:2]
        row = self.prediction(cases[0])
        with self.assertRaisesRegex(ValueError, "Missing"):
            ev.validate_predictions([row], cases)
        self.assertEqual(ev.validate_predictions([row], cases, True), [cases[1]["id"]])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            ev.validate_predictions([row, row], cases, True)
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            ev.validate_predictions([{**row, "id": "unknown"}], cases, True)

    def test_malformed_context_and_nan_latency_rejected(self):
        case = self.data["cases"][0]
        row = self.prediction(case)
        row["contexts"][0]["page"] = 0
        with self.assertRaisesRegex(ValueError, "one-based"):
            ev.validate_predictions([row], [case])
        row = self.prediction(case)
        row["latency_ms"] = float("nan")
        with self.assertRaisesRegex(ValueError, "latency"):
            ev.validate_predictions([row], [case])

    def test_adapter_converts_zero_based_pages_and_windows_paths(self):
        result = to_context(
            {"content": "text", "metadata": {"source": r"D:\data\rag.pdf", "page": 0}}
        )
        self.assertEqual(result, {"content": "text", "source": "rag.pdf", "page": 1})
        with self.assertRaises(ValueError):
            to_context({"content": "text", "metadata": {"source_file": "rag.pdf"}})

    def test_adapter_records_exactly_the_generation_retrieval(self):
        class Retriever:
            calls = 0

            def retrieve(self, query, top_k=5):
                self.calls += 1
                return [
                    {
                        "content": query,
                        "metadata": {"source_file": "rag.pdf", "page": 7},
                    }
                ]

        class Generator:
            llm = object()

            def rag_simple(self, question, retriever, llm, top_k=5):
                docs = retriever.retrieve(question, top_k=top_k)
                return docs[0]["content"]

        adapter = AppAdapter.__new__(AppAdapter)
        adapter.retriever = Retriever()
        adapter.retrieval_only = False
        adapter.generator = Generator()
        result = adapter.predict("A test question", 3)
        self.assertEqual(adapter.retriever.calls, 1)
        self.assertEqual(result["contexts"][0]["content"], result["answer"])
        self.assertEqual(result["contexts"][0]["page"], 8)
        recorder = RecordingRetriever(adapter.retriever)
        recorder.retrieve("x", top_k=3)
        self.assertEqual(recorder.calls, 1)

    def test_token_f1_is_diagnostic_and_numeric_normalization(self):
        self.assertEqual(ev.token_f1("1,536 dimensions", "1536 dimensions"), 1)
        self.assertEqual(ev.token_f1("", "anything"), 0)
        self.assertLess(
            ev.token_f1("RAG retrieves data", "RAG never retrieves data"), 1
        )

    def test_cli_score_review_export_and_stale_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, review_path = root / "predictions.jsonl", root / "reviews.jsonl"
            cases = ev.select_cases(self.data, "dev")
            predictions = [self.prediction(c) for c in cases]
            ev.write_jsonl(path, predictions)
            common = ["--predictions", str(path), "--split", "dev"]
            self.assertEqual(
                ev.main(["score", *common, "--output-dir", str(root / "report")]), 0
            )
            self.assertTrue((root / "report/per_case.csv").exists())
            self.assertEqual(
                ev.main(["review-template", *common, "--output", str(review_path)]), 0
            )
            review = ev.read_jsonl(review_path)[0]
            review.update(
                reviewer="test reviewer", correctness=2, faithfulness=2, relevance=2
            )
            ev.write_jsonl(review_path, [review])
            reviews = ev.load_reviews(review_path, {p["id"]: p for p in predictions})
            report = ev.make_report(self.data, cases, predictions, 10, reviews=reviews)
            self.assertEqual(report["human_reviewed_cases"], 1)
            self.assertEqual(report["overall"]["metrics"]["faithfulness"]["n"], 1)
            predictions[0]["answer"] = "changed answer"
            with self.assertRaisesRegex(ValueError, "different prediction"):
                ev.load_reviews(review_path, {p["id"]: p for p in predictions})
            exported = root / "ragas.jsonl"
            self.assertEqual(
                ev.main(["export-ragas", *common, "--output", str(exported)]), 0
            )
            rows = ev.read_jsonl(exported)
            self.assertEqual(
                len(rows), sum(c["expected_behavior"] == "answer" for c in cases)
            )
            self.assertTrue(all(r["reference_contexts"] for r in rows))

    def test_run_metadata_rejects_changed_predictions_or_excessive_k(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.jsonl"
            ev.write_jsonl(path, [self.prediction(self.data["cases"][0])])
            metadata = {
                "dataset_sha256": ev.file_hash(ev.DEFAULT_DATASET),
                "source_sha256": self.data["source"]["sha256"],
                "complete": True,
                "predictions_sha256": ev.file_hash(path),
                "top_k": 3,
            }
            ev.write_json(path.with_suffix(".run.json"), metadata)
            ev.verify_run_metadata(path, ev.DEFAULT_DATASET, self.data, 3)
            with self.assertRaisesRegex(ValueError, "top_k"):
                ev.verify_run_metadata(path, ev.DEFAULT_DATASET, self.data, 5)
            path.write_text(path.read_text() + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Predictions changed"):
                ev.verify_run_metadata(path, ev.DEFAULT_DATASET, self.data, 3)

    def test_run_records_failures_and_returns_nonzero(self):
        class FakeAdapter:
            settings = {"synthetic_test": True}

            def __init__(self, *args):
                pass

            def predict(self, question, k):
                raise RuntimeError("synthetic failure")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.jsonl"
            with patch("evaluation.app_adapter.AppAdapter", FakeAdapter):
                status = ev.main(["run", "--limit", "1", "--output", str(path)])
            self.assertEqual(status, 1)
            row = ev.read_jsonl(path)[0]
            self.assertIn("synthetic failure", row["error"])
            self.assertTrue(
                json.loads(path.with_suffix(".run.json").read_text())["complete"]
            )


if __name__ == "__main__":
    unittest.main()
