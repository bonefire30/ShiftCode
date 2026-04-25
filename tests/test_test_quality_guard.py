from __future__ import annotations

import unittest

from test_quality_guard import (
    evaluate_test_quality,
    extract_prompt_contract_checklist,
)


class TestPromptChecklistExtraction(unittest.TestCase):
    def test_extracts_core_contracts(self) -> None:
        prompt = """
Requirements:
- Process() returns "credit", and must call LogTransaction() before return.
- field Id must be readable (exported).
- RunPayment calls p.Process().
"""
        checklist = extract_prompt_contract_checklist(prompt)
        self.assertIn("must call LogTransaction() before return", checklist)
        self.assertIn("returns 'credit'", checklist)
        self.assertIn("field Id must be readable/exported", checklist)
        self.assertIn("RunPayment calls p.Process()", checklist)


class TestQualityEvaluation(unittest.TestCase):
    def test_flags_over_specified_panic_and_nil(self) -> None:
        prompt = 'Process() returns "credit".'
        checklist = extract_prompt_contract_checklist(prompt)
        failures, _warnings, ok = evaluate_test_quality(
            module_name="mod0",
            prompt_text=prompt,
            prompt_contract_checklist=checklist,
            java_sources={"source.java": "class X { String Process(){ return \"credit\"; } }"},
            go_sources={"source.java": 'func Process() string { return "credit" }'},
            generated_tests={
                "source.java": """
func TestRunPaymentNil(t *testing.T) {
    defer func() { _ = recover() }()
    _ = RunPayment(nil)
}
"""
            },
        )
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("over_specified_tests:") for f in failures))

    def test_flags_missing_required_assertion(self) -> None:
        prompt = """
Requirements:
- Process() returns "credit" and must call LogTransaction() before return.
"""
        checklist = extract_prompt_contract_checklist(prompt)
        failures, _warnings, ok = evaluate_test_quality(
            module_name="mod1",
            prompt_text=prompt,
            prompt_contract_checklist=checklist,
            java_sources={"source.java": "class X { void LogTransaction(){} String Process(){ return \"credit\"; } }"},
            go_sources={"source.java": "func (x *X) Process() string { x.LogTransaction(); return \"credit\" }"},
            generated_tests={
                "source.java": """
func TestProcessReturn(t *testing.T) {
    if got := p.Process(); got != "credit" { t.Fatal(got) }
}
"""
            },
        )
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("missing_required_assertions:") for f in failures))

    def test_allows_standard_error_nil_checks(self) -> None:
        failures, _warnings, ok = evaluate_test_quality(
            module_name="mod2",
            prompt_text='Load() returns "ok".',
            prompt_contract_checklist=[],
            java_sources={"source.java": "class X { String load(){ return \"ok\"; } }"},
            go_sources={"source.go": "func Load() (string, error) { return \"ok\", nil }"},
            generated_tests={
                "source_test.go": """
func TestLoad(t *testing.T) {
    got, err := Load()
    if err != nil { t.Fatal(err) }
    if got != "ok" { t.Fatal(got) }
}
"""
            },
        )
        self.assertTrue(ok)
        self.assertEqual([], failures)

    def test_reports_unsupported_nil_input_line(self) -> None:
        failures, _warnings, ok = evaluate_test_quality(
            module_name="mod3",
            prompt_text='Load() returns "ok".',
            prompt_contract_checklist=[],
            java_sources={"source.java": "class X { String load(){ return \"ok\"; } }"},
            go_sources={"source.go": "func Load(v any) string { return \"ok\" }"},
            generated_tests={
                "source_test.go": """
func TestLoadNil(t *testing.T) {
    _ = Load(nil)
}
"""
            },
        )
        self.assertFalse(ok)
        self.assertTrue(any("source_test.go:3" in f for f in failures))


if __name__ == "__main__":
    unittest.main()
