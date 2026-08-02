"""Video decode and encode.

Encoding takes whichever of two paths is available. With ffmpeg on the system,
frames are piped to it and encoded once as H.264, with the original's audio
copied across. Without it, OpenCV writes VP9/WebM, which every current browser
plays but which carries no audio -- OpenCV's writers are video only.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

log = logging.getLogger(__name__)

#: Tried in order when ffmpeg is unavailable. VP9 in WebM plays in browsers;
#: MPEG-4 Part 2 in MP4 is the last resort and generally needs a real player.
FALLBACK_CODECS: tuple[tuple[str, str], ...] = (("vp09", ".webm"), ("mp4v", ".mp4"))


class VideoError(RuntimeError):
    """Raised when a clip cannot be read or written."""


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    frame_count: int

    @property
    def duration_s(self) -> float:
        return self.frame_count / self.fps if self.fps > 0 else 0.0


@dataclass(frozen=True)
class EncodeResult:
    path: Path
    codec: str
    audio_copied: bool


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def probe(path: str | Path) -> VideoInfo:
    """Read a clip's dimensions, rate and length."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise VideoError(f"cannot open video: {path}")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        info = VideoInfo(
            width=int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            # Containers routinely report nonsense here; 30 is a safer guess
            # than dividing by zero downstream.
            fps=fps if 1.0 <= fps <= 480.0 else 30.0,
            frame_count=max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 0),
        )
    finally:
        capture.release()
    if info.width <= 0 or info.height <= 0:
        raise VideoError(f"video reports an empty frame size: {path}")
    return info


def read_frames(path: str | Path, stride: int = 1) -> Iterator[tuple[int, np.ndarray]]:
    """Yield ``(index, frame)`` pairs, optionally keeping only every ``stride``th."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise VideoError(f"cannot open video: {path}")
    try:
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                return
            if index % stride == 0:
                yield index, frame
            index += 1
    finally:
        capture.release()


class _FfmpegSink:
    """Pipes raw frames into ffmpeg, muxing audio from the source clip."""

    def __init__(self, output: Path, info: VideoInfo, source: Path, crf: int):
        command = [
            ffmpeg_path() or "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{info.width}x{info.height}", "-r", f"{info.fps}",
            "-i", "pipe:0",
            "-i", str(source),
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "160k", "-shortest",
            str(output),
        ]
        self._process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )

    def write(self, frame: np.ndarray) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self) -> None:
        assert self._process.stdin is not None
        self._process.stdin.close()
        code = self._process.wait()
        if code != 0:
            detail = (self._process.stderr.read() or b"").decode("utf-8", "replace")[-800:]
            raise VideoError(f"ffmpeg exited with {code}: {detail}")


class _OpenCvSink:
    """Writes frames with OpenCV, negotiating a codec the build actually has."""

    def __init__(self, output: Path, info: VideoInfo):
        self.writer = None
        self.result: EncodeResult | None = None
        for fourcc, suffix in FALLBACK_CODECS:
            target = output.with_suffix(suffix)
            writer = cv2.VideoWriter(
                str(target), cv2.VideoWriter_fourcc(*fourcc), info.fps, (info.width, info.height)
            )
            if writer.isOpened():
                self.writer = writer
                self.result = EncodeResult(target, fourcc, audio_copied=False)
                return
            writer.release()
        raise VideoError("no usable video encoder is available")

    def write(self, frame: np.ndarray) -> None:
        assert self.writer is not None
        self.writer.write(frame)

    def close(self) -> None:
        if self.writer is not None:
            self.writer.release()
            self.writer = None


class FrameSink:
    """Accepts corrected frames and produces an encoded file.

    Prefers ffmpeg, which encodes H.264 in one pass and carries the source's
    audio over. Falls back to OpenCV when ffmpeg is missing or refuses to start,
    in which case the output is silent and may land on a different extension
    than asked for -- read :attr:`result` rather than assuming.
    """

    def __init__(self, output: Path, info: VideoInfo, source: Path, crf: int = 18):
        self._output = Path(output)
        self._info = info
        self._output.parent.mkdir(parents=True, exist_ok=True)
        self._result: EncodeResult | None = None
        self._frames_written = 0

        self._sink: _FfmpegSink | _OpenCvSink
        if ffmpeg_path():
            try:
                self._sink = _FfmpegSink(self._output, info, Path(source), crf)
                self._using_ffmpeg = True
                return
            except OSError as exc:
                log.warning("could not start ffmpeg (%s); falling back to OpenCV", exc)
                self._output.unlink(missing_ok=True)
        self._sink = _OpenCvSink(self._output, info)
        self._using_ffmpeg = False

    @property
    def result(self) -> EncodeResult:
        if self._result is None:
            raise VideoError("sink has not been closed yet")
        return self._result

    def write(self, frame: np.ndarray) -> None:
        self._sink.write(frame)
        self._frames_written += 1

    def close(self) -> None:
        if self._result is not None:
            return
        self._sink.close()
        if self._using_ffmpeg:
            self._result = EncodeResult(self._output, "h264", audio_copied=True)
        else:
            assert isinstance(self._sink, _OpenCvSink) and self._sink.result is not None
            self._result = self._sink.result
        if self._frames_written == 0:
            raise VideoError("no frames were written")

    def __enter__(self) -> "FrameSink":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            # Let the original failure surface rather than a teardown error.
            try:
                self._sink.close()
            except Exception:  # noqa: BLE001
                log.debug("sink teardown failed while handling %s", exc_type.__name__)
            return
        self.close()
