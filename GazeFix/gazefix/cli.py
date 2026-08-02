"""Command line entry point: ``gazefix input.mp4 -o output.mp4``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import CorrectionSettings
from .pipeline import correct_video
from .video import VideoError, ffmpeg_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gazefix",
        description="Redirect a speaker's gaze towards the camera in a video.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="video to correct")
    parser.add_argument("-o", "--output", type=Path, required=True, help="where to write it")
    parser.add_argument("--strength", type=float, default=1.0,
                        help="how much of the correction to apply, 0 to 1")
    parser.add_argument("--max-correction", type=float, default=16.0, metavar="DEG",
                        help="leave gaze further off the lens than this alone")
    parser.add_argument("--falloff-start", type=float, default=11.0, metavar="DEG",
                        help="start fading the correction out at this offset")
    parser.add_argument("--fov", type=float, default=60.0, metavar="DEG",
                        help="horizontal field of view of the taking lens")
    parser.add_argument("--lens", type=float, nargs=2, default=(0.5, 0.5), metavar=("X", "Y"),
                        help="where the lens sits, as fractions of the frame; "
                             "the centre is right for uncropped footage")
    parser.add_argument("--faces", type=int, default=1, metavar="N",
                        help="maximum number of faces to correct")
    parser.add_argument("--no-calibrate", action="store_true",
                        help="skip per-subject calibration and use population anatomy")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress the progress bar")
    return parser


def _progress_printer(stream=sys.stderr):
    """A redrawing bar on a terminal, sparse lines when piped to a file."""
    state = {"stage": "", "shown": -1}
    interactive = hasattr(stream, "isatty") and stream.isatty()
    step = 1 if interactive else 25

    def report(fraction: float, stage: str) -> None:
        percent = int(fraction * 100)
        if stage == state["stage"] and percent < state["shown"] + step:
            return
        state["stage"], state["shown"] = stage, percent
        if interactive:
            filled = int(fraction * 30)
            bar = "#" * filled + "-" * (30 - filled)
            print(f"\r{stage:<12} [{bar}] {percent:3d}%", end="", file=stream, flush=True)
        else:
            print(f"{stage}: {percent}%", file=stream, flush=True)

    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    if not args.input.exists():
        print(f"gazefix: no such file: {args.input}", file=sys.stderr)
        return 2

    try:
        settings = CorrectionSettings(
            strength=args.strength,
            max_correction_deg=args.max_correction,
            falloff_start_deg=args.falloff_start,
            fov_deg=args.fov,
            lens_position=tuple(args.lens),
            max_faces=args.faces,
            auto_calibrate=not args.no_calibrate,
        )
    except ValueError as exc:
        print(f"gazefix: {exc}", file=sys.stderr)
        return 2

    progress = None if args.quiet else _progress_printer()
    try:
        report = correct_video(args.input, args.output, settings, progress)
    except VideoError as exc:
        print(f"\ngazefix: {exc}", file=sys.stderr)
        return 1
    if progress and sys.stderr.isatty():
        print(file=sys.stderr)

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
        return 0

    stats = report.stats
    print(f"wrote {report.output_path} ({report.codec}, {report.elapsed_s}s)")
    print(f"  face found in {stats['frames_with_face']}/{stats['frames']} frames, "
          f"corrected {stats['frames_corrected']}")
    print(f"  gaze was {stats['mean_offset_deg']} deg off the lens on average "
          f"(peak {stats['peak_offset_deg']}), moved the eyes "
          f"{stats['mean_iris_shift_px']} px on average")
    if report.calibration["converged"]:
        print(f"  calibrated this subject's eye anatomy from "
              f"{report.calibration['samples']} frames")
    if not ffmpeg_path():
        print("  install ffmpeg for H.264 output, audio, and faster encoding")
    for warning in report.warnings:
        print(f"  ! {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
