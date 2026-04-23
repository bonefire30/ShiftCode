"""
Java source parsing: tree-sitter + tree-sitter-java when available, else regex fallback.
Used by the architect agent for multi-file migration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Optional tree-sitter
_TS_PARSER: Any = None


def _load_tree_sitter() -> bool:
    global _TS_PARSER
    if _TS_PARSER is not None:
        return True
    try:
        from tree_sitter import Language, Parser  # type: ignore[import-not-found]
        import tree_sitter_java as tsjava  # type: ignore[import-not-found]

        lang = Language(tsjava.language())
        try:
            _TS_PARSER = Parser(lang)
        except TypeError:
            # older py-tree-sitter
            p = Parser()
            p.set_language(lang)
            _TS_PARSER = p
        return True
    except Exception:  # noqa: BLE001
        _TS_PARSER = None
        return False


@dataclass
class JavaFileInfo:
    path: str  # relative to project root, posix style
    package: str
    imports: list[str]  # e.g. "java.util.List" or "com.example.User"
    classes: list[str]  # simple names
    methods: list[str]  # raw signature-ish lines
    fields: list[str]  # raw field lines
    source_text: str = ""

    def simple_class_names(self) -> list[str]:
        return list(self.classes)


# --- Regex fallback (no tree-sitter) ---

_RE_PACKAGE = re.compile(
    r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE
)
_RE_IMPORT = re.compile(
    r"^\s*import\s+(?:static\s+)?([^;*]+?)\s*;", re.MULTILINE
)
# class, interface, enum, record (Java 16+)
_RE_TYPE_DECL = re.compile(
    r"(?:^|\n)\s*(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?"
    r"(class|interface|enum|@interface|record)\s+(\w+)",
    re.MULTILINE,
)
_RE_METHOD = re.compile(
    r"^\s*(?:@(?:\w+)(?:\([^)]*\))?\s*)*"
    r"(?:public|protected|private|static|final|synchronized|abstract|default|native|strictfp)+"
    r"[\s\w<>,?@\[\].]*\s+(\w+)\s*\([^;]*$",
    re.MULTILINE,
)
# Looser: line with identifier(...) {
_RE_METHOD_LOOSE = re.compile(
    r"^\s*[\w<>,?@\[\].\s]+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w.,\s]+)?\s*\{",
    re.MULTILINE,
)
_RE_FIELD = re.compile(
    r"^\s*(?:@(?:\w+)(?:\([^)]*\))?\s*)*"
    r"(?:public|protected|private|static|final|transient|volatile)\s+"
    r"[^;(]+?(\w+)\s*[=;]",  # not perfect; ok for heuristics
    re.MULTILINE,
)


def _parse_with_regex(relative_path: str, text: str) -> JavaFileInfo:
    m = _RE_PACKAGE.search(text)
    package = m.group(1) if m else ""
    imports = [x.strip() for x in _RE_IMPORT.findall(text)]
    classes: list[str] = []
    for m2 in _RE_TYPE_DECL.finditer(text):
        classes.append(m2.group(2))
    methods: list[str] = []
    for line in text.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("@"):
            continue
        mm = _RE_METHOD_LOOSE.search(line)
        if mm and mm.group(1) not in (
            "if",
            "for",
            "while",
            "switch",
            "catch",
            "synchronized",
        ):
            if line_stripped and not line_stripped.startswith("//"):
                methods.append(line.strip()[:500])
    fields: list[str] = []
    for m3 in _RE_FIELD.finditer(text):
        fields.append(m3.group(0).strip()[:300])

    return JavaFileInfo(
        path=relative_path,
        package=package,
        imports=imports,
        classes=classes,
        methods=methods[:200],  # cap
        fields=fields[:200],
        source_text=text,
    )


def _ts_collect(
    text: str, rel_path: str, tree: Any
) -> JavaFileInfo:
    """Traverse tree-sitter tree for package, import, class, method, field."""
    root = tree.root_node
    package = ""
    imports: list[str] = []
    classes: list[str] = []
    methods: list[str] = []
    fields: list[str] = []

    stack: list[Any] = [root]
    while stack:
        node = stack.pop()
        t = node.type
        if t == "package_declaration":
            for c in node.children:
                if c.type in ("scoped_identifier", "identifier") and not package:
                    package = _node_text(text, c)
        elif t == "import_declaration":
            imp = _extract_import_path(text, node)
            if imp:
                imports.append(imp)
        elif t in (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
        ):
            child_fn = getattr(node, "child_by_field_name", None)
            nnode = child_fn("name") if child_fn else None
            if nnode:
                n = _node_text(text, nnode)
                if n and n not in classes:
                    classes.append(n)
        elif t in ("method_declaration", "constructor_declaration"):
            line = _node_text(text, node)[:500]
            mline = line.split("{")[0].strip() if "{" in line else line
            if mline:
                methods.append(mline)
        elif t == "field_declaration":
            fields.append(_node_text(text, node)[:300])
        for c in node.children:
            stack.append(c)

    return JavaFileInfo(
        path=rel_path,
        package=package,
        imports=imports,
        classes=classes,
        methods=methods[:200],
        fields=fields[:200],
        source_text=text,
    )


def _node_text(text: str, node: Any) -> str:
    return text[node.start_byte : node.end_byte]


def _extract_import_path(text: str, node: Any) -> str:
    s = _node_text(text, node)
    s = re.sub(r"^\s*import\s+static\s+", "", s)
    s = re.sub(r"^\s*import\s+", "", s)
    s = s.split(";")[0].strip()
    if s.startswith("*"):
        return ""
    return s.strip()


def parse_java_file(project_root: Path, file_path: Path) -> JavaFileInfo:
    """
    Read and parse a .java file under project_root.
    `file_path` may be absolute or relative; we store `path` relative to project_root.
    """
    project_root = project_root.resolve()
    file_path = file_path.resolve()
    try:
        rel = file_path.relative_to(project_root)
    except ValueError:
        rel = file_path
    rel_str = str(rel).replace("\\", "/")
    text = file_path.read_text(encoding="utf-8", errors="replace")
    if _load_tree_sitter() and _TS_PARSER is not None:
        try:
            tree = _TS_PARSER.parse(bytes(text, "utf-8"))
            if tree and tree.root_node:
                return _ts_collect(text, rel_str, tree)
        except Exception:  # noqa: BLE001
            pass
    return _parse_with_regex(rel_str, text)


def parse_java_string(relative_path: str, text: str) -> JavaFileInfo:
    """Parse in-memory (benchmarks) without file read."""
    if _load_tree_sitter() and _TS_PARSER is not None:
        try:
            tree = _TS_PARSER.parse(bytes(text, "utf-8"))
            if tree and tree.root_node:
                return _ts_collect(text, relative_path, tree)
        except Exception:  # noqa: BLE001
            pass
    return _parse_with_regex(relative_path, text)


def java_info_to_dict(i: JavaFileInfo) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(i)


def java_info_from_dict(d: dict[str, Any]) -> JavaFileInfo:
    return JavaFileInfo(
        path=d.get("path", ""),
        package=d.get("package", ""),
        imports=list(d.get("imports") or []),
        classes=list(d.get("classes") or []),
        methods=list(d.get("methods") or []),
        fields=list(d.get("fields") or []),
        source_text=d.get("source_text", "") or "",
    )


def detect_framework_flags(infos: list[JavaFileInfo]) -> list[str]:
    """
    Heuristics: Spring, JPA, JAX-RS, etc. from source text and imports.
    """
    text_blob = "\n".join(i.source_text for i in infos)
    flags: list[str] = []
    if "org.springframework" in text_blob or "@Component" in text_blob or "@SpringBootApplication" in text_blob:
        flags.append("spring")
    if "@Transactional" in text_blob or "javax.persistence" in text_blob or "jakarta.persistence" in text_blob:
        flags.append("jpa_transactional")
    if "@Path" in text_blob and "jakarta.ws.rs" in text_blob or "javax.ws.rs" in text_blob:
        flags.append("jaxrs")
    if "org.hibernate" in text_blob or "@Entity" in text_blob:
        flags.append("jpa_entity")
    return list(dict.fromkeys(flags))
