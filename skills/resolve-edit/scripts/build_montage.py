"""Re-ordered edit ("montage") from the clean linear material + the sequence plan of DECISIONS.json.

Each sequence = list of reference ranges; only the clean material (linear rules applied) inside them is used.
Optional bloopers (raw ranges) after a title card. Markers: Purple = sequence start (also the YouTube chapters),
Red/Blue/Green = review markers inside sequences, Pink = title and bloopers.

Usage: python build_montage.py DECISIONS.json TRANSCRIPT.json CLIPS.json OUT_PLAN.json [--fps N] [--profile DIR]
(--fps only for an old clips.json without its rate; default 25)
"""
import argparse

from common import (Clips, add_profile_arg, fps_arg, ascii_only, is_spoken, load_json, load_settings, load_words, parse_time,
                    save_json, tc)
from edl_lib import compute_linear, review_markers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("decisions")
    ap.add_argument("transcript")
    ap.add_argument("clips")
    ap.add_argument("out")
    fps_arg(ap)
    add_profile_arg(ap)
    args = ap.parse_args()

    dec = load_json(args.decisions)
    words = load_words(args.transcript)
    settings = load_settings(args.profile)
    clips = Clips(args.clips, args.fps, settings)
    fps = clips.fps
    clean, cuts, demos, report = compute_linear(dec, words, clips, settings)
    mcfg = dec["montage"]

    pieces, markers, sequences, pos = [], [], [], 0
    for seq in mcfg["sequences"]:
        placed = []
        for k, (ra, rb) in enumerate(seq["ranges"]):
            fa, fb = round(parse_time(ra, fps) * fps), round(parse_time(rb, fps) * fps)
            placed_r = []
            for la, lb in clean:
                a, b = max(la, fa), min(lb, fb)
                if b > a:
                    placed_r.append((a, b, pos))
                    pieces.extend(clips.split(a, b))
                    pos += b - a
            if placed_r and k > 0:  # material moved from elsewhere in the shoot, joined inside this sequence
                markers.append([placed_r[0][2], "Cyan", "Raccord deplace",
                                ascii_only(f"Suite de '{seq['title']}' tournee ailleurs ({tc(fa, fps, frames=True)} ref)")])
            markers += review_markers(placed_r, cuts, demos, fps)
            placed += placed_r
        if not placed:
            print(f"WARNING: sequence '{seq['title']}' is empty")
            continue
        first = clips.split(placed[0][0], placed[0][1])[0]
        sequences.append({"title": seq["title"], "frame": placed[0][2], "first": first})
        markers.append([placed[0][2], "Purple", ascii_only(seq["title"]), "Debut de sequence"])

    plan = {"kind": "montage", "fps": fps, "pieces": pieces, "markers": sorted(markers), "sequences": sequences,
            "main_frames": pos, "title": None, "tail_pieces": [], "tail_markers": []}

    bl = mcfg.get("bloopers") or []
    if bl:
        plan["title"] = {"text": mcfg.get("blooper_title") or settings.get("montage", {}).get("blooper_title", "Bloopers")}
        tpos = 0
        for b in bl:
            end = parse_time(b["end"], fps)
            if b.get("start") in (None, "before_first_word"):
                rush = clips.at(end - 1 / fps)
                rs = clips.start[rush] / fps
                start = min(w["start"] for w in words if rs <= w["start"] < end and is_spoken(w)) - 0.3
            else:
                start = parse_time(b["start"], fps)
            a, z = round(start * fps), round(end * fps)
            plan["tail_markers"].append([tpos, "Pink", ascii_only(b["label"]), "Betisier"])
            for p in clips.split(a, z):
                plan["tail_pieces"].append(p)
            tpos += z - a
        plan["tail_frames"] = tpos

    save_json(args.out, plan)
    print(f"{len(pieces)} main pieces, main part {tc(pos, fps, frames=True)}, {len(sequences)} sequences, "
          f"{len(markers)} markers" + (f", bloopers {len(plan['tail_pieces'])} pieces "
                                      f"{tc(plan['tail_frames'], fps, frames=True)}" if bl else ""))
    for s in sequences:
        print(f"  {tc(s['frame'], fps, frames=True)}  {s['title']}")


if __name__ == "__main__":
    main()
