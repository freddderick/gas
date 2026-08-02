"""The image operation that actually redirects a gaze.

Two displacement fields are layered over the eye region:

* an **eyeball** layer confined to the eye opening, carrying the full
  correction. It translates everything visible of the eyeball, not just the
  iris: when an eye rotates, the whole exposed sphere turns with it, so the
  sclera travels too.
* a **socket** layer over the lids and nearby skin, carrying a fraction of the
  correction. Eyelids ride with the eyes in real faces -- the upper lid drops
  when you look down -- and without this the corrected eye reads as a stare.

Both layers are pinned to zero at the inner and outer corners of the eye. Those
corners are anchored to the orbital rim and do not move when gaze changes, and
letting them drift does more than look wrong: the corners are what
:mod:`gazefix.gaze` measures gaze against, so a warp that moves them cancels out
its own correction.

The layers are summed and resampled in one pass, so the eye is never composited
over itself. A fold guard scales the field back if it ever becomes
non-injective, which is what stops the eye smearing when a clip asks for more
correction than the geometry can pay for.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .gaze import smoothstep


@dataclass(frozen=True)
class WarpParams:
    """Shape of the two displacement layers."""

    #: Fraction of the correction carried by the eyelids and surrounding skin,
    #: given separately for horizontal and vertical. Lids track vertical gaze
    #: closely and barely move horizontally. This rides *on top of* the eyeball
    #: layer rather than replacing part of it.
    lid_follow: tuple[float, float] = (0.10, 0.35)
    #: Socket ellipse size, as multiples of the eye's corner-to-corner width.
    socket_radius: tuple[float, float] = (1.05, 0.50)
    #: Where the socket layer starts fading, as a fraction of that ellipse.
    socket_plateau: float = 0.40
    #: Radius around each corner of the eye held fixed, as a fraction of the
    #: eye's width.
    corner_pin: float = 0.16
    #: Share of the distance from a lid margin to the middle of the opening
    #: spent tapering. The rest is a plateau that translates rigidly. Lower
    #: moves more of the eye at full strength but folds at a smaller correction.
    margin_taper: float = 0.45
    #: Smallest Jacobian determinant tolerated before the field is scaled back.
    min_jacobian: float = 0.08


@dataclass(frozen=True)
class WarpResult:
    image: np.ndarray
    #: Fraction of the requested displacement that survived the fold guard.
    applied_fraction: float


def _region_of_interest(
    lid_polygon: np.ndarray, params: WarpParams, shape: tuple[int, int]
) -> tuple[int, int, int, int]:
    height, width = shape
    span = float(lid_polygon[:, 0].max() - lid_polygon[:, 0].min())
    pad_x = int(np.ceil(span * params.socket_radius[0] + 6))
    pad_y = int(np.ceil(span * params.socket_radius[1] + 6))
    x0 = max(int(np.floor(lid_polygon[:, 0].min())) - pad_x, 0)
    y0 = max(int(np.floor(lid_polygon[:, 1].min())) - pad_y, 0)
    x1 = min(int(np.ceil(lid_polygon[:, 0].max())) + pad_x, width)
    y1 = min(int(np.ceil(lid_polygon[:, 1].max())) + pad_y, height)
    return x0, y0, x1, y1


def _normalised_depth(mask: np.ndarray) -> np.ndarray:
    """Height within the eye opening, per column: 0 at each lid margin, 1 mid-way.

    Returns an array shaped like ``mask``, meaningful only where the mask is
    set. Columns thinner than a couple of pixels are reported as fully tapered,
    which keeps the corners of the opening from moving.
    """
    rows = np.arange(mask.shape[0], dtype=np.float32)[:, None]
    inside = mask > 0
    big = np.float32(mask.shape[0] + 1)
    top = np.where(inside, rows, big).min(axis=0)
    bottom = np.where(inside, rows, np.float32(-1)).max(axis=0)
    span = bottom - top
    usable = span > 1.0
    depth = np.zeros_like(mask, dtype=np.float32)
    np.divide(
        rows - top[None, :],
        np.where(usable, span, 1.0)[None, :],
        out=depth,
        where=np.broadcast_to(usable[None, :], mask.shape),
    )
    # Fold the [0, 1] span onto [0, 0.5] measured from the nearer margin, so a
    # single taper width applies at both lids.
    return np.clip(np.minimum(depth, 1.0 - depth), 0.0, 0.5) * 2.0


def build_displacement_field(
    shape: tuple[int, int],
    lid_polygon: np.ndarray,
    corners: tuple[np.ndarray, np.ndarray],
    displacement: np.ndarray,
    params: WarpParams = WarpParams(),
) -> tuple[np.ndarray, np.ndarray]:
    """Backward-map offsets for one eye patch, in patch-local coordinates.

    Args:
        shape: ``(height, width)`` of the patch.
        lid_polygon: Eyelid margin, in patch-local pixels.
        corners: Outer and inner corners of the eye, in patch-local pixels.
            The field is held at zero around these.
        displacement: How far the eyeball should move, in pixels.

    Returns ``(fx, fy)`` such that the output pixel at ``(x, y)`` is sampled
    from ``(x + fx, y + fy)`` of the input. Note the sign: to move the eye
    *down* the map reaches *up*.
    """
    height, width = shape
    d = np.asarray(displacement, dtype=np.float64)
    d_lid = d * np.asarray(params.lid_follow, dtype=np.float64)

    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    poly = np.asarray(lid_polygon, dtype=np.float64)
    span = max(float(np.linalg.norm(np.asarray(corners[0]) - np.asarray(corners[1]))), 1e-6)

    # --- corner pinning, shared by both layers -----------------------------
    pin_radius = max(span * params.corner_pin, 1e-6)
    to_corner = np.minimum(
        np.hypot(xx - corners[0][0], yy - corners[0][1]),
        np.hypot(xx - corners[1][0], yy - corners[1][1]),
    )
    w_corner = smoothstep(0.0, pin_radius, to_corner)

    # --- socket layer ------------------------------------------------------
    socket_center = poly.mean(axis=0)
    rx = max(span * params.socket_radius[0], 1e-6)
    ry = max(span * params.socket_radius[1], 1e-6)
    q = np.hypot((xx - socket_center[0]) / rx, (yy - socket_center[1]) / ry)
    w_socket = (1.0 - smoothstep(params.socket_plateau, 1.0, q)) * w_corner

    # --- eyeball layer -----------------------------------------------------
    # Taper in normalised aperture coordinates rather than by distance to the
    # boundary. The eye opening is a thin sliver, so a distance transform is
    # small almost everywhere in it and would damp the whole eye; normalising
    # per column instead leaves a plateau down the middle that translates
    # rigidly, which is where the iris actually is.
    mask = np.zeros((height, width), np.uint8)
    cv2.fillPoly(mask, [np.round(poly).astype(np.int32)], 255)
    depth = _normalised_depth(mask)
    band = float(np.clip(params.margin_taper, 0.05, 1.0))
    w_eyeball = np.where(mask > 0, smoothstep(0.0, band, depth), 0.0).astype(np.float32)
    # The opening is measured per column off a rasterised mask, so its height
    # steps by whole pixels from one column to the next. Left alone those steps
    # are near-vertical cliffs in the weight, and the fold guard reads them as a
    # tearing warp and throttles the whole correction. Smoothing costs a little
    # of the plateau and buys back most of the usable range.
    sigma = max(0.05 * span, 0.8)
    w_eyeball = cv2.GaussianBlur(w_eyeball, (0, 0), sigma) * w_corner

    fx = -(d_lid[0] * w_socket + d[0] * w_eyeball)
    fy = -(d_lid[1] * w_socket + d[1] * w_eyeball)
    return fx.astype(np.float32), fy.astype(np.float32)


def min_jacobian(fx: np.ndarray, fy: np.ndarray) -> float:
    """Smallest determinant of the backward map's Jacobian.

    Stays near 1 for a gentle warp. Dropping towards zero means the map is about
    to fold, which shows up in the output as a mirrored crease through the eye.
    """
    if fx.shape[0] < 3 or fx.shape[1] < 3:
        return 1.0
    dfx_dy, dfx_dx = np.gradient(fx.astype(np.float64))
    dfy_dy, dfy_dx = np.gradient(fy.astype(np.float64))
    det = (1.0 + dfx_dx) * (1.0 + dfy_dy) - dfx_dy * dfy_dx
    return float(det.min())


def warp_eye(
    image: np.ndarray,
    lid_polygon: np.ndarray,
    corners: tuple[np.ndarray, np.ndarray],
    displacement: np.ndarray,
    params: WarpParams = WarpParams(),
) -> WarpResult:
    """Redirect one eye by sliding the visible eyeball ``displacement`` pixels.

    Args:
        image: Full BGR frame. Not modified.
        lid_polygon: ``(N, 2)`` eyelid margin, in frame pixels.
        corners: Outer and inner corners of the eye, in frame pixels.
        displacement: ``(dx, dy)`` the eyeball should move.
    """
    d = np.asarray(displacement, dtype=np.float64)
    if float(np.linalg.norm(d)) < 1e-3:
        return WarpResult(image, 1.0)

    x0, y0, x1, y1 = _region_of_interest(np.asarray(lid_polygon), params, image.shape[:2])
    if x1 - x0 < 4 or y1 - y0 < 4:
        return WarpResult(image, 0.0)

    patch = image[y0:y1, x0:x1]
    origin = np.array([x0, y0], dtype=np.float64)
    local_poly = np.asarray(lid_polygon, dtype=np.float64) - origin
    local_corners = (
        np.asarray(corners[0], dtype=np.float64) - origin,
        np.asarray(corners[1], dtype=np.float64) - origin,
    )

    # Back the displacement off until the map is injective. In practice this
    # only engages on eyes that are nearly shut or on very large corrections.
    fraction = 1.0
    for _ in range(6):
        fx, fy = build_displacement_field(
            patch.shape[:2], local_poly, local_corners, d * fraction, params
        )
        if min_jacobian(fx, fy) >= params.min_jacobian:
            break
        fraction *= 0.7
    else:
        return WarpResult(image, 0.0)

    map_x = (np.arange(patch.shape[1], dtype=np.float32)[None, :] + fx)
    map_y = (np.arange(patch.shape[0], dtype=np.float32)[:, None] + fy)
    warped = cv2.remap(patch, map_x, map_y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    # Only take resampled pixels where the field is actually doing something, so
    # the interpolation does not soften skin that was meant to stay put.
    active = (np.hypot(fx, fy) > 1e-3).astype(np.float32)
    alpha = cv2.GaussianBlur(active, (0, 0), 1.2)[..., None]
    out = image.copy()
    out[y0:y1, x0:x1] = np.clip(
        warped.astype(np.float32) * alpha + patch.astype(np.float32) * (1.0 - alpha), 0, 255
    ).astype(image.dtype)
    return WarpResult(out, fraction)
