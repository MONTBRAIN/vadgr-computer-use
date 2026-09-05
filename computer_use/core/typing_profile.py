# Copyright 2026 Victor Santiago Montaño Diaz
# Licensed under the Apache License, Version 2.0.

"""Pure standard-library interpreter for observable-context typing profiles."""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Protocol

CLASSES = (
    "same_key",
    "same_finger",
    "same_hand",
    "alternate_hand",
    "other",
    "ordinary_space",
    "clause",
    "sentence",
    "newline",
    "paragraph",
)
NON_BOUNDARY_CLASSES = frozenset(CLASSES[:6])
_MODEL_FIELDS = frozenset(
    (
        "kind",
        "version",
        "rank_dependence",
        "rank_transition",
        "styles",
        "class_quantiles",
        "reference_class_weights",
        "calibration_scale",
        "ordinary_space_added_pause_ms",
    )
)
_LIMIT_FIELDS = frozenset(
    (
        "minimum_interval_ms",
        "maximum_total_gap_ms",
        "maximum_transport_unit_ms",
        "minimum_validation_graphemes",
        "class_maximum_ms",
    )
)
_CLASS_MAXIMUM_MS = {
    "same_key": 1500.0,
    "same_finger": 1500.0,
    "same_hand": 1500.0,
    "alternate_hand": 1500.0,
    "other": 1500.0,
    "ordinary_space": 1500.0,
    "clause": 2500.0,
    "sentence": 3500.0,
    "newline": 5000.0,
    "paragraph": 5000.0,
}


class RandomSource(Protocol):
    def random(self) -> float: ...


@dataclass(frozen=True)
class OperationState:
    """The one speed style held for a complete operation."""

    speed_log: float


@dataclass(frozen=True)
class GapSample:
    gap_class: str
    quantile_draw: float
    total_ms: float
    rank_bin: int | None = None


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} is not a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} is not finite")
    return result


def _draw(weights: Sequence[float], random: RandomSource) -> int:
    target = min(max(float(random.random()), 0.0), math.nextafter(1.0, 0.0))
    return _draw_probability(weights, target)


def _draw_probability(weights: Sequence[float], target: float) -> int:
    cumulative = 0.0
    for index, weight in enumerate(weights):
        cumulative += weight
        if target < cumulative:
            return index
    return len(weights) - 1


def _quantile(values: Sequence[float], probability: float) -> float:
    position = min(max(probability, 0.0), 1.0) * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _piecewise_moments(values: Sequence[float]) -> tuple[float, float]:
    segments = len(values) - 1
    mean = (
        math.fsum((values[index] + values[index + 1]) / 2 for index in range(segments)) / segments
    )
    second = (
        math.fsum(
            (
                values[index] * values[index]
                + values[index] * values[index + 1]
                + values[index + 1] * values[index + 1]
            )
            / 3
            for index in range(segments)
        )
        / segments
    )
    return mean, second


def _piecewise_clipped_mean(values: Sequence[float], lower: float, upper: float) -> float:
    integrals = []
    for left, right in pairwise(values):
        change = right - left
        knots = [0.0, 1.0]
        if change:
            knots.extend(
                point
                for point in ((lower - left) / change, (upper - left) / change)
                if 0 < point < 1
            )
        knots.sort()
        integral = 0.0
        for start, end in pairwise(knots):
            start_value = min(upper, max(lower, left + change * start))
            end_value = min(upper, max(lower, left + change * end))
            integral += (start_value + end_value) * (end - start) / 2
        integrals.append(integral)
    return math.fsum(integrals) / len(integrals)


