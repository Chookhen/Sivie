"""CLI entrypoint for the road-hazard-detector.

Examples:
  python main.py --input ./samples --mock
  python main.py --input drive.mov --fps 1 --output detections.json
"""

from __future__ import annotations

import json

import click
from dotenv import load_dotenv

from detector.dedupe import dedupe as _dedupe
from detector.gps_sync import apply_gps, auto_time_offset, generate_mock_track, load_track
from detector.osm_context import enrich
from detector.pipeline import run_pipeline
from detector import cache as _cache

load_dotenv()


@click.command()
@click.option("--input", "input_path", default=None,
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
@click.option("--gpx", "gpx_path", default=None,
              help="GPS track file (.gpx or .csv).")
@click.option("--time-offset", default=0.0, show_default=True, type=float,
              help="Seconds to shift video time to align with GPS clock (added on top of auto-sync).")
@click.option("--no-auto-sync", "no_auto_sync", is_flag=True, default=False,
              help="Disable automatic video<->GPX time alignment (use raw --time-offset only).")
@click.option("--mock-gps", "mock_gps", is_flag=True, default=False,
              help="Lay a synthetic Berkeley route under REAL detections (for the map demo when no .gpx exists).")
@click.option("--save-frames-dir", "save_frames_dir", default=None,
              help="Copy analyzed frames here; adds image_url to each detection.")
@click.option("--request-delay", "request_delay_sec", default=0.0, show_default=True, type=float,
              help="Seconds to wait between API calls (use ~7 to avoid rate limiting).")
@click.option("--min-confidence", "min_confidence", default=0.0, show_default=True, type=float,
              help="Drop detections below this confidence (e.g. 0.65 to cut false positives).")
@click.option("--detector", type=click.Choice(["yolo", "gemini"]), default="yolo", show_default=True,
              help="Detection backend: local YOLO road-damage model or the Gemini VLM.")
@click.option("--yolo-conf", "yolo_conf", default=0.25, show_default=True, type=float,
              help="YOLO confidence threshold (lower = more detections).")
@click.option("--dedupe", "do_dedupe", is_flag=True, default=False,
              help="Collapse duplicate detections of the same physical hazard (best-frame wins).")
@click.option("--enrich", "enrich_osm", is_flag=True, default=False,
              help="Enrich detections with OSM road name, road class, and nearby POIs.")
@click.option("--street", "aggregate_street", is_flag=True, default=False,
              help="Merge into the persistent hazard DB; add per-street counts & weight.")
@click.option("--street-db", "street_db", default="hazard_db.json", show_default=True,
              help="Path to the persistent hazard database JSON.")
@click.option("--ai-priority", "ai_priority", is_flag=True, default=False,
              help="Use Gemini (2.5 Pro) to score urgency + concise reasons per hazard.")
@click.option("--ai-model", "ai_model", default=None,
              help="Override the Gemini priority model (default: gemini-2.5-pro).")
@click.option("--ai-mock", "ai_mock", is_flag=True, default=False,
              help="Use a mock urgency evaluator (no API key needed) to test the wiring.")
@click.option("--ai-max", "ai_max", default=None, type=int,
              help="Cap how many detections get a Gemini call (cost/testing control).")
@click.option("--no-cache", "no_cache", is_flag=True, default=False,
              help="Bypass the OSM lookup cache (always fetch fresh).")
@click.option("--clear-cache", "clear_cache", is_flag=True, default=False,
              help="Delete the OSM cache file and exit.")
def main(input_path, fps, output, max_frames, blur_threshold, mock, skip_blur_check, gpx_path, time_offset, no_auto_sync, mock_gps, save_frames_dir, request_delay_sec, min_confidence, detector, yolo_conf, do_dedupe, enrich_osm, aggregate_street, street_db, ai_priority, ai_model, ai_mock, ai_max, no_cache, clear_cache):
    if clear_cache:
        _cache.clear_cache()
        return

    if not input_path:
        raise click.UsageError("Missing option '--input'.")

    report = run_pipeline(
        input_path=input_path,
        fps=fps,
        blur_threshold=blur_threshold,
        max_frames=max_frames,
        mock=mock,
        skip_blur_check=skip_blur_check,
        save_frames_dir=save_frames_dir,
        request_delay_sec=request_delay_sec,
        min_confidence=min_confidence,
        detector=detector,
        yolo_conf=yolo_conf,
    )

    report_dict = report.model_dump(mode="json")
    if save_frames_dir:
        for det in report_dict["detections"]:
            det["image_url"] = f"/frames/{det['frame']}"
    if gpx_path:
        offset = time_offset
        if not no_auto_sync:
            auto = auto_time_offset(input_path, gpx_path)
            if auto is not None:
                print(f"[gps] auto time-sync: video<->track offset = {auto:.1f}s (+ {time_offset:.1f}s manual)")
                offset += auto
            else:
                print("[gps] auto time-sync unavailable (no video/track timestamps); using --time-offset only")
        apply_gps(report_dict, load_track(gpx_path), offset)
        report_dict["gps_source"] = "gpx"
    elif mock or mock_gps:
        dets = report_dict.get("detections", [])
        max_t = max((d["timestamp_offset_sec"] for d in dets), default=120.0)
        apply_gps(report_dict, generate_mock_track(duration_sec=max_t + 5), time_offset)
        report_dict["gps_source"] = "synthetic"
    else:
        report_dict["gps_source"] = "none"

    if do_dedupe:
        _dedupe(report_dict, use_gps=bool(gpx_path or mock or mock_gps), frames_dir=save_frames_dir)

    if enrich_osm:
        enrich(report_dict, use_cache=not no_cache)

    if aggregate_street or ai_priority:
        from detector.street_registry import update_and_aggregate
        update_and_aggregate(report_dict, db_path=street_db)

    if ai_priority:
        from detector.gemini_priority import evaluate_report
        # Write a baseline snapshot first so the output is usable immediately;
        # the evaluator then checkpoints incrementally as Gemini results land.
        with open(output, "w", encoding="utf-8") as fh:
            json.dump(report_dict, fh, indent=2)
        evaluate_report(
            report_dict,
            frames_dir=save_frames_dir,
            mock=ai_mock,
            model=ai_model,
            max_items=ai_max,
            save_path=output,
        )

    with open(output, "w", encoding="utf-8") as fh:
        json.dump(report_dict, fh, indent=2)

    written = report_dict["detections"]
    print(f"\nWrote {len(written)} detection(s) -> {output}")
    top = written[:5]
    if top:
        print("\nTop priorities:")
        for d in top:
            score = d.get("final_priority") if d.get("final_priority") is not None else d["priority"]
            reasons = d.get("justification") or []
            why = f" | {reasons[0]}" if reasons else ""
            print(f"  [{d['priority_label']:>8}] {score:>5} | {d['type']:<14} | {d['frame']}{why}")


if __name__ == "__main__":
    main()
