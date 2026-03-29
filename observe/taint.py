from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable


class Sensitivity(IntEnum):
    public = 0
    internal_doc = 1
    pii = 2
    credential = 3

    @classmethod
    def from_str(cls, s: str) -> Sensitivity:
        return cls[s] if s in cls.__members__ else cls.public


def merge_labels(a: set[str], b: Iterable[str]) -> set[str]:
    out = set(a)
    for x in b:
        out.add(x)
    return out


@dataclass
class Artifact:
    id: str
    origin: str
    labels: set[str] = field(default_factory=set)
    preview: str = ""

    def sensitivity_order(self) -> Sensitivity:
        order = Sensitivity.public
        for lab in self.labels:
            if lab in Sensitivity.__members__:
                order = max(order, Sensitivity[lab])
        return order


class TaintStore:
    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}

    def new_artifact(
        self,
        origin: str,
        labels: Iterable[str],
        preview: str = "",
        artifact_id: str | None = None,
    ) -> Artifact:
        aid = artifact_id or str(uuid.uuid4())
        art = Artifact(id=aid, origin=origin, labels=set(labels), preview=preview[:500])
        self._artifacts[aid] = art
        return art

    def get(self, artifact_id: str) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    def union_text(
        self,
        parts: list[tuple[str, str]],
        *,
        origin: str = "merged",
    ) -> tuple[str, Artifact]:
        """parts: list of (text, artifact_id or empty for untainted)."""
        labels: set[str] = set()
        chunks: list[str] = []
        for text, aid in parts:
            chunks.append(text)
            if aid and (a := self.get(aid)):
                labels = merge_labels(labels, a.labels)
        merged = "".join(chunks)
        art = self.new_artifact(origin, labels, preview=merged)
        return merged, art

    def labels_for_tool_args(self, arg_text: str, artifact_refs: list[str]) -> set[str]:
        labels: set[str] = set()
        for aid in artifact_refs:
            if aid and (a := self.get(aid)):
                labels = merge_labels(labels, a.labels)
        labels = merge_labels(labels, infer_labels_from_text(arg_text))
        return labels


def infer_labels_from_text(text: str) -> set[str]:
    """Lightweight heuristics when artifact IDs are missing from the LLM."""
    labels: set[str] = set()
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", text) or re.search(r"\S+@\S+\.\S+", text):
        labels.add("pii")
    if re.search(r"sk-[A-Za-z0-9]{8,}", text) or "API_KEY" in text:
        labels.add("credential")
    if (
        "Internal roadmap" in text
        or "legacy API" in text
        or "internal notes" in text.lower()
        or "from rag" in text.lower()
    ):
        labels.add("internal_doc")
    return labels

    def attach_labels_to_message_text(self, text: str, refs: list[str]) -> Artifact:
        labels = self.labels_for_tool_args(text, refs)
        return self.new_artifact("llm_context", labels, preview=text)
