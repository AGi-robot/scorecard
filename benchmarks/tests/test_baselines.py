"""Run with python -m unittest discover -s benchmarks/tests -v.

Set IFBENCH_OFFICIAL and LCB_OFFICIAL to enable pinned upstream scorer fixtures.
Fixture results are temporary synthetic checks, never benchmark scores.
"""
import argparse
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import baseline_common as common


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.args = argparse.Namespace(stage="all", output=self.root, n=1, limit=0,
                                       max_tokens=50, temperature=0, model="fixture",
                                       base_url="http://localhost:8000/v1", request_timeout=1)
        self.data = self.root / "data.jsonl"
        self.data.write_text('{"id":"x"}\n')

    def test_manifest_rejects_model_or_data_changes(self):
        common.initialize(self.args, {}, self.data, 1)
        self.args.model = "other"
        with self.assertRaises(ValueError):
            common.initialize(self.args, {}, self.data, 1)
        self.args.model = "fixture"
        self.data.write_text('{}\n')
        with self.assertRaises(ValueError):
            common.initialize(self.args, {}, self.data, 1)

    def test_credential_url_rejected(self):
        self.args.base_url = "https://user:secret@example.com/v1"
        with self.assertRaises(ValueError):
            common.initialize(self.args, {}, self.data, 1)

    def test_partial_generation_resumes_only_successes(self):
        tasks = [{"id": "a"}, {"id": "b"}]
        with patch.object(common, "complete", side_effect=["first", RuntimeError("offline")]):
            with self.assertRaises(RuntimeError):
                common.responses(self.args, tasks, lambda t: [])
        self.assertEqual(len(common.read_jsonl(self.root / "responses.jsonl")), 1)
        with patch.object(common, "complete", return_value="second") as request:
            self.assertEqual(common.responses(self.args, tasks, lambda t: []), [["first"], ["second"]])
            self.assertEqual(request.call_count, 1)

    def test_incomplete_and_duplicate_samples_never_score(self):
        self.args.stage = "score"
        with self.assertRaises(ValueError):
            common.responses(self.args, [{"id": "a"}], lambda t: [])
        row = json.dumps({"id": "a", "sample": 0, "response": "text"}) + "\n"
        (self.root / "responses.jsonl").write_text(row * 2)
        with self.assertRaises(ValueError):
            common.responses(self.args, [{"id": "a"}], lambda t: [])

    def test_truncated_completion_is_not_saved(self):
        response = io.BytesIO(json.dumps({"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]}).encode())
        with patch.object(common.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(ValueError):
                common.responses(self.args, [{"id": "a"}], lambda t: [])
        self.assertEqual((self.root / "responses.jsonl").read_text(), "")

    def test_bounded_run_keeps_capped_text_and_continues_without_retry(self):
        capped = {"choices": [{"message": {"content": "partial answer",
                   "reasoning_content": "private reasoning"}, "finish_reason": "length"}],
                  "usage": {"completion_tokens": 50}}
        stopped = {"choices": [{"message": {"content": "finished"}, "finish_reason": "stop"}]}
        with patch.object(common.urllib.request, "urlopen", side_effect=[
                io.BytesIO(json.dumps(capped).encode()), io.BytesIO(json.dumps(stopped).encode())]) as request:
            outputs = common.responses(self.args, [{"id": "a"}, {"id": "b"}],
                                       lambda t: [{"role": "user", "content": t["id"]}], bounded=True)
        self.assertEqual(outputs, [["partial answer"], ["finished"]])
        self.assertEqual(request.call_count, 2)
        sent = json.loads(request.call_args_list[0].args[0].data)
        self.assertEqual(sent["messages"], [{"role": "user", "content": "a"}])
        self.assertEqual(sent["max_tokens"], 50)
        record = common.read_jsonl(self.root / "responses.jsonl")[0]
        self.assertEqual(record["finish_reason"], "length")
        self.assertEqual(record["usage"]["completion_tokens"], 50)
        self.assertEqual(record["reasoning_content"], "private reasoning")

    def test_bounded_timeout_continues_and_resumes_without_reasking(self):
        completion = {"choices": [{"message": {"content": "next answer"}, "finish_reason": "stop"}]}
        for error in (TimeoutError("timed out"), common.urllib.error.URLError(TimeoutError())):
            with self.subTest(error=type(error).__name__):
                path = self.root / "responses.jsonl"
                path.unlink(missing_ok=True)
                with patch.object(common.urllib.request, "urlopen", side_effect=[
                        error, io.BytesIO(json.dumps(completion).encode())]):
                    output = common.responses(self.args, [{"id": "a"}, {"id": "b"}],
                                              lambda t: [], bounded=True)
                self.assertEqual(output, [[""], ["next answer"]])
                self.assertEqual(common.read_jsonl(path)[0]["finish_reason"], "timeout")
                with patch.object(common, "complete") as request:
                    self.assertEqual(common.responses(self.args, [{"id": "a"}, {"id": "b"}],
                                                      lambda t: [], bounded=True), output)
                    request.assert_not_called()

    def test_bounded_reasoning_only_response_scores_empty_answer(self):
        payload = {"choices": [{"message": {"content": None, "reasoning_content": "still thinking"},
                                "finish_reason": "length"}]}
        with patch.object(common.urllib.request, "urlopen",
                          return_value=io.BytesIO(json.dumps(payload).encode())):
            self.assertEqual(common.responses(self.args, [{"id": "a"}], lambda t: [], bounded=True), [[""]])

    def test_bounded_connection_failure_is_not_a_scored_timeout(self):
        with patch.object(common.urllib.request, "urlopen",
                          side_effect=common.urllib.error.URLError(ConnectionRefusedError())):
            with self.assertRaises(common.urllib.error.URLError):
                common.responses(self.args, [{"id": "a"}], lambda t: [], bounded=True)
        self.assertEqual((self.root / "responses.jsonl").read_text(), "")

    def test_ifbench_default_budgets_and_explicit_overrides(self):
        import ifbench_baseline as runner
        for model, tokens, timeout in [("ministral-3-8b-uncensored", 4096, 600),
                                       ("swift15-qwen3.8-27b-local", 8192, 1200)]:
            args = argparse.Namespace(model=model, max_tokens=None, request_timeout=None)
            runner.configure_limits(args)
            self.assertEqual((args.max_tokens, args.request_timeout), (tokens, timeout))
        args = argparse.Namespace(model="ministral", max_tokens=1000, request_timeout=90)
        runner.configure_limits(args)
        self.assertEqual((args.max_tokens, args.request_timeout), (1000, 90))

    def test_ifbench_timeout_changes_cannot_resume_old_manifest(self):
        protocol = {"generation_policy": "bounded-v1", "request_timeout_seconds": 600}
        common.initialize(self.args, protocol, self.data, 1)
        with self.assertRaises(ValueError):
            common.initialize(self.args, {**protocol, "request_timeout_seconds": 1200}, self.data, 1)

    def test_scorecard_keeps_suites_separate_and_excludes_smoke(self):
        import scorecard_all
        suites = [("ifbench", "IFBench single-turn"), ("ifbench", "IFBench multi-turn"),
                  ("livecodebench", "LiveCodeBench release_v6")]
        for directory, name in suites:
            for full in (False, True):
                out = self.root / directory / "results" / (name + str(full))
                out.mkdir(parents=True)
                common.write_json(out / "summary.json", {
                    "suite": name, "full_run": full, "model": "fixture", "n": 10,
                    "prompt_loose": 0.5, "prompt_strict": 0.4, "pass@1": 0.3, "pass@5": 0.6})
        with patch.object(scorecard_all, "HERE", self.root):
            rows = scorecard_all.rows()
        rows.sort(key=lambda r: [name for _, name in suites].index(r["bench"]))
        self.assertEqual([r["bench"] for r in rows], [name for _, name in suites])
        self.assertEqual([r["strict"] for r in rows], ["50.0", "50.0", "30.0"])

    def test_chatbot_loser_and_tie_are_counted(self):
        import scorecard_all
        out = self.root / "grace_chatbot_eval/results"
        out.mkdir(parents=True)
        vote = {"left": "winner", "right": "loser", "script": "one", "overall": "A"}
        (out / "fixture_votes.jsonl").write_text(json.dumps(vote) + "\n")
        with patch.object(scorecard_all, "HERE", self.root):
            result = {r["model"]: r for r in scorecard_all.rows()}
        self.assertEqual(result["winner"]["loose"], "100% win")
        self.assertEqual(result["loser"]["loose"], "0% win")
        self.assertEqual(result["loser"]["strict"], "Elo 1484")
        vote["overall"] = "tie"
        (out / "fixture_votes.jsonl").write_text(json.dumps(vote) + "\n")
        with patch.object(scorecard_all, "HERE", self.root):
            self.assertTrue(all(r["loose"] == "50% win" for r in scorecard_all.rows()))

    def test_bfcl_v4_mind_adapter_propagates_endpoint_failure(self):
        sys.path.insert(0, str(common.HERE / "bfcl"))
        import mind_memory_run as runner

        error = runner.urllib.error.HTTPError(
            "http://localhost/v1/chat/completions", 503, "unavailable", {},
            io.BytesIO(b"fixture endpoint unavailable"),
        )
        with patch.object(runner.urllib.request, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                runner.completion(
                    "http://localhost/v1", "fixture", "EMPTY",
                    [{"role": "user", "content": "fixture"}], 32, 1,
                )


@unittest.skipUnless(os.environ.get("IFBENCH_OFFICIAL"), "set IFBENCH_OFFICIAL for official fixture")
class IFBenchOfficialTests(unittest.TestCase):
    def test_capped_answer_and_timeout_reach_official_scorer(self):
        import ifbench_baseline as runner
        good = " ".join(["kaleidoscope"] + ["nebula"] * 2 + ["whisper"] * 3 + ["labyrinth"] * 5 + ["paradox"] * 7)
        with tempfile.TemporaryDirectory() as directory:
            argv = ["ifbench_run", "--official", os.environ["IFBENCH_OFFICIAL"],
                    "--output", directory, "--limit", "2", "--model", "ministral-fixture",
                    "--base-url", "http://localhost:8000/v1"]
            with patch.object(sys, "argv", argv), patch.object(common, "complete", side_effect=[
                    {"response": good, "finish_reason": "length"},
                    {"response": "", "finish_reason": "timeout"}]):
                runner.run()
            result = json.loads((Path(directory) / "summary.json").read_text())
            self.assertEqual(result["prompt_strict"], 0.5)
            self.assertEqual(result["generation"], {"token_limited": 1, "timed_out": 1, "empty_answers": 1})
            self.assertEqual(result["max_tokens"], 4096)
            self.assertFalse(result["full_run"])

    def test_single_turn_official_positive_and_negative(self):
        import ifbench_baseline as runner
        runner.prepare_nltk()
        sys.path.insert(0, os.environ["IFBENCH_OFFICIAL"])
        import evaluation_lib as evaluator
        inp = evaluator.read_prompt_list(str(Path(os.environ["IFBENCH_OFFICIAL"]) / "data/IFBench_test.jsonl"))[0]
        good = " ".join(["kaleidoscope"] + ["nebula"] * 2 + ["whisper"] * 3 + ["labyrinth"] * 5 + ["paradox"] * 7)
        for name in ("strict", "loose"):
            fn = getattr(evaluator, "test_instruction_following_" + name)
            self.assertTrue(fn(inp, {inp.prompt: good}).follow_all_instructions)
            self.assertFalse(fn(inp, {inp.prompt: "incorrect"}).follow_all_instructions)

    def test_multiturn_preserves_released_history_and_scores_final_turn(self):
        import ifbench_baseline as runner
        import pyarrow.parquet as pq
        path = common.HERE / ".cache" / f"ifbench-multiturn-{runner.MULTITURN_REVISION}.parquet"
        if not path.is_file():
            self.skipTest("prepare the pinned multi-turn dataset to run this fixture")
        expected = pq.read_table(path).to_pylist()[0]["messages"]
        with tempfile.TemporaryDirectory() as directory:
            argv = ["ifbench_run", "--official", os.environ["IFBENCH_OFFICIAL"],
                    "--output", directory, "--limit", "1", "--model", "fixture",
                    "--base-url", "http://localhost:8000/v1"]
            with patch.object(sys, "argv", argv), patch.object(common, "complete", return_value={
                    "response": "Galaxies sparkle.", "finish_reason": "stop"}) as request:
                runner.run(multiturn=True)
            self.assertEqual(request.call_args.args[1], expected)
            result = json.loads((Path(directory) / "summary.json").read_text())
            self.assertEqual(result["prompt_strict"], 1)
            self.assertFalse(result["full_run"])


@unittest.skipUnless(os.environ.get("LCB_OFFICIAL"), "set LCB_OFFICIAL for official fixture")
class LiveCodeBenchOfficialTests(unittest.TestCase):
    def test_adapter_indexes_all_release_files_and_scores_subset(self):
        sys.path.insert(0, str(common.HERE / "livecodebench"))
        import livecodebench_run as runner
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for i in range(6):
                row = dict(question_title="fixture", question_content="Echo a line", platform="atcoder",
                           question_id=str(i), contest_id="fixture", contest_date="2025-01-01T00:00:00",
                           starter_code="", difficulty="easy", public_test_cases=json.dumps([
                               {"input": "hello\n", "output": "hello\n", "testtype": "stdin"}]),
                           private_test_cases="[]", metadata="{}")
                path = root / ("test.jsonl" if i == 0 else f"test{i+1}.jsonl")
                path.write_text(json.dumps(row) + "\n")
                paths.append(path)
            argv = ["livecodebench_run", "--official", os.environ["LCB_OFFICIAL"],
                    "--output", str(root / "results"), "--limit", "1", "--model", "fixture",
                    "--base-url", "http://localhost:8000/v1"]
            with patch.object(sys, "argv", argv), patch.object(runner, "download", side_effect=paths), \
                    patch.object(common, "complete", return_value="```python\nprint(input())\n```"), \
                    patch.object(runner, "HERE", root):
                (root / ".cache" / runner.DATA_REVISION).mkdir(parents=True)
                runner.main()
            manifest = json.loads((root / "results/manifest.json").read_text())
            result = json.loads((root / "results/summary.json").read_text())
            self.assertEqual(manifest["total"], 6)
            self.assertEqual(result["pass@1"], 1)
            self.assertFalse(result["full_run"])

    def test_prompt_extraction_and_official_pass_at_k(self):
        sys.path.insert(0, os.environ["LCB_OFFICIAL"])
        previous = os.getcwd()
        os.chdir(os.environ["LCB_OFFICIAL"])
        self.addCleanup(os.chdir, previous)
        from lcb_runner.benchmarks.code_generation import CodeGenerationProblem
        from lcb_runner.prompts.code_generation import format_prompt_generation
        from lcb_runner.utils.extraction_utils import extract_code
        from lcb_runner.lm_styles import LMStyle
        from lcb_runner.evaluation import codegen_metrics
        row = dict(question_title="fixture", question_content="Echo a line", platform="atcoder",
                   question_id="fixture", contest_id="fixture", contest_date="2025-01-01T00:00:00",
                   starter_code="", difficulty="easy", public_test_cases=json.dumps([
                       {"input": "hello\n", "output": "hello\n", "testtype": "stdin"}]),
                   private_test_cases="[]", metadata="{}")
        problem = CodeGenerationProblem(**row)
        messages = format_prompt_generation(problem, LMStyle.OpenAIChat)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("Echo a line", messages[1]["content"])
        good = extract_code("```python\nprint(input())\n```", LMStyle.OpenAIChat)
        bad = extract_code("```python\nprint('wrong')\n```", LMStyle.OpenAIChat)
        metrics = codegen_metrics([problem.get_evaluation_sample()] * 2, [[good] * 10, [bad] * 10],
                                  k_list=[1, 5, 10], num_process_evaluate=1, timeout=6)
        for name in ("pass@1", "pass@5", "pass@10"):
            self.assertEqual(metrics[0][name], 0.5)


if __name__ == "__main__":
    unittest.main()
