# What warping can and cannot do

GazeFix redirects a gaze by moving the pixels that are already in the frame. It
never invents an eye. That single choice sets everything below, and it is worth
being precise about, because the failure mode of a gaze corrector that oversells
itself is a video full of people who look subtly wrong.

## The geometric ceiling

The visible eyeball has to slide inside the eye opening while the eyelids stay
where they are. So the displacement field has to fall back to zero at the lid
margins, and the only room available for that ramp is the depth of the opening
itself — for an adult with normally open eyes, roughly 4 pixels for every 8.5
pixels of iris radius.

Once the requested shift approaches that depth, the ramp is steeper than one
pixel per pixel. The map stops being injective: it folds, and a fold in an eye
looks like a crease or a smear. `warp.min_jacobian` detects this and
`warp.warp_eye` scales the whole field back until it is gone, which is why
asking for more past that point delivers less, not more.

## What that costs in degrees

The eyeball's centre of rotation sits about two iris-radii behind the surface,
so a shift of *d* pixels corresponds to about `asin(d / (2.05 × iris_radius))`
of gaze. With an opening depth around 0.45 of the iris radius, the ceiling lands
near **10–13° of requested correction**, and the delivered change a viewer
actually perceives is a fraction of that.

That fraction is not a fudge factor, it is anatomy: the iris is taller than the
eye opening, so the lids clip it top and bottom. Moving the eyeball down by two
pixels does not move the *visible* dark region by two pixels, because that
region is bounded above and below by lids that have not moved. Vertical gaze in
a real face is carried as much by eyelid position as by iris position, which is
why `WarpParams.lid_follow` exists and why pushing it too high makes people look
sleepy rather than downcast.

## The measured response

From `tools/measure_fidelity.py` on the test portrait (iris radius 8.5 px,
opening depth 4.0 px), asking for a vertical shift as a multiple of the opening
depth:

| asked (× depth) | delivered (px) | kept | field unfolded |
|---|---|---|---|
| 0.25 | 0.44 | 0.43 | 1.00 |
| 0.50 | 1.01 | 0.50 | 1.00 |
| 0.75 | 1.61 | 0.53 | 1.00 |
| 1.00 | 2.22 | 0.55 | 1.00 |
| 1.50 | 2.33 | 0.39 | 0.70 |
| 2.00 | 2.15 | 0.27 | 0.49 |

Delivery rises until the request reaches the opening's depth and then flattens —
the fold guard starts clawing the field back, and the extra request buys
nothing. That knee is where `gaze.BUDGET_FRACTION` is set, and
`ClipReport.stats["budget_limited_fraction"]` reports how often a clip hit it.

Reproduce it with:

```sh
python tools/fetch_fixtures.py
python tools/measure_fidelity.py
```

## Where the model itself is approximate

- **The lens position is assumed, not measured.** Everything hinges on knowing
  where the camera was relative to the eyes. GazeFix assumes the frame centre,
  which is right for footage straight out of a camera and wrong for anything
  cropped or reframed. Nothing in the picture reveals the true lens position, so
  it is a setting rather than something inferred — and getting it wrong biases
  every correction in the clip. This is the single most common reason a run does
  nothing useful.
- **Focal length is assumed too.** `fov_deg` defaults to 60°, typical of a
  laptop webcam. A long lens on a tight shot wants a smaller value.
- **Head pose comes from the detector**, which computes it under its own assumed
  camera. On unusual framing that adds error on top of the assumption above.
- **One free anatomical parameter.** Where the eyeball's centre of rotation
  projects between the eye's corners varies between people. `calibrate.py` fits
  it per subject from binocular agreement, which needs a dozen usable frames; a
  still or a very short clip falls back to a population average.

## When to reach for something else

Warping is the right tool for the everyday case: one person, roughly facing the
camera, reading from a screen just below or beside the lens. It is the wrong
tool for a profile view, for a glance right off the edge of frame, or for
turning a downward-tilted phone shot into eye contact. Those need a model that
*redraws* the eye region rather than rearranging it — which is what production
systems like NVIDIA Maxine and Apple's attention correction do, at the cost of a
trained generative model and the artefacts that come with one.

GazeFix reports what it could not do instead of faking it. A run that leaves the
eyes alone and says so is working correctly.
