#!/usr/bin/env python3
"""Measure how much of a requested eye shift actually reaches the image.

This is the experiment behind ``gaze.BUDGET_FRACTION`` and behind the range
claims in ``docs/limits.md``. It asks the warp for a series of displacements,
scaled against each eye's own opening, and measures what came out by tracking
the centroid of the dark iris region.

    python tools/fetch_fixtures.py
    python tools/measure_fidelity.py

The delivered figure is deliberately pessimistic: it measures the *visible*
iris, which the eyelids clip top and bottom, so it reports the change a viewer
would see rather than the displacement the field applied.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gazefix.anatomy import EYES  # noqa: E402
from gazefix.geometry import aperture_half_height, extract_eye  # noqa: E402
from gazefix.landmarks import FaceTracker  # noqa: E402
from gazefix.warp import WarpParams, warp_eye  # noqa: E402

MULTIPLES = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)


def dark_centroid(image, center, half=(11, 7), upsample=6):
    """Sub-pixel centroid of the dark iris region around ``center``."""
    x0, y0 = int(center[0] - half[0]), int(center[1] - half[1])
    patch = image[y0:y0 + 2 * half[1], x0:x0 + 2 * half[0]].astype(np.float32).mean(axis=2)
    patch = cv2.resize(patch, None, fx=upsample, fy=upsample, interpolation=cv2.INTER_CUBIC)
    weight = np.clip(patch.max() - patch, 0, None) ** 3
    if weight.sum() <= 0:
        return np.array([np.nan, np.nan])
    yy, xx = np.mgrid[0:patch.shape[0], 0:patch.shape[1]]
    return np.array([float((xx * weight).sum() / weight.sum()) / upsample + x0,
                     float((yy * weight).sum() / weight.sum()) / upsample + y0])


def measure(image_path: Path, params: WarpParams) -> None:
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"{image_path}: cannot read", file=sys.stderr)
        return
    with FaceTracker(video=False) as tracker:
        faces = tracker.detect(image, 0)
    if not faces:
        print(f"{image_path}: no face found", file=sys.stderr)
        return

    eye = extract_eye(faces[0].landmarks, EYES[0])
    depth = aperture_half_height(eye.lid_polygon)
    baseline = dark_centroid(image, eye.iris_center)
    print(f"\n{image_path.name}: iris radius {eye.iris_semi_major:.2f} px, "
          f"opening depth {depth:.2f} px, fissure {eye.fissure_width:.1f} px, "
          f"openness {eye.openness:.3f}")
    print(f"  {'axis':>4} {'asked':>7} {'x depth':>8} {'delivered':>10} "
          f"{'kept':>6} {'unfolded':>9}")

    for axis, name in ((0, "x"), (1, "y")):
        for multiple in MULTIPLES:
            displacement = np.zeros(2)
            displacement[axis] = depth * multiple
            result = warp_eye(image, eye.lid_polygon,
                              (eye.outer_corner, eye.inner_corner), displacement, params)
            delivered = dark_centroid(result.image, eye.iris_center) - baseline
            kept = float(delivered @ displacement) / float(displacement @ displacement)
            print(f"  {name:>4} {displacement[axis]:>7.2f} {multiple:>8.2f} "
                  f"{delivered[axis]:>10.2f} {kept:>6.2f} {result.applied_fraction:>9.2f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="*", type=Path,
                        default=[Path(__file__).resolve().parent.parent
                                 / "tests" / "fixtures" / "portrait.jpg"])
    args = parser.parse_args()

    missing = [p for p in args.images if not p.exists()]
    if missing:
        print(f"missing fixtures: {missing}. Run tools/fetch_fixtures.py first.",
              file=sys.stderr)
        return 1
    for path in args.images:
        measure(path, WarpParams())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
