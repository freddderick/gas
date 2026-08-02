"""Temporal filters that keep the correction steady between frames.

Landmark detection is independent per frame, so its output jitters by a fraction
of a pixel even on a still subject. Feeding that straight into the warp makes
the eyes shimmer, which is far more noticeable than the jitter itself. The
correction is filtered rather than the landmarks, so a genuine saccade still
comes through at full speed.
"""

from __future__ import annotations

import numpy as np


class OneEuroFilter:
    """Low-pass filter whose cutoff rises with the signal's own speed.

    Slow movement is filtered hard, which removes jitter; fast movement is barely
    filtered at all, which keeps saccades and blinks from lagging behind the
    face. ``min_cutoff`` sets the resting smoothness in hertz and ``beta`` how
    readily it gives way to motion.
    """

    def __init__(self, min_cutoff: float = 1.6, beta: float = 0.05, d_cutoff: float = 1.0):
        if min_cutoff <= 0 or d_cutoff <= 0:
            raise ValueError("cutoffs must be positive")
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self._value: np.ndarray | None = None
        self._derivative: np.ndarray | None = None

    @staticmethod
    def _alpha(cutoff: float | np.ndarray, dt: float) -> np.ndarray:
        tau = 1.0 / (2.0 * np.pi * np.asarray(cutoff, dtype=np.float64))
        return 1.0 / (1.0 + tau / max(dt, 1e-6))

    def reset(self) -> None:
        self._value = None
        self._derivative = None

    def __call__(self, sample: np.ndarray, dt: float) -> np.ndarray:
        x = np.asarray(sample, dtype=np.float64)
        if self._value is None or self._derivative is None or self._value.shape != x.shape:
            self._value = x.copy()
            self._derivative = np.zeros_like(x)
            return x.copy()

        raw_derivative = (x - self._value) / max(dt, 1e-6)
        a_d = self._alpha(self.d_cutoff, dt)
        self._derivative = a_d * raw_derivative + (1.0 - a_d) * self._derivative

        cutoff = self.min_cutoff + self.beta * np.abs(self._derivative)
        a = self._alpha(cutoff, dt)
        self._value = a * x + (1.0 - a) * self._value
        return self._value.copy()


class BlinkGate:
    """Suppresses correction while an eye is closing, with hysteresis.

    A closing eye has almost no visible sclera, so there is nothing for the warp
    to slide the iris across, and the landmark positions get unreliable at the
    same moment. Two thresholds keep the gate from chattering when someone's eye
    aspect ratio sits near the boundary, and the gain moves gradually so the
    correction fades rather than snapping off mid-blink.
    """

    def __init__(self, close_below: float = 0.14, open_above: float = 0.20, rate: float = 0.35):
        if open_above <= close_below:
            raise ValueError("open_above must exceed close_below")
        self.close_below = float(close_below)
        self.open_above = float(open_above)
        self.rate = float(np.clip(rate, 1e-3, 1.0))
        self._closed = False
        self._gain = 1.0

    @property
    def gain(self) -> float:
        return self._gain

    def reset(self) -> None:
        self._closed = False
        self._gain = 1.0

    def update(self, openness: float) -> float:
        """Feed this frame's eye aspect ratio and get the correction gain."""
        if self._closed:
            if openness >= self.open_above:
                self._closed = False
        elif openness <= self.close_below:
            self._closed = True

        target = 0.0 if self._closed else 1.0
        self._gain += (target - self._gain) * self.rate
        if abs(self._gain - target) < 1e-3:
            self._gain = target
        return self._gain
