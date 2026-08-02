# GazeFix

A platform for correcting eye gaze in talking-head video. Upload a clip, and the
speaker's eyes are pointed back at the lens.

Everyone who has recorded a video call, an interview, or a piece to camera knows
the problem: you look at the screen, so you never look at the camera, and the
result reads as slightly evasive to whoever watches it. GazeFix measures where
each eye is actually pointing, works out where it would have to point to meet
the lens, and warps the eye region to close the gap.

It is deliberate about what it will not do. Corrections it cannot make
convincingly are reported rather than faked, and a glance that is clearly
deliberate — someone turning to a second monitor — is left alone instead of
being dragged back into an unblinking stare. [`docs/limits.md`](docs/limits.md)
sets out where the ceiling is and how it was measured.

## What is here

| | |
|---|---|
| `gazefix/` | The correction library: detection, gaze geometry, warping, video I/O |
| `gazefix/server/` | A FastAPI service and a dependency-free web front end |
| `gazefix/cli.py` | `gazefix in.mp4 -o out.mp4` for headless and batch use |
| `tools/` | Fixture fetcher and the fidelity measurement behind the range claims |
| `tests/` | 109 tests; the pure-geometry ones need neither a model nor a video |

## Getting started

```sh
cd GazeFix
python -m venv .venv && source .venv/bin/activate
pip install -e '.[server,dev]'
```

The face landmark model (3.6 MB) downloads on first use and is cached under
`~/.cache/gazefix`; set `GAZEFIX_MODEL_DIR` to put it elsewhere.

**Install ffmpeg if you can.** Without it GazeFix still works, but it falls back
to OpenCV's VP9 encoder, which is several times slower and cannot carry an audio
track — your corrected clip comes out silent. With ffmpeg present the output is
H.264 with the original audio copied across.

### The web app

```sh
python -m gazefix.server.app       # http://127.0.0.1:8000
```

Drop in a clip, adjust the controls, and watch the result. While the run is in
progress you can scrub through frames and drag across the picture to wipe
between the original and the correction, so you can judge the settings without
waiting for the whole clip.

### The command line

```sh
gazefix interview.mp4 -o interview-fixed.mp4
gazefix piece.mov -o piece-fixed.mp4 --strength 0.8 --lens 0.5 0.05 --json
```

### As a library

```python
from gazefix import CorrectionSettings, correct_video

report = correct_video(
    "interview.mp4", "interview-fixed.mp4",
    CorrectionSettings(strength=0.8, lens_position=(0.5, 0.05)),
)
print(report.stats)      # offsets found, how much was corrected
print(report.warnings)   # anything it could not do, in plain language
```

## The one setting that matters most

**Where was the camera?** Everything depends on it. GazeFix assumes the lens was
at the centre of the frame, which is correct for footage straight out of a
camera and wrong for anything cropped or reframed — a vertical cut of a wider
shot, say, or a zoomed-in edit. Aim the eyes at the centre of a reframed shot
and you aim them at a point the lens never occupied.

Nothing in the picture reveals the true lens position, so it is a setting rather
than something inferred. In the web app, drag the marker on the camera pad;
values outside the frame are allowed, because for a vertical crop the camera
usually was outside it. On the command line it is `--lens X Y` in fractions of
the frame.

If a run reports that it corrected nothing, this is almost always why, and the
warning says so.

## How it works

1. **Detect.** MediaPipe's Face Landmarker gives 478 points per face, including
   iris rings, plus a head pose matrix.
2. **Measure.** Model the eye as a sphere whose centre of rotation sits behind
   the eyelid plane. The iris's offset from that centre, corrected for
   foreshortening from head turn, gives the current gaze direction. The
   projected iris size is the ruler that converts pixels to millimetres.
3. **Aim.** The direction from that eye to the lens, expressed in the head's own
   frame, is where the eye should be pointing. Solved per eye, so the two eyes
   converge slightly, as real eyes do.
