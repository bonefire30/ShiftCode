from __future__ import annotations

import unittest

from scripts.run_layered_evaluation_suite import load_manifest, run_suite, suite_names, validate_manifest


class TestLayeredEvaluationSuite(unittest.TestCase):
    def test_manifest_has_required_layers_and_fixture_metadata(self) -> None:
        manifest = load_manifest()
        validate_manifest(manifest)
        self.assertEqual(set(suite_names(manifest)), {"core", "features", "smoke", "wave1"})
        for suite in (manifest.get("suites") or {}).values():
            fixtures = suite.get("fixtures") or []
            self.assertTrue(fixtures)
            for fixture in fixtures:
                for key in ("id", "path", "purpose", "javaPattern", "expectedStatus", "mustNotReportSuccess"):
                    self.assertIn(key, fixture)

    def test_mock_smoke_report_has_metadata_without_real_llm(self) -> None:
        report = run_suite(suite="smoke", profile="mock", confirm_real_llm=False)
        self.assertEqual(report["suite"], "smoke")
        self.assertEqual(report["mode"], "mock")
        self.assertGreaterEqual(report["total"], 1)
        self.assertEqual(report["failed"], 0)
        for result in report["results"]:
            self.assertEqual(result["profile"], "mock")
            self.assertEqual(result["llmCallStatus"], "success")
            self.assertIn(result["conversionStatus"], {"success", "warning", "partial", "unsupported", "error"})
            self.assertIsNone(result["llm_run_metadata"]["tokenUsage"]["totalTokens"])

    def test_real_llm_requires_confirmation(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "confirm-real-llm"):
            run_suite(suite="smoke", profile="codex-proxy", confirm_real_llm=False)

    def test_real_profile_must_be_allowed_by_suite(self) -> None:
        manifest = load_manifest()
        manifest["suites"]["smoke"]["allowRealProfiles"] = ["minimax"]
        with self.assertRaisesRegex(RuntimeError, "not allowed"):
            run_suite(suite="smoke", profile="codex-proxy", confirm_real_llm=True, manifest=manifest)

    def test_wave1_mock_can_run_without_real_llm_confirmation(self) -> None:
        report = run_suite(suite="wave1", profile="mock", confirm_real_llm=False)
        self.assertEqual(report["suite"], "wave1")
        self.assertEqual(report["mode"], "mock")

    def test_features_do_not_allow_must_not_success_fixtures_to_mock_success(self) -> None:
        report = run_suite(suite="features", profile="mock", confirm_real_llm=False)
        self.assertEqual(report["failed"], 0)
        for result in report["results"]:
            if result["mustNotReportSuccess"]:
                self.assertNotEqual(result["conversionStatus"], "success")

    def test_invalid_expected_status_fails_manifest_validation(self) -> None:
        manifest = load_manifest()
        manifest["suites"]["smoke"]["fixtures"][0]["expectedStatus"] = "mixed"
        with self.assertRaisesRegex(ValueError, "expectedStatus"):
            validate_manifest(manifest)

    def test_must_not_report_success_cannot_expect_success(self) -> None:
        manifest = load_manifest()
        manifest["suites"]["features"]["fixtures"][0]["expectedStatus"] = "success"
        with self.assertRaisesRegex(ValueError, "mustNotReportSuccess"):
            validate_manifest(manifest)

    def test_real_result_fails_when_expected_status_mismatches_actual_status(self) -> None:
        manifest = load_manifest()
        fixture = manifest["suites"]["smoke"]["fixtures"][0]
        fixture["expectedStatus"] = "warning"

        def fake_stream(*_args, **_kwargs):
            yield "reviewer", {
                "llm_run_metadata": {"llmCallStatus": "success", "conversionStatus": "success"},
                "last_build_ok": True,
                "last_test_ok": True,
                "test_gen_ok": True,
                "test_quality_ok": True,
                "go_output_dir": "project_migrations/fake",
            }

        from unittest.mock import patch

        with patch("scripts.run_layered_evaluation_suite.validate_profile_runtime"), patch(
            "scripts.run_layered_evaluation_suite.stream_project_workflow",
            side_effect=fake_stream,
        ):
            report = run_suite(suite="smoke", profile="codex-proxy", confirm_real_llm=True, manifest=manifest)
        self.assertEqual(report["failed"], 1)
        self.assertIn("expected conversionStatus warning, got success", report["results"][0]["gateFailures"])

    def test_real_report_includes_project_explainability_fields(self) -> None:
        manifest = load_manifest()

        def fake_stream(*_args, **_kwargs):
            yield "reviewer", {
                "llm_run_metadata": {
                    "llmCallStatus": "success",
                    "conversionStatus": "partial",
                    "projectStatusSummary": {"success": 0, "warning": 0, "partial": 1, "unsupported": 0, "error": 0},
                    "summaryCompleteness": "complete",
                    "conversionItems": [{"id": "mod0", "status": "partial", "reasons": ["x"], "engineeringStatus": {"build": "success", "tests": "partial", "testGeneration": "partial", "testQuality": "success"}}],
                    "testFailureExplanations": ["tests are partial"],
                    "testGenerationReasons": ["generated tests are partial"],
                    "testIssueCategories": [{"category": "generated_test_compile_failure", "message": "compile failed"}],
                    "recommendedNextActions": ["inspect failing tests"],
                },
                "last_build_ok": True,
                "last_test_ok": False,
                "test_gen_ok": False,
                "test_quality_ok": True,
                "go_output_dir": "project_migrations/fake",
            }

        from unittest.mock import patch

        with patch("scripts.run_layered_evaluation_suite.validate_profile_runtime"), patch(
            "scripts.run_layered_evaluation_suite.stream_project_workflow",
            side_effect=fake_stream,
        ):
            report = run_suite(suite="features", profile="codex-proxy", confirm_real_llm=True, manifest=manifest)
        result = report["results"][0]
        self.assertIn("projectStatusSummary", result)
        self.assertEqual(result["summaryCompleteness"], "complete")
        self.assertIn("conversionItems", result)
        self.assertIn("testFailureExplanations", result)
        self.assertIn("testGenerationReasons", result)
        self.assertIn("testIssueCategories", result)
        self.assertIn("recommendedNextActions", result)


if __name__ == "__main__":
    unittest.main()
