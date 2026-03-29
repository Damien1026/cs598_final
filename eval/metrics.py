from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BinaryMetrics:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    def f1(self) -> float:
        p, r = self.precision(), self.recall()
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "precision": round(self.precision(), 4),
            "recall": round(self.recall(), 4),
            "f1": round(self.f1(), 4),
        }


def update_alert_metrics(
    m: BinaryMetrics,
    *,
    predicted_alert: bool,
    should_alert: bool,
) -> None:
    if should_alert and predicted_alert:
        m.tp += 1
    elif should_alert and not predicted_alert:
        m.fn += 1
    elif not should_alert and predicted_alert:
        m.fp += 1
    else:
        m.tn += 1