4. **Gate.** Fade the correction out for deliberate look-aways, for heads turned
   too far for a flat warp to sell, and during blinks. Smooth what survives with
   a one-euro filter so slow drift is steadied without lagging a real saccade.
5. **Warp.** Slide the visible eyeball inside the eye opening, with the lids
   riding partway along and the eye's corners pinned. A fold guard scales the
   field back if the map would ever become non-injective.

### Calibrating to the subject

The model has one free anatomical parameter: where the eyeball's centre of
rotation projects between the two corners of the eye. It is not the midpoint —
the eye opening reaches further towards the temple than the nose — and it varies
between people.

GazeFix fits it per subject with no ground truth and no cooperation, by
exploiting a constraint the geometry has to satisfy anyway: **a real pair of
eyes converges on one point, so the two eyes must report the same gaze
direction.** Both estimates are linear in the parameter, so the value that
reconciles them falls straight out of a one-dimensional least squares over a
sample of frames.

On the test portrait this puts the two eyes' disagreement at 1.4°, down from 16°
at the naive midpoint, and it recovers the same value across different faces —
which is also the evidence that the geometry is right, since the two eyes are
solved independently from different landmarks. `tests/test_calibrate.py` checks
it by constructing eyes from a known parameter and confirming the fit recovers
it.

## What it cannot do

Because GazeFix rearranges the pixels that are already in the frame rather than
redrawing the eye, the size of correction it can make is bounded by how much of
the eyeball is visible between the lids — in practice around **10–13° of
requested correction**, with the perceived change a fraction of that.

That covers the everyday case, which is someone reading from a screen just below
or beside the lens. It does not cover a profile view, a glance right off the
edge of frame, or turning a phone shot filmed from the lap into eye contact.
Those need a model that *redraws* the eye region, which is the approach
production systems take, at the cost of a trained generative model.

`docs/limits.md` has the measured response curve and how to reproduce it:

```sh
python tools/fetch_fixtures.py
python tools/measure_fidelity.py
```

Every run reports `budget_limited_fraction` — how often the clip asked for more
than the geometry could pay for. A high number means the camera was far off the
subject's eyeline, and no amount of tuning will fix that.

## Performance

Roughly **26 ms per frame** at 640×800 on a CPU: 17 ms for detection and 9 ms
for the gaze solve and warp. Encoding usually dominates — VP9 through OpenCV is
around 0.5 s per frame, which is why installing ffmpeg is worth it. Correction
runs a calibration pass over a sample of frames first, then a full pass.

## Tests

```sh
pytest                                   # 109 tests
pytest -m "not model"                    # skip anything needing the model
python tools/fetch_fixtures.py && pytest # include the end-to-end tests
```

The geometry, warping, filtering and calibration tests are plain numpy and run
in under a second. The model-backed tests skip themselves if the landmarker or
the portrait fixture is missing, so a fresh checkout with no network still runs
most of the suite.

Neither the model nor the test portrait is committed — the first is 3.6 MB of
weights, the second is a photograph of a person. `tools/fetch_fixtures.py`
retrieves both from Google's public MediaPipe buckets.

## Configuration

| Environment variable | Purpose |
|---|---|
| `GAZEFIX_MODEL_DIR` | Where to cache the landmarker model |
| `GAZEFIX_WORKSPACE` | Where the service keeps uploads and results |
| `GAZEFIX_HOST` / `GAZEFIX_PORT` | Service bind address |
| `GAZEFIX_MAX_UPLOAD_MB` | Upload ceiling, default 512 |

## A note on use

Gaze correction changes what a person appears to have been doing while they were
filmed. That is unremarkable for a webinar or a conference talk, and it is not
unremarkable for footage that is meant to be a record — an interview, testimony,
anything evidentiary. This repository is aimed squarely at the first kind of
video. If you are working with the second kind, the honest option is to leave
the eyes alone.
