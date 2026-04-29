"""Conversion status classification helpers.

The classifier is intentionally conservative: engineering validation can prove
that generated Go builds/tests pass, but it cannot upgrade known unsupported or
partial Java features to success.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


VALID_STATUSES = {"success", "warning", "partial", "unsupported", "error"}
STATUS_SEVERITY = {
    "success": 0,
    "warning": 1,
    "partial": 2,
    "unsupported": 3,
    "error": 4,
}


@dataclass(frozen=True)
class StatusContribution:
    status: str
    reason: str
    source: str = "classifier"


def merge_statuses(*statuses: str | None) -> str:
    merged = "success"
    for status in statuses:
        if not status:
            continue
        if status not in STATUS_SEVERITY:
            raise ValueError(f"invalid conversion status: {status!r}")
        if STATUS_SEVERITY[status] > STATUS_SEVERITY[merged]:
            merged = status
    return merged


def classify_java_sources(java_sources: dict[str, str] | list[str] | str) -> list[StatusContribution]:
    if isinstance(java_sources, str):
        items = [("source.java", java_sources)]
    elif isinstance(java_sources, dict):
        items = list(java_sources.items())
    else:
        items = [(f"source_{idx}.java", text) for idx, text in enumerate(java_sources)]

    contributions: list[StatusContribution] = []
    seen: set[tuple[str, str]] = set()

    def add(status: str, reason: str, source: str) -> None:
        key = (status, reason)
        if key not in seen:
            contributions.append(StatusContribution(status=status, reason=reason, source=source))
            seen.add(key)

    for path, text_raw in items:
        text = text_raw or ""
        compact = re.sub(r"\s+", " ", text)
        if re.search(r"\.\s*stream\s*\(", text) or re.search(r"\bStream\s*<", text):
            add("unsupported", "Detected Java stream pipeline; stream pipelines are currently unsupported.", path)
        if re.search(r"\bclass\s+\w+\s*<[^>]+>", text) or re.search(r"\binterface\s+\w+\s*<[^>]+>", text) or re.search(r"\b(?:public|private|protected|static|final|\s)+<[^>]+>\s+\w+\s*\(", text):
            add("unsupported", "Detected Java generics; generic type semantics require explicit mapping and are currently unsupported.", path)
        if re.search(r"^\s*@(?:Service|Component|Repository|Controller|RestController|Autowired|Bean|Entity|Table|Transactional)\b", text, re.MULTILINE):
            add("unsupported", "Detected framework annotation; annotation behavior depends on framework runtime behavior.", path)
        has_checked_throws = bool(
            re.search(
                r"\bthrows\s+(?:[\w.]+\s*,\s*)*(?:IOException|SQLException|ParseException|Exception|Throwable|ReflectiveOperationException|ClassNotFoundException|InterruptedException)\b",
                text,
            )
        )
        has_catch = bool(re.search(r"\bcatch\s*\(", text))
        has_retry_error_flow = bool(
            re.search(r"\b(retry|backoff|attempt|recover|fallback)\b", compact, re.IGNORECASE)
            and (has_checked_throws or has_catch or re.search(r"\bthrow\s+new\s+\w+", text))
        )
        if has_checked_throws or has_catch or has_retry_error_flow:
            add("partial", "Detected Java exception flow; Go error-return design requires manual review.", path)
        if re.search(r"\bparse\w*\s*\(", compact, re.IGNORECASE) or re.search(r"\bObjectMapper\b|\bJson\b|\bJSON\b", text):
            add("warning", "Detected parser/config behavior; defaults and error paths may require review.", path)
    return contributions


def status_reasons(contributions: list[StatusContribution]) -> list[str]:
    return [c.reason for c in contributions]


def classifier_status(contributions: list[StatusContribution]) -> str:
    return merge_statuses(*(c.status for c in contributions))


def final_conversion_status(
    *,
    llm_call_status: str | None,
    engineering_status: dict[str, Any],
    contributions: list[StatusContribution],
    fatal: str | None = None,
) -> str:
    if fatal:
        return "error"
    execution_status = "error" if llm_call_status == "error" else "success"
    if not bool(engineering_status.get("build", False)):
        execution_status = merge_statuses(execution_status, "partial")
    if not bool(engineering_status.get("tests", False)):
        execution_status = merge_statuses(execution_status, "partial")
    if not bool(engineering_status.get("testGeneration", False)):
        execution_status = merge_statuses(execution_status, "partial")
    if not bool(engineering_status.get("testQuality", False)):
        execution_status = merge_statuses(execution_status, "partial")
    return merge_statuses(execution_status, classifier_status(contributions))
