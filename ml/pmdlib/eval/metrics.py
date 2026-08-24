"""Evaluation metrics and the real-data acceptance test."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)

from ..data.loader import CLASS_ORDER


@dataclass
class ClassificationResult:
    name: str
    accuracy: float
    balanced_accuracy: float
    macro_f1: float
    weighted_f1: float
    per_class: pd.DataFrame
    confusion: np.ndarray

    def row(self) -> dict[str, float | str]:
        return {
            "model": self.name,
            "accuracy": round(self.accuracy, 4),
            "balanced_acc": round(self.balanced_accuracy, 4),
            "macro_f1": round(self.macro_f1, 4),
            "weighted_f1": round(self.weighted_f1, 4),
        }


def evaluate_classifier(name: str, y_true: np.ndarray, y_pred: np.ndarray) -> ClassificationResult:
    labels = np.arange(len(CLASS_ORDER))
    p, r, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, zero_division=0
    )
    per_class = pd.DataFrame(
        {"class": CLASS_ORDER, "precision": p, "recall": r, "f1": f1, "support": support}
    )
    return ClassificationResult(
        name=name,
        accuracy=float(accuracy_score(y_true, y_pred)),
        balanced_accuracy=float(balanced_accuracy_score(y_true, y_pred)),
        macro_f1=float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        weighted_f1=float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        per_class=per_class,
        confusion=confusion_matrix(y_true, y_pred, labels=labels),
    )


def evaluate_binary(y_true: np.ndarray, score: np.ndarray) -> dict[str, float]:
    """Anomaly detection: is this throw abnormal at all?"""
    return {
        "roc_auc": round(float(roc_auc_score(y_true, score)), 4),
        "positive_rate": round(float(np.mean(y_true)), 4),
    }


#: What the real Sehwa events *should* be called, judged from their signals.
#:
#: All seven carry a maintenance code, but a code names the component that was
#: serviced, not necessarily something visible in that capture. Three events show
#: an unambiguous signal-level fault and the model must get those right. The four
#: completed PMD014 throws are labelled E03 (a control-relay component) yet their
#: signals are textbook healthy - so NORMAL is the signal-consistent answer, and
#: scoring them as E03 would be scoring the model against information that is not
#: present in the data.
REAL_EXPECTATIONS: dict[str, dict[str, str]] = {
    "PMD055#5416": {"expect": "E01_LOCK_LATCH", "why": "stalled throw, never locks, drive never cut"},
    "PMD055#5417": {"expect": "E01_LOCK_LATCH", "why": "stalled throw, never locks, drive never cut"},
    "PMD014#2594": {"expect": "E03_LINE_RELAY", "why": "motor never started, no supply sag"},
    "PMD014#2593": {"expect": "NORMAL", "why": "completed throw, textbook current profile"},
    "PMD014#2595": {"expect": "NORMAL", "why": "completed throw, textbook current profile"},
    "PMD014#2596": {"expect": "NORMAL", "why": "completed throw, textbook current profile"},
    "PMD014#2597": {"expect": "NORMAL", "why": "completed throw, textbook current profile"},
}

#: The three events that must be correct for the acceptance test to pass: the
#: ones whose fault is unambiguously present in the signal.
DIAGNOSTIC_EVENTS = ("PMD055#5416", "PMD055#5417", "PMD014#2594")


def acceptance_test(keys: list[str], y_pred: np.ndarray) -> tuple[pd.DataFrame, bool]:
    """Score predictions against the 7 real, never-trained-on Sehwa events."""
    rows = []
    for key, pred_idx in zip(keys, y_pred, strict=True):
        exp = REAL_EXPECTATIONS[key]
        pred = CLASS_ORDER[int(pred_idx)]
        rows.append(
            {
                "event": key,
                "expected": exp["expect"],
                "predicted": pred,
                "correct": pred == exp["expect"],
                "diagnostic": key in DIAGNOSTIC_EVENTS,
                "why": exp["why"],
            }
        )
    df = pd.DataFrame(rows)
    passed = bool(df[df.diagnostic].correct.all())
    return df, passed
