"""Train and evaluate the humidity model on labeled classroom sessions."""

import argparse
import csv
import json
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from random import Random
from statistics import fmean, pstdev
from time import perf_counter_ns

from ai.humidity import LABELS, WINDOW_SIZE, HumidityModel, window_features


@dataclass(frozen=True)
class LabeledWindow:
    session: str
    label: str
    humidity: tuple[float, ...]


def synthetic_windows(seed: int) -> list[LabeledWindow]:
    """Choose a labeled scenario before generating measured values and noise."""
    rng = Random(seed)
    windows = []
    for label in LABELS:
        for run in range(40):
            baseline = rng.uniform(29, 71)
            if label == "humidity_fluctuating":
                trend, noise = 0, rng.uniform(6, 25)
            elif label == "stable":
                trend, noise = rng.uniform(-0.45, 0.45), rng.uniform(0.25, 2.1)
            else:
                trend, noise = rng.uniform(1.1, 4), rng.uniform(0.25, 2.1)
                if label == "humidity_falling":
                    trend = -trend
            for _ in range(4):
                offset = rng.uniform(-2, 2)
                readings = tuple(
                    round(max(0, min(100, baseline + offset + trend * index + rng.uniform(-noise, noise))), 2)
                    for index in range(WINDOW_SIZE)
                )
                windows.append(LabeledWindow(f"{label}-{run:02d}", label, readings))
    return windows


def read_windows(path: Path) -> list[LabeledWindow]:
    windows = []
    columns = [f"rh{index}" for index in range(1, WINDOW_SIZE + 1)]
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not set(["session", "label", *columns]).issubset(reader.fieldnames or ()):
            raise ValueError(f"Expected CSV columns session,label,{','.join(columns)}")
        for row in reader:
            try:
                session = (row["session"] or "").strip()
                label = (row["label"] or "").strip()
                readings = tuple(float(row[column]) for column in columns)
                window_features(readings)
                if not session or label not in LABELS:
                    raise ValueError("Expected a session ID and a known class label")
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid dataset row {reader.line_num}: {exc}") from exc
            windows.append(LabeledWindow(session, label, readings))
    return windows


def split_sessions(windows: list[LabeledWindow], seed: int) -> tuple[list[LabeledWindow], list[LabeledWindow]]:
    """Hold out whole recording sessions so related windows cannot leak."""
    by_session = {}
    for window in windows:
        if by_session.setdefault(window.session, window.label) != window.label:
            raise ValueError(f"Session {window.session!r} has multiple class labels")
    rng = Random(seed)
    held_out = set()
    for label in LABELS:
        sessions = sorted(session for session, actual in by_session.items() if actual == label)
        if len(sessions) < 2:
            raise ValueError(f"Class {label} needs at least two independently recorded sessions")
        rng.shuffle(sessions)
        held_out.update(sessions[:max(1, len(sessions) // 5)])
    train = [window for window in windows if window.session not in held_out]
    test = [window for window in windows if window.session in held_out]
    return train, test


def fit(train: list[LabeledWindow]) -> HumidityModel:
    by_label = {label: [] for label in LABELS}
    for window in train:
        by_label[window.label].append(window_features(window.humidity))
    centroids = {
        label: tuple(fmean(column) for column in zip(*features))
        for label, features in by_label.items()
    }
    all_features = [row for features in by_label.values() for row in features]
    scales = tuple(pstdev(column) or 1.0 for column in zip(*all_features))
    return HumidityModel(scales, centroids)


def evaluate(model: HumidityModel, test: list[LabeledWindow]) -> dict:
    matrix = [[0 for _ in LABELS] for _ in LABELS]
    latencies = []
    for window in test:
        started = perf_counter_ns()
        prediction = model.predict(window.humidity)
        latencies.append((perf_counter_ns() - started) / 1_000)
        matrix[LABELS.index(window.label)][LABELS.index(prediction)] += 1

    classes = {}
    for index, label in enumerate(LABELS):
        correct = matrix[index][index]
        predicted = sum(row[index] for row in matrix)
        support = sum(matrix[index])
        precision = correct / predicted if predicted else 0
        recall = correct / support
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        classes[label] = {"precision": precision, "recall": recall, "f1": f1, "support": support}

    latencies.sort()
    return {
        "labels": list(LABELS),
        "confusion_matrix_actual_rows_predicted_columns": matrix,
        "accuracy": sum(matrix[index][index] for index in range(len(LABELS))) / len(test),
        "macro_f1": fmean(metrics["f1"] for metrics in classes.values()),
        "per_class": classes,
        "inference_time_us": {"mean": fmean(latencies), "p95": latencies[ceil(0.95 * len(latencies)) - 1]},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, help="Use a labeled CSV instead of synthetic sessions")
    parser.add_argument("--seed", type=int, default=261, help="Seed for generation and the session split")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    try:
        windows = read_windows(args.dataset) if args.dataset else synthetic_windows(args.seed)
        train, test = split_sessions(windows, args.seed)
        model = fit(train)
        report = {
            "source": args.dataset.name if args.dataset else "synthetic",
            "seed": args.seed,
            "train_sessions": len({window.session for window in train}),
            "test_sessions": len({window.session for window in test}),
            "train_windows": len(train),
            "test_windows": len(test),
            **evaluate(model, test),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in (("humidity_model.json", model.as_dict()), ("evaluation.json", report)):
            (args.output_dir / filename).write_text(
                json.dumps(content, indent=2, allow_nan=False) + "\n", encoding="utf-8",
            )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Held out {len(test)} windows. Accuracy={report['accuracy']:.3f}, macro-F1={report['macro_f1']:.3f}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
