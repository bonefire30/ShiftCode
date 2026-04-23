"""
Optional per-project code vector store for large multi-file migrations.
Falls back to no-op if chromadb / embeddings are unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CodebaseRAG:
    """Stub implementation; can be extended with Chroma + OpenAI embeddings."""

    _chunks: list[str] = field(default_factory=list)
    _chroma: Any = None

    def add_file(self, java_path: str, go_code: str) -> None:
        text = f"FILE:{java_path}\n{go_code[:12000]}"
        self._chunks.append(text)
        self._try_chroma_add(java_path, go_code)

    def query(self, text: str, k: int = 3) -> list[str]:
        if not self._chunks and self._chroma is None:
            return []
        out = self._try_chroma_query(text, k)
        if out:
            return out
        return self._keyword_fallback(text, k)

    def _try_chroma_add(self, java_path: str, go_code: str) -> None:
        try:  # noqa: SIM105
            import chromadb  # type: ignore[import-not-found]

            if not hasattr(self, "_chroma") or not self._chroma:
                c = chromadb.Client()
                col = c.get_or_create_collection("migrated")
                col.add(
                    documents=[go_code[:8000]],
                    metadatas=[{"java": java_path}],
                    ids=[java_path],
                )
                self._chroma = col
        except Exception:  # noqa: BLE001
            return

    def _try_chroma_query(self, text: str, k: int) -> list[str]:
        try:
            c = getattr(self, "_chroma", None)
            if c is None:
                return []
            r = c.query(query_texts=[text], n_results=k)
            docs = (r.get("documents") or [[]])[0]
            return [str(d) for d in docs] if isinstance(docs, list) else []
        except Exception:  # noqa: BLE001
            return []

    def _keyword_fallback(self, text: str, k: int) -> list[str]:
        toks = set(text.lower().split())
        scored: list[tuple[int, str]] = []
        for c in self._chunks:
            words = c.lower().split()
            s = sum(1 for w in toks if w in words)
            if s:
                scored.append((-s, c[:4000]))
        scored.sort()
        return [c for _, c in scored[:k]]


def make_rag() -> CodebaseRAG:
    return CodebaseRAG()
