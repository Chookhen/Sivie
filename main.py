"""CLI entrypoint for the road-hazard-detector.

Examples:
  python main.py --input ./samples --mock
  python main.py --input drive.mov --fps 1 --output detections.json
"""

from __future__ import annotations

import json

import click
from dotenv import load_dotenv

from detector.pipeline import run_pipeline

load_dotenv()


@click.command()
@click.option("--input", "input_path", required=True,
              help="Path to a video file OR a folder of images.")
@click.option("--fps", default=1.0, show_default=True, type=float,
              help="Frames per second to extract (video input only).")
@click.option("--output", default="detections.json", show_default=True,
              help="Where to write the detections JSON.")
@click.option("--max-frames", default=None, type=int,
              help="Cap number of frames (for testing / cost control).")
@click.option("--blur-threshold", default=100.0, show_default=True, type=float,
              help="Laplacian-variance threshold; frames below are skipped.")
@click.option("--mock", is_flag=True, default=False,
              help="Run with fake detections (no API key / footage needed).")
@click.option("--skip-blur-check", is_flag=True, default=False,
              help="Disable the blur filter.")
def main(input_path, fps, output, max_frames, blur_threshold, mock, skip_blur_check):
    report = run_pipeline(
        input_path=input_path,
        fps=fps,
        blur_threshold=blur_threshold,
        max_frames=max_frames,
        mock=mock,
        skip_blur_check=skip_blur_check,
    )

    with open(output, "w", encoding="utf-8") as fh:
        json.dump(report.model_dump(mode="json"), fh, indent=2)

    print(f"\nWrote {len(report.detections)} detection(s) -> {output}")
    top = report.detections[:5]
    if top:
        print("\nTop priorities:")
        for d in top:
            print(f"  [{d.priority_label.value:>8}] {d.priority:>5} | {d.type.value:<14} | {d.frame} | {d.description}")


if __name__ == "__main__":
    main()