class ArtifactInterpreter:
    """Interpret one validated observable-context total-gap profile."""

    def __init__(self, profile: Mapping[str, object], *, require_cleared: bool = True):
        if not isinstance(profile, Mapping):
            raise ValueError("typing profile is not an object")
        self.profile = dict(profile)
        model = self.profile.get("model")
        limits = self.profile.get("limits")
        if not isinstance(model, Mapping) or not isinstance(limits, Mapping):
            raise ValueError("typing profile model or limits are missing")
        self.model = dict(model)
        self.limits = dict(limits)
        self.styles: tuple[dict[str, object], ...] = ()
        self.class_quantiles: dict[str, tuple[float, ...]] = {}
        self.reference_class_weights: dict[str, float] = {}
        self.class_maximum_ms: dict[str, float] = {}
        self.rank_transitions: tuple[tuple[tuple[float, ...], ...], ...] = ()
        self._quantile_cache: OrderedDict[float, dict[str, tuple[float, ...]]] = OrderedDict()
        self._calibration_cache: OrderedDict[tuple[float, float | None], tuple[float, float]] = (
            OrderedDict()
        )
        self._validate(require_cleared=require_cleared)

    def _validate(self, *, require_cleared: bool) -> None:
        if (
            self.profile.get("schema") != 6
            or self.model.get("kind") != "observable_context_empirical_total_gap"
            or self.model.get("version") != 1
        ):
            raise ValueError("unsupported typing profile schema")
        if set(self.model) != _MODEL_FIELDS:
            raise ValueError("typing profile model fields are invalid")
        if set(self.limits) != _LIMIT_FIELDS:
            raise ValueError("typing profile limit fields are invalid")
        rank_dependence = self.model.get("rank_dependence")
        raw_transition = self.model.get("rank_transition")
        if rank_dependence == "independent":
            if raw_transition is not None:
                raise ValueError("independent typing profile has a rank transition")
        elif rank_dependence == "markov_4_bin":
            if not isinstance(raw_transition, Mapping) or set(raw_transition) != {
                "bins",
                "initial",
                "matrix",
            }:
                raise ValueError("typing profile rank transition fields are invalid")
            if raw_transition["bins"] != 4 or raw_transition["initial"] != [0.25] * 4:
                raise ValueError("typing profile rank transition initialization is invalid")
            self.rank_transition = self._validated_rank_matrix(raw_transition["matrix"])
        else:
            raise ValueError("typing profile rank dependence is invalid")
        if (
            _finite_number(
                self.model.get("ordinary_space_added_pause_ms"),
                "ordinary-space added pause",
            )
            != 0.0
        ):
            raise ValueError("ordinary-space added pause must be zero")

        validation = self.profile.get("validation")
        if not isinstance(validation, Mapping) or not isinstance(validation.get("cleared"), bool):
            raise ValueError("typing profile has no validation verdict")
        if require_cleared and not validation["cleared"]:
            raise ValueError("typing profile did not clear validation")

        raw_styles = self.model.get("styles")
        if not isinstance(raw_styles, list) or not raw_styles:
            raise ValueError("typing profile styles are invalid")
        styles = []
        for raw_style in raw_styles:
            if not isinstance(raw_style, Mapping) or set(raw_style) != {"weight", "speed_log"}:
                raise ValueError("typing profile style fields are invalid")
            weight = _finite_number(raw_style["weight"], "style weight")
            speed_log = _finite_number(raw_style["speed_log"], "style speed")
            if weight <= 0:
                raise ValueError("typing profile style weights are invalid")
            styles.append({"weight": weight, "speed_log": speed_log})
        if not math.isclose(
            math.fsum(float(style["weight"]) for style in styles),
            1.0,
            abs_tol=2e-7,
        ):
            raise ValueError("typing profile style weights are invalid")
        self.styles = tuple(styles)

        raw_quantiles = self.model.get("class_quantiles")
        raw_weights = self.model.get("reference_class_weights")
        raw_maximums = self.limits.get("class_maximum_ms")
        if not all(
            isinstance(value, Mapping) for value in (raw_quantiles, raw_weights, raw_maximums)
        ):
            raise ValueError("typing profile class tables are invalid")
        if not all(
            set(value) == set(CLASSES) for value in (raw_quantiles, raw_weights, raw_maximums)
        ):
            raise ValueError("typing profile classes are invalid")

        weights = {
            name: _finite_number(raw_weights[name], f"{name} reference weight") for name in CLASSES
        }
        if any(value < 0 for value in weights.values()) or not math.isclose(
            math.fsum(weights.values()), 1.0, abs_tol=2e-7
        ):
            raise ValueError("reference class weights are invalid")
        self.reference_class_weights = weights

        minimum = _finite_number(self.limits["minimum_interval_ms"], "minimum interval")
        total_maximum = _finite_number(self.limits["maximum_total_gap_ms"], "maximum total gap")
        transport_maximum = _finite_number(
            self.limits["maximum_transport_unit_ms"], "maximum transport unit"
        )
        minimum_length = self.limits["minimum_validation_graphemes"]
        if (
            isinstance(minimum_length, bool)
            or not isinstance(minimum_length, int)
            or minimum_length < 200
        ):
            raise ValueError("minimum validation length is invalid")
        if minimum != 20.0 or total_maximum != 5000.0 or transport_maximum != 5000.0:
            raise ValueError("typing profile limits are invalid")

        maximums = {name: _finite_number(raw_maximums[name], f"{name} maximum") for name in CLASSES}
        if maximums != _CLASS_MAXIMUM_MS:
            raise ValueError("typing profile class support is invalid")
        self.class_maximum_ms = maximums

        quantiles: dict[str, tuple[float, ...]] = {}
        for name in CLASSES:
            raw_values = raw_quantiles[name]
            if not isinstance(raw_values, list) or len(raw_values) < 2:
                raise ValueError("typing profile class quantiles are invalid")
            values = tuple(_finite_number(value, f"{name} quantile") for value in raw_values)
            if any(value <= 0 for value in values) or any(
                values[index] > values[index + 1] for index in range(len(values) - 1)
            ):
                raise ValueError("typing profile class quantiles are invalid")
            quantiles[name] = values
        self.class_quantiles = quantiles

        calibration_scale = _finite_number(self.model["calibration_scale"], "calibration scale")
        if calibration_scale <= 0:
            raise ValueError("calibration scale is invalid")

    @staticmethod
    def _validated_rank_matrix(
        raw_matrix: object,
    ) -> tuple[tuple[float, ...], ...]:
        if not isinstance(raw_matrix, list) or len(raw_matrix) != 4:
            raise ValueError("typing profile rank transition matrix is invalid")
        matrix = []
        for raw_row in raw_matrix:
            if not isinstance(raw_row, list) or len(raw_row) != 4:
                raise ValueError("typing profile rank transition matrix is invalid")
            row = tuple(_finite_number(value, "rank transition") for value in raw_row)
            if any(value < 0 for value in row) or not math.isclose(
                math.fsum(row), 1.0, abs_tol=2e-7
            ):
                raise ValueError("typing profile rank transition matrix is invalid")
            matrix.append(row)
        if any(
            not math.isclose(
                math.fsum(row[column] for row in matrix),
                1.0,
                abs_tol=2e-7,
            )
            for column in range(4)
        ):
            raise ValueError("typing profile rank transition is not doubly stochastic")
        return tuple(matrix)

    @property
    def maximum_total_gap_ms(self) -> float:
        return float(self.limits["maximum_total_gap_ms"])

    @property
    def maximum_transport_unit_ms(self) -> float:
        return float(self.limits["maximum_transport_unit_ms"])

    def start(self, random: RandomSource, *, custom: bool = False) -> OperationState:
        if custom:
            return OperationState(0.0)
        index = _draw([float(style["weight"]) for style in self.styles], random)
        return OperationState(float(self.styles[index]["speed_log"]))

    def _transformed_quantiles(self, exponent: float) -> dict[str, tuple[float, ...]]:
        cached = self._quantile_cache.get(exponent)
        if cached is not None:
            self._quantile_cache.move_to_end(exponent)
            return cached
        result = {}
        for name, values in self.class_quantiles.items():
            if name not in NON_BOUNDARY_CLASSES:
                result[name] = values
                continue
            class_center, _ = _piecewise_moments(values)
            powered = tuple((value / class_center) ** exponent for value in values)
            powered_center, _ = _piecewise_moments(powered)
            result[name] = tuple(class_center * value / powered_center for value in powered)
        self._quantile_cache[exponent] = result
        if len(self._quantile_cache) > 128:
            self._quantile_cache.popitem(last=False)
        return result

    def _expected_rate(
        self,
        scale: float,
        quantiles: Mapping[str, Sequence[float]],
        *,
        custom: bool,
    ) -> float:
        styles = (
            ((1.0, 0.0),)
            if custom
            else tuple((float(style["weight"]), float(style["speed_log"])) for style in self.styles)
        )
        minimum = float(self.limits["minimum_interval_ms"])
        rates = []
        for style_weight, speed_log in styles:
            speed = math.exp(speed_log)
            expected_gap = math.fsum(
                class_weight
                * _piecewise_clipped_mean(
                    tuple(scale * speed * value for value in quantiles[name]),
                    minimum,
                    self.class_maximum_ms[name],
                )
                for name, class_weight in self.reference_class_weights.items()
            )
            rates.append(style_weight * 12_000.0 / expected_gap)
        return math.fsum(rates)

    def _scale_for_quantiles(
        self,
        wpm: float,
        quantiles: Mapping[str, Sequence[float]],
        *,
        custom: bool,
    ) -> float:
        low, high = 0.001, 100_000.0
        if (
            not self._expected_rate(low, quantiles, custom=custom)
            >= wpm
            >= self._expected_rate(high, quantiles, custom=custom)
        ):
            raise ValueError("requested WPM is outside profile support")
        for _ in range(56):
            middle = (low + high) / 2
            if self._expected_rate(middle, quantiles, custom=custom) > wpm:
                low = middle
            else:
                high = middle
        return (low + high) / 2

    def _non_boundary_cv(self, quantiles: Mapping[str, Sequence[float]]) -> float:
        total_weight = math.fsum(
            self.reference_class_weights[name] for name in NON_BOUNDARY_CLASSES
        )
        if total_weight <= 0:
            raise ValueError("non-boundary reference weights are invalid")
        class_moments = []
        for name in NON_BOUNDARY_CLASSES:
            class_weight = self.reference_class_weights[name] / total_weight
            values = quantiles[name]
            center, _ = _piecewise_moments(values)
            mean, second = _piecewise_moments(tuple(value / center for value in values))
            class_moments.append((class_weight, mean, second))
        mean = math.fsum(weight * value for weight, value, _ in class_moments)
        second = math.fsum(weight * value for weight, _, value in class_moments)
        variance = max(second - mean * mean, 0.0)
        return math.sqrt(variance) / mean

    def calibration(self, wpm: float, iki_cv: float | None = None) -> tuple[float, float]:
        wpm = _finite_number(wpm, "custom WPM")
        if (
            not 10 <= wpm <= 200
            or iki_cv is not None
            and (not math.isfinite(float(iki_cv)) or not 0 <= float(iki_cv) <= 1)
        ):
            raise ValueError("custom timing values are invalid")
        key = wpm, None if iki_cv is None else float(iki_cv)
        cached = self._calibration_cache.get(key)
        if cached is not None:
            self._calibration_cache.move_to_end(key)
            return cached
        custom = iki_cv is not None
        exponent = 1.0
        if iki_cv is not None:
            target_cv = float(iki_cv)
            if target_cv == 0:
                exponent = 0.0
            else:
                low, high = 0.0, 1.0
                while self._non_boundary_cv(self._transformed_quantiles(high)) < target_cv:
                    high *= 2
                    if high > 128:
                        raise ValueError("custom timing values are outside profile support")
                for _ in range(48):
                    middle = (low + high) / 2
                    if self._non_boundary_cv(self._transformed_quantiles(middle)) < target_cv:
                        low = middle
                    else:
                        high = middle
                exponent = (low + high) / 2
        quantiles = self._transformed_quantiles(exponent)
        if iki_cv is None and wpm == float(self.profile.get("nominal_wpm", -1)):
            scale = float(self.model["calibration_scale"])
        else:
            scale = self._scale_for_quantiles(wpm, quantiles, custom=custom)
        result = scale, exponent
        self._calibration_cache[key] = result
        if len(self._calibration_cache) > 256:
            self._calibration_cache.popitem(last=False)
        return result

    def expected_wpm(self, wpm: float, iki_cv: float | None = None) -> float:
        scale, exponent = self.calibration(wpm, iki_cv)
        return self._expected_rate(
            scale,
            self._transformed_quantiles(exponent),
            custom=iki_cv is not None,
        )

    def sample_gap(
        self,
        state: OperationState,
        gap_class: str,
        scale: float,
        random: RandomSource,
        *,
        residual_exponent: float = 1.0,
    ) -> GapSample:
        if gap_class not in self.class_quantiles:
            raise ValueError("unknown typing gap class")
        probability = min(max(float(random.random()), 0.0), math.nextafter(1.0, 0.0))
        quantiles = self._transformed_quantiles(residual_exponent)[gap_class]
        raw = scale * math.exp(state.speed_log) * _quantile(quantiles, probability)
        total = min(
            self.class_maximum_ms[gap_class],
            max(float(self.limits["minimum_interval_ms"]), raw),
        )
        return GapSample(gap_class, probability, total, min(int(probability * 4), 3))

    def _rank_draw(
        self,
        previous: int | None,
        random: RandomSource,
    ) -> tuple[int, float]:
        draw = min(max(float(random.random()), 0.0), math.nextafter(1.0, 0.0))
        if not hasattr(self, "rank_transition") or previous is None:
            return min(int(draw * 4), 3), draw
        row = self.rank_transition[previous]
        cumulative = 0.0
        for rank_bin, weight in enumerate(row):
            upper = cumulative + weight
            if draw < upper or rank_bin == 3:
                within = 0.0 if weight == 0 else (draw - cumulative) / weight
                within = min(max(within, 0.0), math.nextafter(1.0, 0.0))
                return rank_bin, (rank_bin + within) / 4
            cumulative = upper
        raise AssertionError("unreachable rank transition")

    def simulate(
        self,
        gap_classes: Sequence[str],
        wpm: float,
        random: RandomSource,
        iki_cv: float | None = None,
        *,
        rank_resets: Sequence[bool] | None = None,
    ) -> tuple[GapSample, ...]:
        if rank_resets is not None and len(rank_resets) != len(gap_classes):
            raise ValueError("rank reset markers do not match typing gaps")
        state = self.start(random, custom=iki_cv is not None)
        scale, exponent = self.calibration(wpm, iki_cv)
        result = []
        previous_rank = None
        for index, gap_class in enumerate(gap_classes):
            if gap_class not in self.class_quantiles:
                raise ValueError("unknown typing gap class")
            if rank_resets is not None and rank_resets[index]:
                previous_rank = None
            rank_bin, probability = self._rank_draw(previous_rank, random)
            quantiles = self._transformed_quantiles(exponent)[gap_class]
            raw = scale * math.exp(state.speed_log) * _quantile(quantiles, probability)
            total = min(
                self.class_maximum_ms[gap_class],
                max(float(self.limits["minimum_interval_ms"]), raw),
            )
            result.append(GapSample(gap_class, probability, total, rank_bin))
            previous_rank = rank_bin
        return tuple(result)


__all__ = ["CLASSES", "ArtifactInterpreter", "GapSample", "OperationState", "RandomSource"]
