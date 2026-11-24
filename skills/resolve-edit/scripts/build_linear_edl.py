"""Linear cut: chronological order, validated removals + long-gap / rush head-tail rules (see edl_lib).

Usage: python build_linear_edl.py DECISIONS.json TRANSCRIPT.json CLIPS.json OUT_PLAN.json [--fps 25] [--profile DIR]
The plan is read by resolve/build_timeline.py.
"""
import argparse

from common import Clips, add_profile_arg, load_json, load_settings, load_words, save_json, tc
from edl_lib import compute_linear, review_markers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("decisions")
    ap.add_argument("transcript")
    ap.add_argument("clips")
    ap.add_argument("out")
    ap.add_argument("--fps", type=int, default=25)
    add_profile_arg(ap)
    args = ap.parse_args()

    clips = Clips(args.clips, args.fps)
    ref, cuts, demos, report = compute_linear(load_json(args.decisions), load_words(args.transcript), clips,
                                              load_settings(args.profile))
    pieces, placed, pos = [], [], 0
    for a, b in ref:
        for p in clips.split(a, b):
            pieces.append(p)
        placed.append((a, b, pos))
        pos += b - a
    markers = review_markers(placed, cuts, demos, args.fps)
    plan = {"kind": "linear", "fps": args.fps, "pieces": pieces, "markers": sorted(markers),
            "total_frames": pos, "report": report, "cuts": cuts, "demos": demos, "clean_ranges": ref}
    save_json(args.out, plan)
    print(f"{len(pieces)} pieces, {tc(pos, args.fps, frames=True)} kept of {tc(clips.total_frames, args.fps, frames=True)}; "
          f"{len(report['gaps_shortened'])} gaps shortened, {len(report['gaps_kept_as_demo'])} kept as demo, "
          f"{len(report['heads_tails_trimmed'])} heads/tails trimmed, {len(report['isolated_slivers_dropped'])} slivers dropped, "
          f"{len(markers)} markers")


if __name__ == "__main__":
    main()
