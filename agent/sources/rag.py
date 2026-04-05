from __future__ import annotations

import re
from pathlib import Path


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class RAGSource:
    """BM25 full-text search over a directory of .txt / .md files.

    Lazy-loads on first query — no model download required.
    """

    def __init__(self, docs_dir: str | Path) -> None:
        self.docs_dir = Path(docs_dir)
        self._corpus: list[tuple[str, str]] = []  # (filename, text)
        self._bm25 = None
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        from rank_bm25 import BM25Okapi

        docs: list[tuple[str, str]] = []
        if self.docs_dir.is_dir():
            for p in sorted(self.docs_dir.rglob("*")):
                if p.suffix.lower() in {".txt", ".md", ".rst"}:
                    try:
                        text = p.read_text(encoding="utf-8", errors="replace")
                        docs.append((p.name, text))
                    except OSError:
                        pass

        if not docs:
            docs = [("(empty)", "No documents found in RAG corpus.")]

        self._corpus = docs
        self._bm25 = BM25Okapi([_tokenize(text) for _, text in docs])
        self._loaded = True

    def search(self, query: str, top_k: int = 3) -> str:
        self._load()
        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        chunks: list[str] = []
        for idx in ranked:
            fname, text = self._corpus[idx]
            preview = text[:600].strip()
            chunks.append(f"[{fname}]\n{preview}")
        return "\n\n---\n\n".join(chunks) if chunks else "(no results)"
