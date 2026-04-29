from __future__ import annotations

import unittest

from conversion_status import classify_java_sources, final_conversion_status, merge_statuses


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
        self.assertTrue(any(c.status == "unsupported" and "annotation" in c.reason.lower() for c in contributions))

    def test_exception_flow_contributes_partial(self) -> None:
        contributions = classify_java_sources("void load() throws IOException { throw new IOException(); }")
        self.assertTrue(any(c.status == "partial" and "exception" in c.reason.lower() for c in contributions))

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
