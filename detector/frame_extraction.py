"""Frame sourcing: from a video (via ffmpeg) or a folder of images.

Each yielded frame carries a `timestamp_offset_sec` (seconds from the start
of the recording) so detections can later be joined to a GPS track.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import List

import cv2

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass
class Frame:
    path: str
    name: str
    timestamp_offset_sec: float


def _is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


def extract_from_video(video_path: str, fps: float, out_dir: str) -> List[Frame]:
    """Extract frames at `fps` using ffmpeg. Returns ordered Frame list."""
    os.makedirs(out_dir, exist_ok=True)
    pattern = os.path.join(out_dir, "frame_%05d.jpg")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",
        pattern,
    ]
    subprocess.run(cmd, check=True)

    frames: List[Frame] = []
    files = sorted(f for f in os.listdir(out_dir) if f.lower().endswith(".jpg"))
    for idx, fname in enumerate(files):
        # ffmpeg fps=N emits one frame every 1/N seconds, starting near t=0.
        ts = idx / fps
        frames.append(Frame(path=os.path.join(out_dir, fname), name=fname, timestamp_offset_sec=round(ts, 3)))
    return frames


def load_from_folder(folder: str) -> List[Frame]:
    """Load images from a folder, ordered by filename, 1s apart by convention."""
    files = sorted(
        f for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    )
    frames: List[Frame] = []
    for idx, fname in enumerate(files):
        frames.append(
            Frame(path=os.path.join(folder, fname), name=fname, timestamp_offset_sec=float(idx))
        )
    return frames


def get_frames(input_path: str, fps: float, tmp_dir: str | None = None) -> List[Frame]:
    if os.path.isdir(input_path):
        return load_from_folder(input_path)
    if _is_video(input_path):
        out_dir = tmp_dir or tempfile.mkdtemp(prefix="frames_")
        return extract_from_video(input_path, fps, out_dir)
    raise ValueError(f"Unsupported input: {input_path} (expected a video file or image folder)")


def laplacian_variance(image_path: str) -> float | None:
    """Return Laplacian variance (sharpness proxy). None if image unreadable."""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


def is_too_blurry(image_path: str, threshold: float) -> bool:
    """Laplacian-variance blur check. Low variance => blurry => skip."""
    v = laplacian_variance(image_path)
    return v is None or v < threshold
