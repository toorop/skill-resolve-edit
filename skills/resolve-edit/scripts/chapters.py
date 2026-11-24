"""YouTube chapters from the FINAL timeline (after the user's manual tweaks).

Each sequence of the montage plan is located in the dumped FINAL timeline by its first source frame
(rush + source in-point), so trims/moves made by hand are taken into account. Sequences no longer present are
skipped. YouTube rules: first chapter at 00:00, at least 3 chapters, each at least 10 s.

Usage: python chapters.py MONTAGE_PLAN.json FINAL_DUMP.json [--min-len 10]
Prints "MM:SS - <internal title>" lines; Claude then rewrites the titles in the channel's style.
"""
import argparse

from common import load_json


def fmt(seconds):
    s = int(seconds)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("final")
    ap.add_argument("--min-len", type=float, default=10.0)
    args = ap.parse_args()

    plan, final = load_json(args.plan), load_json(args.final)
    fps = plan.get("fps", 25)
    # every video track (the user may move shots to V2 as overlays), but nothing after the title card (bloopers)
    titles = [it[3] for it in final["items"] if it[1] == "Text+"]
    end = min(titles) if titles else final["frames"]
    vids = [it for it in final["items"] if it[2] == "video" and it[1] != "Text+" and it[3] < end]
    found, missing = [], []
    for seq in plan["sequences"]:
        clip, src_in, src_out = seq["first"]
        hit = sorted((it for it in vids if it[1] == clip and it[5] <= src_in < it[5] + (it[4] - it[3])),
                     key=lambda it: it[3])
        if hit:
            frame = hit[0][3] + src_in - hit[0][5]
        else:  # head trimmed by hand: a later piece of the same first shot
            later = sorted((it for it in vids if it[1] == clip and src_in < it[5] < src_out), key=lambda it: it[3])
            if not later:
                missing.append(seq["title"])
                continue
            frame = later[0][3]
        found.append((frame / fps, seq["title"]))
    found.sort()
    chapters = []
    for t, title in found:
        if chapters and t - chapters[-1][0] < args.min_len:
            continue
        chapters.append((t, title))
    if chapters:
        chapters[0] = (0.0, chapters[0][1])
    if titles and plan.get("title"):  # bloopers chapter at the title card
        chapters.append((min(titles) / fps, plan["title"]["text"]))
    for t, title in chapters:
        print(f"{fmt(t)} - {title}")
    if missing:
        print(f"\n# not found in FINAL (removed?): {missing}")
    if len(chapters) < 3:
        print("\n# WARNING: YouTube needs at least 3 chapters")


if __name__ == "__main__":
    main()
