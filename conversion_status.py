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
    category: str = "generic"
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

    def add(status: str, reason: str, source: str, category: str = "generic") -> None:
        key = (status, reason, category)
        if key not in seen:
            contributions.append(StatusContribution(status=status, reason=reason, category=category, source=source))
            seen.add(key)

    for path, text_raw in items:
        text = text_raw or ""
        compact = re.sub(r"\s+", " ", text)
        if re.search(r"\.\s*stream\s*\(", text) or re.search(r"\bStream\s*<", text):
            add("unsupported", "Detected Java stream pipeline; stream pipelines are currently unsupported.", path, category="stream_pipeline_unsupported")
        if re.search(r"\bclass\s+\w+\s*<[^>]+>", text) or re.search(r"\binterface\s+\w+\s*<[^>]+>", text) or re.search(r"\b(?:public|private|protected|static|final|\s)+<[^>]+>\s+\w+\s*\(", text):
            add("unsupported", "Detected Java generics; generic type semantics require explicit mapping and are currently unsupported.", path, category="java_generics_unsupported")
        if re.search(r"^\s*@(?:Service|Component|Repository|Controller|RestController|Autowired|Bean|Entity|Table|Transactional|ConfigurationProperties|Value|PropertySource)\b", text, re.MULTILINE):
            add("unsupported", "Detected framework or dynamic config behavior; manually migrate framework-driven configuration semantics.", path, category="config_dynamic_or_framework_unsupported")

        has_config_get = bool(re.search(r"\b\w*config\w*\s*\.\s*get\(\s*\"[^\"]+\"\s*\)", text, re.IGNORECASE))
        has_get_or_default = bool(re.search(r"\b\w*config\w*\s*\.\s*getOrDefault\(\s*\"[^\"]+\"\s*,", text, re.IGNORECASE))
        has_required_field_validation = bool(
            re.search(r"containsKey\(\s*\"[^\"]+\"\s*\)", text)
            or re.search(r"\.get\(\s*\"[^\"]+\"\s*\)\s*==\s*null", compact)
        ) and bool(re.search(r"throw\s+new\s+(?:IllegalArgumentException|IllegalStateException)\b", text))
        has_simple_parse_failure = bool(
            re.search(r"\b(?:Integer|Long|Double|Float|Short|Byte)\.parse\w+\s*\(", text)
        )

        if has_config_get:
            add("warning", "Detected map-backed config lookup; review missing-key behavior and zero-value assumptions.", path, category="config_map_lookup_missing_key_caveat")
        if has_get_or_default:
            add("warning", "Detected config default value fallback; verify missing-key behavior and preserved defaults in Go.", path, category="config_default_value_fallback")
        if has_required_field_validation:
            add("partial", "Detected required config field validation; Java exception flow should become explicit Go error returns and needs review.", path, category="config_required_field_error_return")
        if has_simple_parse_failure:
            add("partial", "Detected config parse failure path; Java parse errors should become explicit Go error returns and need review.", path, category="config_parse_failure_error_return")

        has_checked_throws = bool(
            re.search(
                r"\bthrows\s+(?:[\w.]+\s*,\s*)*(?:IOException|SQLException|ParseException|Exception|Throwable|ReflectiveOperationException|ClassNotFoundException|InterruptedException)\b",
                text,
            )
        )
        has_catch = bool(re.search(r"\bcatch\s*\(", text))
        has_validation_throw = bool(
            re.search(r"\bif\s*\([^)]*\)\s*\{?\s*throw\s+new\s+(?:IllegalArgumentException|IllegalStateException)\b", compact)
        )
        has_local_precondition_throw = bool(
            re.search(
                r"\b(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?\w+\s+\w+\s*\([^)]*\)\s*\{\s*if\s*\([^)]*\)\s*\{?\s*throw\s+new\s+(?:IllegalArgumentException|IllegalStateException)\b",
                compact,
            )
            or re.search(
                r"\b(?:public|private|protected)?\s+[A-Z]\w*\s*\([^)]*\)\s*\{\s*if\s*\([^)]*\)\s*\{?\s*throw\s+new\s+(?:IllegalArgumentException|IllegalStateException)\b",
                compact,
            )
        )
        has_parse_failure_catch = bool(
            re.search(r"\btry\s*\{[^}]*\b(?:Integer|Long|Double|Float|Short|Byte)\.parse\w+\s*\([^}]*\}[^}]*catch\s*\(\s*\w*NumberFormatException\b", compact)
        )
        has_single_operation_fallback = bool(
            re.search(r"\btry\s*\{[^}]*\}\s*catch\s*\([^)]*\)\s*\{[^}]*\breturn\b", compact)
        )
        has_retry_error_flow = bool(
            re.search(r"\b(retry|backoff|attempt|recover|fallback)\b", compact, re.IGNORECASE)
            and (has_checked_throws or has_catch or re.search(r"\bthrow\s+new\s+\w+", text))
        )
        if has_validation_throw and not has_local_precondition_throw:
            add(
                "partial",
                "Detected validation throw flow; convert Java validation exceptions into explicit Go error returns and review caller behavior.",
                path,
                category="validation_throw_error_return",
            )
        if has_single_operation_fallback:
            add(
                "partial",
                "Detected single-operation fallback flow; review fallback semantics after converting exception control flow to Go error handling.",
                path,
                category="single_operation_fallback_flow",
            )
        if has_retry_error_flow:
            add(
                "partial",
                "Detected retry loop exception flow; review retry and terminal-error semantics after converting to Go error returns.",
                path,
                category="retry_loop_manual_review",
            )
        if has_parse_failure_catch:
            add(
                "partial",
                "Detected parse failure catch flow; convert parse exceptions into explicit Go error returns and review invalid-input behavior.",
                path,
                category="parse_failure_error_return",
            )
        if has_checked_throws or has_catch or has_retry_error_flow:
            add("partial", "Detected Java exception flow; Go error-return design requires manual review.", path, category="java_exception_flow_partial")
        if (
            re.search(r"\bparse\w*\s*\(", compact, re.IGNORECASE)
            or re.search(r"\bObjectMapper\b|\bJson\b|\bJSON\b|\bPattern\.compile\b|\bMatcher\b", text)
        ) and not any(
            c.source == path and c.category.startswith("config_")
            for c in contributions
        ):
            add("warning", "Detected parser/config behavior; defaults and error paths may require review.", path, category="config_generic_caveat")
    return contributions


def status_reasons(contributions: list[StatusContribution]) -> list[str]:
    return [c.reason for c in contributions]


def status_reason_details(contributions: list[StatusContribution]) -> list[dict[str, str]]:
    return [
        {
            "category": c.category,
            "status": c.status,
            "message": c.reason,
            "source": c.source,
        }
        for c in contributions
    ]


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
