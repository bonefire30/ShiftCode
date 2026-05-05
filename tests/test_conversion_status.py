from __future__ import annotations

import unittest

from conversion_status import (
    classify_java_sources,
    final_conversion_status,
    merge_statuses,
    status_reason_details,
)


class TestConversionStatus(unittest.TestCase):
    def test_merge_status_severity(self) -> None:
        self.assertEqual(merge_statuses("success", "warning"), "warning")
        self.assertEqual(merge_statuses("warning", "partial"), "partial")
        self.assertEqual(merge_statuses("partial", "unsupported"), "unsupported")
        self.assertEqual(merge_statuses("unsupported", "error"), "error")

    def test_stream_pipeline_contributes_unsupported(self) -> None:
        contributions = classify_java_sources("items.stream().map(x -> x.name()).toList();")
        self.assertTrue(any(c.status == "unsupported" and "stream" in c.reason.lower() for c in contributions))

    def test_generics_contributes_unsupported(self) -> None:
        contributions = classify_java_sources("public class Result<T> { T value; }")
        self.assertTrue(any(c.status == "unsupported" and "generic" in c.reason.lower() for c in contributions))

    def test_framework_annotation_contributes_unsupported(self) -> None:
        contributions = classify_java_sources("@Service\npublic class UserService {}")
        details = status_reason_details(contributions)
        self.assertTrue(
            any(
                d["status"] == "unsupported"
                and d["category"] == "config_dynamic_or_framework_unsupported"
                for d in details
            )
        )

    def test_exception_flow_contributes_partial(self) -> None:
        contributions = classify_java_sources("void load() throws IOException { throw new IOException(); }")
        self.assertTrue(any(c.status == "partial" and "exception" in c.reason.lower() for c in contributions))

    def test_validation_throw_error_return_category(self) -> None:
        contributions = classify_java_sources("if (age < 0) { throw new IllegalArgumentException(\"age cannot be negative\"); }")
        details = status_reason_details(contributions)
        self.assertTrue(any(d["category"] == "validation_throw_error_return" and d["status"] == "partial" for d in details))

    def test_single_operation_fallback_flow_category(self) -> None:
        contributions = classify_java_sources("try { return fetch(primary); } catch (RuntimeException e) { return \"fallback\"; }")
        details = status_reason_details(contributions)
        self.assertTrue(any(d["category"] == "single_operation_fallback_flow" and d["status"] == "partial" for d in details))

    def test_retry_loop_manual_review_category(self) -> None:
        contributions = classify_java_sources("while (true) { try { return task.run(); } catch (Exception e) { attempt++; if (attempt >= maxAttempts) { throw e; } } }")
        details = status_reason_details(contributions)
        self.assertTrue(any(d["category"] == "retry_loop_manual_review" and d["status"] == "partial" for d in details))

    def test_parse_failure_error_return_category(self) -> None:
        contributions = classify_java_sources("try { return Integer.parseInt(raw); } catch (NumberFormatException e) { throw new IllegalArgumentException(\"timeout is invalid\"); }")
        details = status_reason_details(contributions)
        self.assertTrue(any(d["category"] == "parse_failure_error_return" and d["status"] == "partial" for d in details))

    def test_illegal_argument_constructor_precondition_does_not_contribute_partial(self) -> None:
        contributions = classify_java_sources(
            "public LRUCache(int capacity) { if (capacity < 1) { throw new IllegalArgumentException(\"capacity must be >= 1\"); } }"
        )
        self.assertFalse(any(c.status == "partial" and "exception" in c.reason.lower() for c in contributions))

    def test_throws_ioexception_contributes_partial(self) -> None:
        contributions = classify_java_sources(
            "public static AppConfig parse(InputStream in) throws IOException { return null; }"
        )
        self.assertTrue(any(c.status == "partial" and "exception" in c.reason.lower() for c in contributions))

    def test_config_parser_contributes_warning(self) -> None:
        contributions = classify_java_sources("Config parseConfig(String text) { return new Config(); }")
        self.assertTrue(any(c.status == "warning" and "parser" in c.reason.lower() for c in contributions))

    def test_config_map_lookup_contributes_specific_warning_category(self) -> None:
        contributions = classify_java_sources("String host = config.get(\"host\");")
        details = status_reason_details(contributions)
        self.assertTrue(any(d["category"] == "config_map_lookup_missing_key_caveat" and d["status"] == "warning" for d in details))

    def test_config_default_fallback_contributes_specific_warning_category(self) -> None:
        contributions = classify_java_sources("String port = config.getOrDefault(\"port\", \"8080\");")
        details = status_reason_details(contributions)
        self.assertTrue(any(d["category"] == "config_default_value_fallback" and d["status"] == "warning" for d in details))

    def test_config_required_field_validation_contributes_partial_category(self) -> None:
        contributions = classify_java_sources("if (!config.containsKey(\"host\") || config.get(\"host\") == null) { throw new IllegalArgumentException(\"host is required\"); }")
        details = status_reason_details(contributions)
        self.assertTrue(any(d["category"] == "config_required_field_error_return" and d["status"] == "partial" for d in details))

    def test_config_parse_failure_contributes_partial_category(self) -> None:
        contributions = classify_java_sources("return Integer.parseInt(config.get(\"timeout\"));")
        details = status_reason_details(contributions)
        self.assertTrue(any(d["category"] == "config_parse_failure_error_return" and d["status"] == "partial" for d in details))

    def test_framework_config_annotation_contributes_unsupported_category(self) -> None:
        contributions = classify_java_sources("@ConfigurationProperties(prefix = \"app\")\nclass AppConfig {}")
        details = status_reason_details(contributions)
        self.assertTrue(any(d["category"] == "config_dynamic_or_framework_unsupported" and d["status"] == "unsupported" for d in details))

    def test_build_success_cannot_override_known_limitation(self) -> None:
        contributions = classify_java_sources("items.stream().count();")
        status = final_conversion_status(
            llm_call_status="success",
            engineering_status={"build": True, "tests": True, "testGeneration": True, "testQuality": True},
            contributions=contributions,
        )
        self.assertEqual(status, "unsupported")

    def test_llm_error_forces_error(self) -> None:
        status = final_conversion_status(
            llm_call_status="error",
            engineering_status={"build": True, "tests": True, "testGeneration": True, "testQuality": True},
            contributions=[],
        )
        self.assertEqual(status, "error")


if __name__ == "__main__":
    unittest.main()
