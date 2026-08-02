"""Face landmark detection, wrapping the MediaPipe Face Landmarker task."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .anatomy import NUM_LANDMARKS
from .headpose import HeadPose

log = logging.getLogger(__name__)

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_FILENAME = "face_landmarker.task"


def model_cache_dir() -> Path:
    override = os.environ.get("GAZEFIX_MODEL_DIR")
    if override:
        return Path(override)
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "gazefix"


def ensure_model(path: Path | None = None) -> Path:
    """Return a local path to the landmarker model, downloading it once if needed."""
    target = Path(path) if path else model_cache_dir() / MODEL_FILENAME
    if target.exists() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    log.info("downloading face landmarker model to %s", target)
    with urllib.request.urlopen(MODEL_URL, timeout=120) as response:  # noqa: S310
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
            shutil.copyfileobj(response, tmp)
            staged = Path(tmp.name)
    staged.replace(target)
    return target


@dataclass(frozen=True)
class FaceObservation:
    """One detected face in one frame."""

    landmarks: np.ndarray  # (478, 2) pixel coordinates
    pose: HeadPose


class FaceTracker:
    """Detects face landmarks across the frames of one clip.

    Defaults to video mode, which carries tracking state between frames and
    gives noticeably steadier landmarks than detecting each frame from scratch.
    That makes the instance stateful and order-dependent: feed it frames in
    order, and use a fresh tracker per clip. Pass ``video=False`` for unrelated
    stills, which makes the tracker stateless and reusable.
    """

    def __init__(self, max_faces: int = 1, model_path: Path | None = None,
                 min_confidence: float = 0.5, video: bool = True):
        from mediapipe.tasks.python import BaseOptions, vision  # heavy; import lazily

        self._model_path = ensure_model(model_path)
        self._video = video
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self._model_path)),
            running_mode=vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE,
            num_faces=max_faces,
            min_face_detection_confidence=min_confidence,
            min_tracking_confidence=min_confidence,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._closed = False

    def detect(self, frame_bgr: np.ndarray, timestamp_ms: int = 0) -> list[FaceObservation]:
        """Detect faces in one frame.

        Args:
            frame_bgr: Frame in OpenCV's BGR order.
            timestamp_ms: Presentation time. Must increase between calls in
                video mode, and is ignored otherwise.
        """
        import mediapipe as mp

        if self._closed:
            raise RuntimeError("tracker is closed")
        height, width = frame_bgr.shape[:2]
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB),
        )
        result = (
            self._landmarker.detect_for_video(image, int(timestamp_ms))
            if self._video
            else self._landmarker.detect(image)
        )

        faces: list[FaceObservation] = []
        matrices = result.facial_transformation_matrixes or []
        for index, points in enumerate(result.face_landmarks or []):
            if len(points) < NUM_LANDMARKS or index >= len(matrices):
                # Without iris refinement or a pose there is nothing to solve.
                continue
            coords = np.array([[p.x * width, p.y * height] for p in points], dtype=np.float64)
            faces.append(FaceObservation(coords, HeadPose.from_matrix(np.asarray(matrices[index]))))
        return faces

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._landmarker.close()
        except Exception as exc:  # noqa: BLE001
            # Releasing the native graph goes through MediaPipe's own dispatcher
            # thread, which may already be gone during interpreter shutdown. The
            # process is ending either way, and a teardown error here would
            # otherwise surface as a spurious job failure.
            log.debug("face landmarker did not close cleanly: %s", exc)

    def __enter__(self) -> "FaceTracker":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
