"""GazeFix — gaze correction for talking-head video.

Redirects a subject's eyes towards the lens by measuring where each eye is
actually looking, working out where it would have to look to meet the camera,
and warping the eye region to close the gap.

Typical use::

    from gazefix import CorrectionSettings, correct_video

    report = correct_video("interview.mp4", "interview_fixed.mp4",
                           CorrectionSettings(strength=0.8))
    print(report.stats)
"""

from .anatomy import EyeSide
from .camera import CameraModel
from .config import CorrectionSettings
from .headpose import HeadPose
from .pipeline import ClipReport, correct_image, correct_video, split_comparison
from .warp import WarpParams

__version__ = "0.1.0"

__all__ = [
    "CameraModel",
    "ClipReport",
    "CorrectionSettings",
    "EyeSide",
    "HeadPose",
    "WarpParams",
    "correct_image",
    "correct_video",
    "split_comparison",
    "__version__",
]
