"""
Build file-level dependency graph from JavaFileInfo list; topological batches for bottom-up translation.
"""

from __future__ import annotations

import re
from collections import defaultdict

from java_ast import JavaFileInfo


def _simple_name_from_import(imp: str) -> str:
    imp = imp.strip().split("//")[0].strip()
    if not imp:
        return ""
    return imp.split(".")[-1]


def _build_class_to_file(infos: list[JavaFileInfo]) -> dict[str, str]:
    """simple class name and FQN -> java file path (posix)."""
    out: dict[str, str] = {}
    for info in infos:
        p = info.path.replace("\\", "/")
        for c in info.classes:
            out[c] = p
            if info.package:
                out[f"{info.package}.{c}"] = p
    return out


def build_dependency_graph(infos: list[JavaFileInfo]) -> dict[str, list[str]]:
    """
    Adjacency: file_path -> list of file paths it must be translated after (dependencies).
    Edge A -> B means: A depends on B (B should be translated before A).
    """
    by_path = {i.path.replace("\\", "/"): i for i in infos}
    class_to_file = _build_class_to_file(infos)
    graph: dict[str, set[str]] = defaultdict(set)

    for info in infos:
        mypath = info.path.replace("\\", "/")
        if mypath not in by_path:
            continue
        # From import lines: map to same-project files
        for imp in info.imports:
            target = class_to_file.get(imp) or class_to_file.get(
                _simple_name_from_import(imp)
            )
            if target and target != mypath and target in by_path:
                graph[mypath].add(target)
        # Heuristic: Capitalized tokens referencing project classes
        for m in re.finditer(
            r"\b([A-Z][a-zA-Z0-9_]*)\b", info.source_text
        ):
            name = m.group(1)
            if name in (
                "String",
                "Object",
                "Integer",
                "Long",
                "Double",
                "Float",
                "Boolean",
                "Byte",
                "Short",
                "Character",
                "Class",
            ):
                continue
            target = class_to_file.get(name)
            if target and target != mypath and target in by_path:
                graph[mypath].add(target)

    return {k: sorted(v) for k, v in graph.items()}


def topological_batches(
    graph: dict[str, list[str]], all_nodes: list[str]
) -> list[list[str]]:
    """
    Kahn's algorithm in layers: each layer can be processed in parallel.
    Nodes with no unprocessed dependencies go to the current batch.
    """
    all_nodes = sorted({n.replace("\\", "/") for n in all_nodes})
    graph = {
        k.replace("\\", "/"): [d.replace("\\", "/") for d in v]
        for k, v in graph.items()
    }

    # For each file, set of files it depends on (must finish first)
    depends: dict[str, set[str]] = {n: set() for n in all_nodes}
    for n, deps in graph.items():
        if n not in depends:
            depends[n] = set()
        for d in deps:
            if d in all_nodes and d != n:
                depends[n].add(d)

    # reverse: who depends on me (for indegree of "remaining dependency count")
    remaining_dep_count: dict[str, int] = {n: len(depends[n]) for n in all_nodes}
    # Also track for each n which nodes block on n
    reverse: dict[str, set[str]] = defaultdict(set)
    for n, ds in depends.items():
        for d in ds:
            reverse[d].add(n)

    pending = set(all_nodes)
    layers: list[list[str]] = []
    while pending:
        ready = [n for n in pending if remaining_dep_count.get(n, 0) == 0]
        if not ready:
            n0 = min(pending)
            ready = [n0]
        ready.sort()
        layers.append(ready)
        for n in ready:
            pending.discard(n)
            for w in reverse.get(n, ()):
                if w in pending:
                    remaining_dep_count[w] = max(0, remaining_dep_count.get(w, 0) - 1)
    return layers


def _norm_path(p: str) -> str:
    return (p or "").replace("\\", "/")


def _module_cluster_key_for_info(
    info: JavaFileInfo, depth: int, path_norm: str
) -> str:
    """Thematic key for grouping; no package => one file per 'module' key."""
    pkg = (getattr(info, "package", None) or "").strip()
    if not pkg:
        return f"__singleton__:{path_norm}"
    parts = [x for x in pkg.split(".") if x]
    if not parts:
        return f"__singleton__:{path_norm}"
    if len(parts) <= depth:
        return ".".join(parts)
    return ".".join(parts[:depth])


