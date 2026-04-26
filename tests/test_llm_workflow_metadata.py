from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from workflow import run_module_agent, run_test_gen_module_agent


class TestLLMWorkflowMetadata(unittest.TestCase):
    def _new_case_dir(self) -> Path:
        base = Path("project_migrations") / "_tmp_unit_tests"
        base.mkdir(parents=True, exist_ok=True)
        case = base / f"llm_case_{uuid.uuid4().hex[:8]}"
        case.mkdir(parents=True, exist_ok=True)
        return case

    def test_module_agent_mock_reports_profile_metadata_without_api_call(self) -> None:
        root = self._new_case_dir()
        try:
            with patch.dict(os.environ, {"JAVA2GO_LLM_MOCK": "1"}, clear=True):
                out, tokens, ok, artifacts, meta = run_module_agent(
                    module_dep_order=["Example.java"],
                    java_sources={"Example.java": "class Example {}"},
                    go_output_dir=root,
                    go_package_map={"Example.java": "main"},
                    llm_profile="codex-proxy",
                )

            self.assertEqual(out, {})
            self.assertEqual(tokens, 0)
            self.assertFalse(ok)
            self.assertEqual(artifacts["effective_count"], 0)
            self.assertEqual(meta["profile"], "codex-proxy")
            self.assertEqual(meta["provider"], "openai-compatible")
            self.assertEqual(meta["model"], "GPT-5.3 Codex")
            self.assertEqual(meta["llmCallStatus"], "success")
            self.assertNotIn("conversionStatus", meta)
            self.assertEqual(meta["promptVersion"], "project-migration-v1")
            self.assertIsNone(meta["tokenUsage"]["totalTokens"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_test_gen_mock_reports_missing_tests_and_metadata(self) -> None:
        root = self._new_case_dir()
        try:
            with patch.dict(os.environ, {"JAVA2GO_LLM_MOCK": "1"}, clear=True):
                out, tokens, ok, expected, generated, failures, artifacts, meta = run_test_gen_module_agent(
                    module_dep_order=["Example.java"],
                    java_sources={"Example.java": "class Example {}"},
                    go_output_dir=root,
                    go_package_map={"Example.java": "main"},
                    expected_go_files=["example.go"],
                    llm_profile="deepseek",
                )

            self.assertEqual(out, {})
            self.assertEqual(tokens, 0)
            self.assertFalse(ok)
            self.assertEqual(expected, 1)
            self.assertEqual(generated, 0)
            self.assertTrue(failures)
            self.assertEqual(artifacts["expected_output_files"], ["example_test.go"])
            self.assertEqual(meta["profile"], "deepseek")
            self.assertEqual(meta["model"], "deepseek-v4-flash")
            self.assertIsNone(meta["tokenUsage"]["totalTokens"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_llm_call_status_is_separate_from_conversion_status(self) -> None:
        from multi_agent_workflow import _llm_run_metadata_with_conversion

        state = {
            "last_build_ok": False,
            "last_test_ok": False,
            "test_gen_ok": False,
            "test_quality_ok": False,
            "llm_run_metadata": {"calls": [{"llmCallStatus": "success"}]},
        }
        meta = _llm_run_metadata_with_conversion(state)
        self.assertEqual(meta["llmCallStatus"], "success")
        self.assertEqual(meta["conversionStatus"], "partial")

        error_state = {**state, "llm_run_metadata": {"calls": [{"llmCallStatus": "error"}]}}
        error_meta = _llm_run_metadata_with_conversion(error_state)
        self.assertEqual(error_meta["llmCallStatus"], "error")
        self.assertEqual(error_meta["conversionStatus"], "partial")


if __name__ == "__main__":
    unittest.main()
