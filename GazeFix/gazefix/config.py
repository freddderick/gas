"""Tunable settings for a correction run."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

from .warp import WarpParams


@dataclass
class CorrectionSettings:
    """Everything a caller can turn.

    The defaults target the common case: one person on a webcam, reading from a
    screen a little below or beside the lens.
    """

    #: Overall scale on the correction. 1.0 puts the eyes on the lens; lower
    #: values keep some of the original offset, which several people prefer
    #: because full correction can read as unblinking.
    strength: float = 1.0

    #: Corrections start fading past ``falloff_start_deg`` and stop entirely past
    #: ``max_correction_deg``, so a deliberate glance away is left alone. See
    #: ``gaze.look_away_attenuation``.
    falloff_start_deg: float = 11.0
    max_correction_deg: float = 16.0

    #: Head rotation past which a flat warp cannot sell the result.
    max_head_yaw_deg: float = 32.0
    max_head_pitch_deg: float = 26.0

    #: Eye aspect ratios bounding the blink gate.
    blink_close_ear: float = 0.14
    blink_open_ear: float = 0.20

    #: Horizontal field of view of the taking lens. 60 degrees suits a laptop
    #: webcam; a longer lens or a tighter shot wants less.
    fov_deg: float = 60.0

    #: Where the lens sits, in fractions of the frame, with (0.5, 0.5) at the
    #: centre and (0, 0) at the top left. The centre is correct for footage
    #: straight out of a camera, and wrong for anything cropped or reframed --
    #: the eyes are then being aimed at a point the lens never occupied. Values
    #: outside [0, 1] are allowed and mean the lens was outside the final frame,
    #: which is the usual case for a vertical crop of a wider shot.
    lens_position: tuple[float, float] = (0.5, 0.5)

    #: One-euro filter on the per-eye correction.
    smoothing_min_cutoff: float = 1.6
    smoothing_beta: float = 0.05

    #: Fit the eyeball anchor to this subject instead of using the population
    #: default, using the binocular agreement signal in ``calibrate``.
    auto_calibrate: bool = True
    calibration_frames: int = 90

    max_faces: int = 1
    warp: WarpParams = field(default_factory=WarpParams)

    def __post_init__(self) -> None:
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError("strength must be within [0, 1]")
        if self.max_correction_deg < self.falloff_start_deg:
            raise ValueError("max_correction_deg must be at least falloff_start_deg")
        if self.blink_open_ear <= self.blink_close_ear:
            raise ValueError("blink_open_ear must exceed blink_close_ear")
        if self.max_faces < 1:
            raise ValueError("max_faces must be at least 1")
        if not 1.0 < self.fov_deg < 179.0:
            raise ValueError("fov_deg must be within (1, 179)")
        lens = tuple(float(v) for v in self.lens_position)
        if len(lens) != 2 or not all(-2.0 <= v <= 3.0 for v in lens):
            raise ValueError("lens_position must be two values within [-2, 3]")
        self.lens_position = lens

    def principal_point_px(self, width: int, height: int) -> tuple[float, float]:
        """Resolve the lens position against a frame size."""
        return (self.lens_position[0] * width, self.lens_position[1] * height)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CorrectionSettings":
        """Build settings from a dict, ignoring keys the version in use does not know."""
        known = {f.name for f in fields(cls)}
        payload = {k: v for k, v in (data or {}).items() if k in known and v is not None}
        warp = payload.pop("warp", None)
        settings = cls(**payload)
        if isinstance(warp, dict):
            settings.warp = WarpParams(**{
                k: tuple(v) if isinstance(v, list) else v
                for k, v in warp.items()
                if k in {f.name for f in fields(WarpParams)}
            })
        return settings