def _split_paths_into_submodules(
    paths: list[str],
    infos_by_path: dict[str, JavaFileInfo],
    depth: int,
    max_files: int,
) -> list[list[str]]:
    """
    Return one or more file lists, each a module, splitting oversized groups
    by deeper package or final chunking.
    """
    paths = sorted({_norm_path(p) for p in paths})
    if not paths:
        return []
    if len(paths) == 1:
        return [paths]

    by_key: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        info = infos_by_path.get(p) or JavaFileInfo(
            path=p, package="", imports=[], classes=[], methods=[], fields=[], source_text=""
        )
        by_key[_module_cluster_key_for_info(info, depth, p)].append(p)

    out: list[list[str]] = []
    for k in sorted(by_key.keys()):
        g = sorted(by_key[k])
        if len(g) <= max_files:
            out.append(g)
            continue
        any_pkg = False
        for p in g:
            inf = infos_by_path.get(p)
            if inf and (inf.package or "").strip():
                any_pkg = True
                break
        if any_pkg:
            out.extend(_split_paths_into_submodules(g, infos_by_path, depth + 1, max_files))
        else:
            for i in range(0, len(g), max_files):
                out.append(g[i : i + max_files])
    return out


def cluster_into_modules(
    infos: list[JavaFileInfo],
    dep_graph: dict[str, list[str]],
    depth: int = 2,
    max_files_per_module: int = 20,
) -> list[list[str]]:
    """
    Group files by package prefix; split oversized groups; order inside each
    module by the same Kahn layer logic as `topological_batches` on a subgraph.
    """
    all_paths = [_norm_path(i.path) for i in infos]
    infos_by_path = {_norm_path(i.path): i for i in infos}
    if not all_paths:
        return []

    raw = _split_paths_into_submodules(
        all_paths, infos_by_path, depth, max_files_per_module
    )
    modules: list[list[str]] = []
    for group in raw:
        sub: dict[str, set[str]] = defaultdict(set)
        gset = {_norm_path(x) for x in group}
        for p in gset:
            for d in dep_graph.get(p, []) or []:
                d = _norm_path(d)
                if d in gset and d != p:
                    sub[p].add(d)
        graph = {k: sorted(v) for k, v in sub.items() if v}
        ordered_layers = topological_batches(graph, list(gset))
        ordered: list[str] = []
        for layer in ordered_layers:
            ordered.extend(layer)
        # safety: all nodes
        for p in gset:
            if p not in ordered:
                ordered.append(p)
        modules.append(ordered)
    return modules


def module_dependency_layers(
    modules: list[list[str]],
    dep_graph: dict[str, list[str]],
) -> list[list[int]]:
    """
    If file A in module i depends (must translate after) on file B in module j, i has an edge to j
    in the per-file dep_graph sense: i waits for j. Kahn-layers of module indices.
    """
    path_to_midx: dict[str, int] = {}
    for i, m in enumerate(modules):
        for p in m:
            path_to_midx[_norm_path(p)] = i

    n = len(modules)
    mod_dep: dict[int, set[int]] = {i: set() for i in range(n)}

    for a, deps in (dep_graph or {}).items():
        a = _norm_path(a)
        if a not in path_to_midx:
            continue
        ia = path_to_midx[a]
        for b in deps or []:
            b = _norm_path(b)
            if b not in path_to_midx:
                continue
            ib = path_to_midx[b]
            if ia != ib:
                mod_dep[ia].add(ib)  # ia must run after ib

    done: set[int] = set()
    remaining = set(range(n))
    layers: list[list[int]] = []
    while remaining:
        ready = [i for i in remaining if mod_dep[i] <= done]
        if not ready:
            m0 = min(remaining)
            ready = [m0]
        ready.sort()
        layers.append(ready)
        for i in ready:
            remaining.discard(i)
        done |= set(ready)
    return layers
