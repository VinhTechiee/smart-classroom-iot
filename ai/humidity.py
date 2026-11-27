"""Window features and nearest-centroid inference for humidity events."""

import json
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from statistics import fmean


MODEL_VERSION = "humidity-centroid-v1"
WINDOW_SIZE = 6
LABELS = ("stable", "humidity_rising", "humidity_falling", "humidity_fluctuating")
FEATURES = ("mean_change", "mean_absolute_step")
MIN_SAMPLE_GAP_MS = 2_500
MAX_SAMPLE_GAP_MS = 15_000


def valid_humidity(value: object) -> bool:
    return type(value) in (int, float) and 0 <= value <= 100


def window_features(readings: Sequence[float]) -> tuple[float, float]:
    if len(readings) != WINDOW_SIZE or not all(map(valid_humidity, readings)):
        raise ValueError(f"Expected {WINDOW_SIZE} humidity readings between 0 and 100% RH")
    split = WINDOW_SIZE // 2
    mean_change = fmean(readings[split:]) - fmean(readings[:split])
    mean_absolute_step = fmean(abs(next_rh - rh) for rh, next_rh in zip(readings, readings[1:]))
    return mean_change, mean_absolute_step


@dataclass(frozen=True)
class HumidityModel:
    scales: tuple[float, ...]
    centroids: dict[str, tuple[float, ...]]

    def predict(self, readings: Sequence[float]) -> str:
        features = window_features(readings)

        def distance(label: str) -> float:
            return sum(
                ((value - center) / scale) ** 2
                for value, center, scale in zip(features, self.centroids[label], self.scales)
            )

        return min(LABELS, key=distance)

    def as_dict(self) -> dict:
        return {
            "version": MODEL_VERSION,
            "window_size": WINDOW_SIZE,
            "feature_names": list(FEATURES),
            "scales": self.scales,
            "centroids": self.centroids,
        }

    @classmethod
    def load(cls, path: Path) -> "HumidityModel":
        model = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(model, dict)
            or model.get("version") != MODEL_VERSION
            or model.get("window_size") != WINDOW_SIZE
            or model.get("feature_names") != list(FEATURES)
        ):
            raise ValueError(f"Unsupported humidity model format in {path}")

        def vector(values: list) -> tuple[float, ...]:
            if not isinstance(values, list) or len(values) != len(FEATURES):
                raise ValueError(f"Invalid feature vector in {path}")
            try:
                numbers = tuple(float(value) for value in values)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"Invalid feature vector in {path}") from exc
            if not all(map(isfinite, numbers)):
                raise ValueError(f"Non-finite model parameter in {path}")
            return numbers

        scales = vector(model.get("scales"))
        centroids = model.get("centroids")
        if min(scales) <= 0 or not isinstance(centroids, dict) or set(centroids) != set(LABELS):
            raise ValueError(f"Invalid scales or class labels in {path}")
        return cls(scales, {label: vector(centroids[label]) for label in LABELS})


class HumidityDetector:
    """Classify recent samples from one device at the classroom's MQTT cadence."""

    def __init__(self, model: HumidityModel):
        self.model = model
        self.samples: deque[float] = deque(maxlen=WINDOW_SIZE)
        self.last_sample_ms: int | None = None

    def observe(self, humidity: float | None, timestamp_ms: int) -> str | None:
        if not valid_humidity(humidity):
            self.samples.clear()
            self.last_sample_ms = None
            return None
        if self.last_sample_ms is not None:
            gap = timestamp_ms - self.last_sample_ms
            if gap < MIN_SAMPLE_GAP_MS:
                return None
            if gap > MAX_SAMPLE_GAP_MS:
                self.samples.clear()
        self.last_sample_ms = timestamp_ms
        self.samples.append(humidity)
        if len(self.samples) == WINDOW_SIZE:
            return self.model.predict(tuple(self.samples))
        return None
