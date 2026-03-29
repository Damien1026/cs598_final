from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TrustStore:
    """Decay and update trust per action fingerprint."""

    path: Path | None = None
    scores: dict[str, float] = field(default_factory=dict)

    def load(self) -> None:
        if self.path and self.path.is_file():
            self.scores = json.loads(self.path.read_text(encoding="utf-8"))

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.scores, indent=2), encoding="utf-8")

    def decay(self) -> None:
        for k in list(self.scores):
            self.scores[k] = max(0.0, self.scores[k] * 0.99)

    def adjust(self, fingerprint: str, action: str) -> None:
        cur = self.scores.get(fingerprint, 0.5)
        if action == "allow":
            cur = min(1.0, cur + 0.15)
        elif action == "deny":
            cur = max(0.0, cur - 0.2)
        elif action == "allow_once":
            cur = min(1.0, cur + 0.05)
        self.scores[fingerprint] = cur

    def trust_for(self, fingerprint: str) -> float:
        return self.scores.get(fingerprint, 0.5)

    def hitl_threshold(self, fingerprint: str, base: float = 0.72) -> float:
        """Higher trust -> higher threshold -> fewer HITL from risk score."""
        t = self.trust_for(fingerprint)
        return base + (t - 0.5) * 0.12
