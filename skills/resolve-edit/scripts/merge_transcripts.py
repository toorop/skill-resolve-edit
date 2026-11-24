"""Merge transcript parts into one JSON whose times are reference-timeline seconds.

Usage:
  python merge_transcripts.py OUT.json --manifest MANIFEST.json     (parts = <part file>.json next to each wav)
  python merge_transcripts.py OUT.json PART1.json:OFFSET [PART2.json:OFFSET ...]
"""
import json
import os
import sys

from common import load_json, save_json


def merge(parts, out_path, source="elevenlabs scribe-v2 via fal.ai"):
    """parts = [(json_path, offset_seconds), ...]"""
    merged = {"source": source, "language_code": None, "parts": [], "words": []}
    for path, offset in parts:
        part = load_json(path)
        merged["language_code"] = merged["language_code"] or part.get("language_code")
        merged["parts"].append({"file": path, "offset": offset, "n_tokens": len(part["words"])})
        for w in part["words"]:
            w = dict(w)
            w["start"] = round(w["start"] + offset, 3)
            w["end"] = round(w["end"] + offset, 3)
            merged["words"].append(w)
    starts = [w["start"] for w in merged["words"]]
    if starts != sorted(starts):
        raise SystemExit("tokens are not in chronological order after merge (wrong offsets?)")
    merged["text"] = "".join(w["text"] for w in merged["words"])
    save_json(out_path, merged)
    print(f"{out_path}: {len(merged['words'])} tokens, {starts[0]:.2f}s -> {merged['words'][-1]['end']:.2f}s")
    return merged


def main():
    out = sys.argv[1]
    if sys.argv[2] == "--manifest":
        manifest = load_json(sys.argv[3])
        parts = [(os.path.splitext(m["file"])[0] + ".json", m["offset"]) for m in manifest]
    else:
        parts = [(a.rsplit(":", 1)[0], float(a.rsplit(":", 1)[1])) for a in sys.argv[2:]]
    merge(parts, out)


if __name__ == "__main__":
    main()
