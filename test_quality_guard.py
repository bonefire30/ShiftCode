"""
Lightweight prompt-contract extraction and generated-test quality checks.
"""

from __future__ import annotations

import re


def extract_prompt_contract_checklist(prompt_text: str) -> list[str]:
    """
    Extract a minimal requirement checklist from migration prompt text.
    """
    text = (prompt_text or "").strip()
    if not text:
        return []
    checklist: list[str] = []
    lower = text.lower()

    # `must call X before return` style requirements.
    for call in re.findall(
        r"(?i)must\s+call\s+`?([a-zA-Z_][\w.]*(?:\(\))?)`?\s+before\s+return",
        text,
    ):
        checklist.append(f"must call {call} before return")

    # `returns "foo"` style return contracts.
    for value in re.findall(
        r"(?i)returns?\s+[\"'`]([^\"'`]+)[\"'`]",
        text,
    ):
        checklist.append(f"returns '{value}'")

    # `field Id readable/exported` style.
    if "field id" in lower and (
        "read" in lower or "exported" in lower or "exposed" in lower
    ):
        checklist.append("field Id must be readable/exported")

    # `RunPayment calls p.Process()` style delegation contract.
    if re.search(r"(?i)\brunpayment\b.*\bcalls?\b.*\bprocess\b", text):
        checklist.append("RunPayment calls p.Process()")

    # Keep deterministic order, remove duplicates.
    out: list[str] = []
    seen: set[str] = set()
    for item in checklist:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _join_sources(src: dict[str, str]) -> str:
    return "\n".join((v or "") for v in src.values())


def _has_any_token(text: str, tokens: list[str]) -> bool:
    return any(t in text for t in tokens)


def _is_contract_covered(check_item: str, tests_text_lc: str) -> bool:
    item = (check_item or "").strip().lower()
    if not item:
        return True

    if item.startswith("must call ") and " before return" in item:
        target = item[len("must call ") :].split(" before return", 1)[0].strip()
        target_name = target.replace("()", "").strip()
        # Require target method and evidence around call-order/delegation verification.
        order_hints = ["call", "called", "before", "order", "delegate", "process"]
        return target_name in tests_text_lc and _has_any_token(tests_text_lc, order_hints)

    if item.startswith("returns '") and item.endswith("'"):
        value = item[len("returns '") : -1]
        return value in tests_text_lc

    if item == "field id must be readable/exported":
        return ".id" in tests_text_lc or " id " in tests_text_lc or "got id" in tests_text_lc

    if item == "runpayment calls p.process()":
        return "runpayment" in tests_text_lc and "process" in tests_text_lc

    # Fallback: simple keyword containment.
    words = [w for w in re.split(r"[^a-z0-9_]+", item) if len(w) >= 3]
    if not words:
        return True
    return all(w in tests_text_lc for w in words)


def evaluate_test_quality(
    *,
    module_name: str,
    prompt_text: str,
    prompt_contract_checklist: list[str],
    java_sources: dict[str, str],
    go_sources: dict[str, str],
    generated_tests: dict[str, str],
) -> tuple[list[str], list[str], bool]:
    """
    Return (failures, warnings, quality_ok).
    Failures are prefixed with:
    - over_specified_tests:
    - missing_required_assertions:
    """
    prompt = prompt_text or ""
    java_text = _join_sources(java_sources)
    go_text = _join_sources(go_sources)
    tests_text = _join_sources(generated_tests)

    combined_lc = f"{prompt}\n{java_text}\n{go_text}".lower()
    tests_lc = tests_text.lower()

    failures: list[str] = []
    warnings: list[str] = []

    # Over-spec checks for panic/recover/nil-like assertions not explicitly grounded.
    suspicious_hits: list[str] = []
    if _has_any_token(tests_lc, ["panic", "recover("]):
        allows_panic = _has_any_token(
            combined_lc,
            ["panic", "recover", "throws", "exception", "must panic", "expected panic"],
        )
        if not allows_panic:
            suspicious_hits.append("panic/recover assertions without prompt or source basis")

    if _has_any_token(tests_lc, ["(nil)", " nil", "== nil", "!= nil"]):
        allows_nil = _has_any_token(combined_lc, ["nil", " null", "null ", "nullable", "non-nil"])
        if not allows_nil:
            suspicious_hits.append("nil assertions without prompt or source basis")

    if suspicious_hits:
        failures.append(
            f"over_specified_tests: module {module_name}: " + "; ".join(suspicious_hits)
        )

    missing_items = [
        item
        for item in (prompt_contract_checklist or [])
        if not _is_contract_covered(item, tests_lc)
    ]
    if missing_items:
        failures.append(
            f"missing_required_assertions: module {module_name}: missing {', '.join(missing_items)}"
        )

    # Optional low-severity warning for very short tests with non-empty checklist.
    if prompt_contract_checklist and len(tests_text.strip()) < 120:
        warnings.append(f"module {module_name}: generated test text is unusually short")

    return failures, warnings, not failures


__all__ = [
    "extract_prompt_contract_checklist",
    "evaluate_test_quality",
]
