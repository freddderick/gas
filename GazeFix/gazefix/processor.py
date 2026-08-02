"""Frame-level orchestration: measure, gate, smooth, warp, and report."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .anatomy import EYES, OUTER_CORNER_WEIGHT, EyeSide
from .camera import CameraModel
from .config import CorrectionSettings
from .gaze import (
    displacement_budget,
    head_pose_attenuation,
    limit_displacement,
    look_away_attenuation,
    solve_eye,
)
from .geometry import aperture_half_height, extract_eye
from .landmarks import FaceObservation
from .smoothing import BlinkGate, OneEuroFilter
from .warp import warp_eye


@dataclass
class EyeReport:
    side: str
    #: How far off the lens this eye was before correction.
    residual_deg: float
    #: Pixels the iris was actually moved.
    applied_px: float
    #: Combined gating: strength, look-away, head pose, blink.
    gain: float
    #: True when the geometry could not pay for the requested shift.
    budget_limited: bool


@dataclass
class FrameReport:
    frame_index: int
    faces_detected: int
    eyes: list[EyeReport] = field(default_factory=list)

    @property
    def corrected(self) -> bool:
        return any(e.applied_px > 0.05 for e in self.eyes)


@dataclass
class ClipStats:
    """Aggregate of what happened across a clip."""

    frames: int = 0
    frames_with_face: int = 0
    frames_corrected: int = 0
    eye_samples: int = 0
    budget_limited_samples: int = 0
    _residual_sum: float = 0.0
    _applied_sum: float = 0.0
    _residual_max: float = 0.0

    def observe(self, report: FrameReport) -> None:
        self.frames += 1
        if report.faces_detected:
            self.frames_with_face += 1
        if report.corrected:
            self.frames_corrected += 1
        for eye in report.eyes:
            self.eye_samples += 1
            self._residual_sum += eye.residual_deg
            self._applied_sum += eye.applied_px
            self._residual_max = max(self._residual_max, eye.residual_deg)
            if eye.budget_limited:
                self.budget_limited_samples += 1

    def as_dict(self) -> dict:
        n = max(self.eye_samples, 1)
        return {
            "frames": self.frames,
            "frames_with_face": self.frames_with_face,
            "frames_corrected": self.frames_corrected,
            "mean_offset_deg": round(self._residual_sum / n, 2),
            "peak_offset_deg": round(self._residual_max, 2),
            "mean_iris_shift_px": round(self._applied_sum / n, 2),
            "budget_limited_fraction": round(self.budget_limited_samples / n, 3),
        }


class _FaceState:
    """Per-face temporal state. Keyed by detection slot, so it survives frames."""

    def __init__(self, settings: CorrectionSettings):
        self.filters = {
            side: OneEuroFilter(settings.smoothing_min_cutoff, settings.smoothing_beta)
            for side in EyeSide
        }
        self.blinks = {
            side: BlinkGate(settings.blink_close_ear, settings.blink_open_ear)
            for side in EyeSide
        }


class GazeCorrector:
    """Applies gaze correction to the frames of one clip.

    Stateful across frames: it smooths each eye's correction over time and tracks
    blink state, so frames must be fed in order and a fresh instance used per
    clip.
    """

    def __init__(
        self,
        camera: CameraModel,
        settings: CorrectionSettings | None = None,
        outer_weight: float = OUTER_CORNER_WEIGHT,
    ):
        self.camera = camera
        self.settings = settings or CorrectionSettings()
        self.outer_weight = float(outer_weight)
        self._faces: dict[int, _FaceState] = {}
        self._frame_index = -1

    def _state(self, slot: int) -> _FaceState:
        if slot not in self._faces:
            self._faces[slot] = _FaceState(self.settings)
        return self._faces[slot]

    def process(
        self,
        frame: np.ndarray,
        faces: list[FaceObservation],
        dt: float,
    ) -> tuple[np.ndarray, FrameReport]:
        """Correct one frame.

        Args:
            frame: BGR frame. Not modified in place.
            faces: Detections for this frame, in stable slot order.
            dt: Seconds since the previous frame, for the temporal filters.
        """
        self._frame_index += 1
        settings = self.settings
        report = FrameReport(frame_index=self._frame_index, faces_detected=len(faces))
        output = frame

        for slot, face in enumerate(faces):
            state = self._state(slot)
            pose_gain = head_pose_attenuation(
                face.pose, settings.max_head_yaw_deg, settings.max_head_pitch_deg
            )

            for indices in EYES:
                eye = extract_eye(face.landmarks, indices)
                blink_gain = state.blinks[indices.side].update(eye.openness)
                solution = solve_eye(eye, face.pose, self.camera, self.outer_weight)
                if solution is None:
                    state.filters[indices.side].reset()
                    continue

                residual = solution.residual_deg
                gain = (
                    settings.strength
                    * blink_gain
                    * pose_gain
                    * look_away_attenuation(
                        residual, settings.falloff_start_deg, settings.max_correction_deg
                    )
                )
                wanted = solution.displacement_px * gain
                smoothed = state.filters[indices.side](wanted, dt)

                budget = displacement_budget(aperture_half_height(eye.lid_polygon))
                limited, was_limited = limit_displacement(smoothed, budget)

                result = warp_eye(
                    output,
                    eye.lid_polygon,
                    (eye.outer_corner, eye.inner_corner),
                    limited,
                    settings.warp,
                )
                output = result.image
                report.eyes.append(
                    EyeReport(
                        side=indices.side.value,
                        residual_deg=residual,
                        applied_px=float(np.linalg.norm(limited)) * result.applied_fraction,
                        gain=gain,
                        budget_limited=was_limited,
                    )
                )
        return output, report


def collect_calibration_samples(
    faces: list[FaceObservation],
    min_openness: float,
) -> list[tuple]:
    """Turn a frame's detections into calibration triples, skipping shut eyes."""
    samples = []
    for face in faces:
        right = extract_eye(face.landmarks, EYES[0])
        left = extract_eye(face.landmarks, EYES[1])
        if min(right.openness, left.openness) < min_openness:
            continue
        samples.append((right, left, face.pose))
    return samples
