"""End-to-end correction of a clip: calibrate, then correct every frame."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .anatomy import OUTER_CORNER_WEIGHT
from .calibrate import AnchorCalibration, fit_outer_corner_weight
from .camera import CameraModel
from .config import CorrectionSettings
from .landmarks import FaceTracker
from .processor import ClipStats, GazeCorrector, collect_calibration_samples
from .video import FrameSink, VideoInfo, probe, read_frames

log = logging.getLogger(__name__)

ProgressFn = Callable[[float, str], None]

#: Eyes at least this open are trusted for calibration; blinks are skipped.
CALIBRATION_MIN_OPENNESS = 0.18


@dataclass
class ClipReport:
    """What a run produced and what it did."""

    output_path: str
    codec: str
    audio_copied: bool
    source: dict
    stats: dict
    calibration: dict
    settings: dict
    elapsed_s: float
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _calibration_stride(info: VideoInfo, budget: int) -> int:
    if info.frame_count > 0:
        return max(1, info.frame_count // max(budget, 1))
    return 5  # length unknown; sample sparsely and stop once the budget is met


def calibrate_clip(
    source: Path,
    settings: CorrectionSettings,
    info: VideoInfo,
    progress: ProgressFn | None = None,
) -> AnchorCalibration:
    """Fit the subject's eyeball anchor from a sample of frames.

    Skipped entirely when ``settings.auto_calibrate`` is off, in which case the
    population default stands.
    """
    if not settings.auto_calibrate:
        return AnchorCalibration.default()

    stride = _calibration_stride(info, settings.calibration_frames)
    samples: list[tuple] = []
    with FaceTracker(max_faces=settings.max_faces) as tracker:
        for index, frame in read_frames(source, stride=stride):
            timestamp_ms = int(index * 1000.0 / info.fps)
            faces = tracker.detect(frame, timestamp_ms)
            samples.extend(collect_calibration_samples(faces, CALIBRATION_MIN_OPENNESS))
            if progress and settings.calibration_frames:
                progress(min(len(samples) / settings.calibration_frames, 1.0), "calibrating")
            if len(samples) >= settings.calibration_frames:
                break
    return fit_outer_corner_weight(samples)


def correct_video(
    source: str | Path,
    output: str | Path,
    settings: CorrectionSettings | None = None,
    progress: ProgressFn | None = None,
) -> ClipReport:
    """Correct every frame of a clip and write the result.

    Args:
        source: Input video.
        output: Desired output path. The extension may change if ffmpeg is not
            available -- the report names the file that was actually written.
        settings: Tuning; defaults suit a single webcam subject.
        progress: Called as ``(fraction, stage)`` while the run proceeds.
    """
    started = time.monotonic()
    source, output = Path(source), Path(output)
    settings = settings or CorrectionSettings()
    info = probe(source)
    camera = CameraModel(
        width=info.width,
        height=info.height,
        fov_deg=settings.fov_deg,
        principal_point=settings.principal_point_px(info.width, info.height),
    )
    warnings: list[str] = []

    calibration = calibrate_clip(source, settings, info, progress)
    if settings.auto_calibrate and not calibration.converged:
        warnings.append(
            "Per-subject calibration did not converge; using the population default "
            "eyeball anchor. Corrections may be slightly biased towards or away from the nose."
        )

    corrector = GazeCorrector(camera, settings, outer_weight=calibration.outer_weight)
    stats = ClipStats()
    frame_period = 1.0 / info.fps

    with FaceTracker(max_faces=settings.max_faces) as tracker, \
            FrameSink(output, info, source) as sink:
        for index, frame in read_frames(source):
            faces = tracker.detect(frame, int(index * 1000.0 / info.fps))
            corrected, report = corrector.process(frame, faces, frame_period)
            sink.write(corrected)
            stats.observe(report)
            if progress and info.frame_count > 0:
                progress(min((index + 1) / info.frame_count, 1.0), "correcting")
    encoded = sink.result

    if stats.frames_with_face == 0:
        warnings.append("No face was detected in this clip; the output matches the input.")
    elif stats.frames_with_face < 0.5 * max(stats.frames, 1):
        warnings.append(
            f"A face was found in only {stats.frames_with_face} of {stats.frames} frames, "
            "so much of the clip is unchanged."
        )
    mean_offset = stats.as_dict()["mean_offset_deg"]
    if stats.frames_with_face and stats.frames_corrected == 0:
        warnings.append(
            f"Nothing was corrected: the subject's gaze averaged {mean_offset:.0f} degrees from "
            f"the lens, past the {settings.max_correction_deg:.0f} degree cutoff that leaves a "
            "deliberate glance away alone. If the footage was cropped or reframed, the lens is "
            "no longer at the frame centre -- set the lens position to where the camera actually "
            "was. Otherwise raise the maximum correction."
        )
    if stats.eye_samples and stats.budget_limited_samples > 0.25 * stats.eye_samples:
        warnings.append(
            "The requested correction exceeded what warping can deliver on a large share of "
            "frames, so those eyes were only partly corrected. This usually means the camera "
            "is far off the subject's eyeline."
        )
    if not encoded.audio_copied:
        warnings.append("ffmpeg was not available, so the output has no audio track.")

    return ClipReport(
        output_path=str(encoded.path),
        codec=encoded.codec,
        audio_copied=encoded.audio_copied,
        source={
            "width": info.width,
            "height": info.height,
            "fps": round(info.fps, 3),
            "frames": info.frame_count,
            "duration_s": round(info.duration_s, 2),
        },
        stats=stats.as_dict(),
        calibration={
            "outer_corner_weight": round(calibration.outer_weight, 4),
            "default_weight": OUTER_CORNER_WEIGHT,
            "samples": calibration.samples,
            "converged": calibration.converged,
            "binocular_residual_deg": (
                None if np.isnan(calibration.residual_deg) else round(calibration.residual_deg, 3)
            ),
        },
        settings=settings.to_dict(),
        elapsed_s=round(time.monotonic() - started, 2),
        warnings=warnings,
    )


def correct_image(
    image: np.ndarray,
    settings: CorrectionSettings | None = None,
    tracker: FaceTracker | None = None,
) -> tuple[np.ndarray, dict]:
    """Correct a single still. Useful for previews and for testing.

    Skips per-subject calibration, which needs more than one frame.
    """
    settings = settings or CorrectionSettings()
    height, width = image.shape[:2]
    camera = CameraModel(
        width, height, settings.fov_deg, settings.principal_point_px(width, height)
    )
    owned = tracker is None
    tracker = tracker or FaceTracker(max_faces=settings.max_faces)
    try:
        faces = tracker.detect(image, 0)
        corrector = GazeCorrector(camera, settings)
        corrected, report = corrector.process(image, faces, 1 / 30)
    finally:
        if owned:
            tracker.close()
    return corrected, {
        "faces_detected": report.faces_detected,
        "eyes": [asdict(eye) for eye in report.eyes],
    }


def split_comparison(before: np.ndarray, after: np.ndarray, position: float = 0.5) -> np.ndarray:
    """Join two frames into one, split vertically, with a marker on the seam."""
    if before.shape != after.shape:
        raise ValueError("frames must have identical shapes")
    width = before.shape[1]
    cut = int(np.clip(position, 0.0, 1.0) * width)
    out = after.copy()
    out[:, :cut] = before[:, :cut]
    if 0 < cut < width:
        cv2.line(out, (cut, 0), (cut, out.shape[0]), (255, 255, 255), 1)
    return out
