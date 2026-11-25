"""What the user changed by hand between the built montage ("02 - MONTAGE") and "03 - FINAL", from facts: Step 9
starts from this report and only asks the user WHY.

Compares the source frames of every rush used by the montage plan with those of the dumped FINAL
(resolve/dump_timeline.py), separately before and after the title card (main part / bloopers):
  removed    source frames of the montage no longer in the FINAL (a whole piece, or a piece shortened / split)
  added      source frames in the FINAL that the montage did not use (a piece lengthened, a passage brought back)
  moved      sequences whose order changed (located like chapters.py, by their first source frame)
  on_v2      shots the user put on video track 2 or above (overlays, J-cuts)
  other      items that are not rushes of the montage (titles, generators, other clips)
Frames are counted from the start of each rush, in timeline frames, like the plans.

Usage: python final_changes.py MONTAGE_PLAN.json FINAL_DUMP.json OUT_PREFIX [--clips CLIPS.json] [--min-frames 2]
Output: OUT_PREFIX.json and OUT_PREFIX.md (e.g. history/09_final_changes); the summary is printed.
"""
import argparse
import os

from common import Clips, load_json, save_json, tc


def merge(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def subtract(xs, ys):
    """Intervals of xs not covered by ys (both merged, half-open)."""
    out = []
    for a, b in xs:
        cur = a
        for c, d in ys:
            if d <= cur or c >= b:
                continue
            if c > cur:
                out.append([cur, c])
            cur = max(cur, d)
        if cur < b:
            out.append([cur, b])
    return out


def by_clip(pieces):
    res = {}
    for clip, a, b in pieces:
        res.setdefault(clip, []).append([a, b])
    return {c: merge(v) for c, v in res.items()}


def longest_increasing(seq):
    """Indexes of one longest increasing subsequence (the sequences that did NOT move)."""
    best, prev = [], [None] * len(seq)
    tails = []
    for i, x in enumerate(seq):
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if seq[tails[mid]] < x:
                lo = mid + 1
            else:
                hi = mid
        prev[i] = tails[lo - 1] if lo else None
        if lo == len(tails):
            tails.append(i)
        else:
            tails[lo] = i
    k = tails[-1] if tails else None
    while k is not None:
        best.append(k)
        k = prev[k]
    return set(best)


def compare(plan, final, min_frames=2):
    fps = plan.get("fps") or final.get("fps") or 25
    used = {p[0] for p in plan["pieces"] + plan.get("tail_pieces", [])}
    titles = [it[3] for it in final["items"] if it[1] == "Text+"]
    cut = min(titles) if titles else final["frames"]
    clips_items = [it for it in final["items"] if it[2] == "video" and it[1] in used]
    other = [it for it in final["items"] if it[2] == "video" and it[1] not in used and it[1] != "Text+"]

    # where each montage piece sits in the montage timeline (main part from 0)
    pos, where = 0, []
    for clip, a, b in plan["pieces"]:
        where.append((clip, a, b, pos))
        pos += b - a

    def at_montage(clip, a):
        for c, x, y, p in where:
            if c == clip and x <= a < y:
                return p + a - x
        return None

    def at_final(clip, a, items):
        for it in items:
            if it[1] == clip and it[5] <= a < it[5] + it[4] - it[3]:
                return it[3] + a - it[5]
        return None

    def part(m_pieces, f_items, montage_side):
        m = by_clip(m_pieces)
        f = by_clip([[it[1], it[5], it[5] + it[4] - it[3]] for it in f_items])
        whole = {(c, a, b) for c, a, b in m_pieces}
        removed, added = [], []
        for clip in sorted(set(m) | set(f)):
            for a, b in subtract(m.get(clip, []), f.get(clip, [])):
                if b - a >= min_frames:
                    removed.append({"clip": clip, "src": [a, b], "frames": b - a, "seconds": round((b - a) / fps, 2),
                                    "whole_piece": (clip, a, b) in whole,
                                    "montage_at": at_montage(clip, a) if montage_side else None})
            for a, b in subtract(f.get(clip, []), m.get(clip, [])):
                if b - a >= min_frames:
                    added.append({"clip": clip, "src": [a, b], "frames": b - a, "seconds": round((b - a) / fps, 2),
                                  "final_at": at_final(clip, a, f_items)})
        total_m = sum(b - a for v in m.values() for a, b in v)
        total_f = sum(b - a for v in f.values() for a, b in v)
        return {"montage_frames": total_m, "final_frames": total_f, "removed": removed, "added": added}

    main_items = [it for it in clips_items if it[3] < cut]
    tail_items = [it for it in clips_items if it[3] >= cut]
    res = {"fps": fps, "main": part(plan["pieces"], main_items, True),
           "bloopers": part(plan.get("tail_pieces", []), tail_items, False)}

    # sequence order (like chapters.py: by the first source frame, or a later piece of that shot if trimmed)
    found = []
    for k, seq in enumerate(plan.get("sequences", [])):
        clip, src_in, src_out = seq["first"]
        hit = [it[3] + src_in - it[5] for it in main_items if it[1] == clip and it[5] <= src_in < it[5] + it[4] - it[3]]
        if not hit:
            hit = [it[3] for it in main_items if it[1] == clip and src_in < it[5] < src_out]
        if hit:
            found.append((min(hit), k, seq["title"]))
        else:
            res.setdefault("sequences_gone", []).append(seq["title"])
    found.sort()
    stay = longest_increasing([k for _, k, _ in found])
    res["moved"] = [{"title": t, "montage_rank": k + 1, "final_rank": i + 1, "final_at": f}
                    for i, (f, k, t) in enumerate(found) if i not in stay]
    res["on_v2"] = [{"clip": it[1], "track": it[0], "src": [it[5], it[5] + it[4] - it[3]], "final_at": it[3],
                     "seconds": round((it[4] - it[3]) / fps, 2)} for it in clips_items if it[0] > 1]
    res["other"] = [{"name": it[1], "track": it[0], "final_at": it[3], "seconds": round((it[4] - it[3]) / fps, 2)}
                    for it in other]
    res["title_card"] = bool(titles)
    return res


def summary(res, clips=None):
    fps = res["fps"]
    name = (lambda c: clips.short(c)) if clips else (lambda c: os.path.splitext(c)[0])
    ref = (lambda c, a: f" (ref {tc(clips.start[c] + a, fps, frames=True)})" if clips and c in clips.start else "")
    lines = []
    for key, label in (("main", "Montage"), ("bloopers", "Bloopers")):
        p = res[key]
        if not p["montage_frames"] and not p["final_frames"]:
            continue
        lines.append(f"## {label}: {tc(p['montage_frames'], fps, frames=True)} built -> "
                     f"{tc(p['final_frames'], fps, frames=True)} in FINAL")
        for r in p["removed"]:
            kind = "piece removed" if r["whole_piece"] else "removed"
            at = f" at montage {tc(r['montage_at'], fps, frames=True)}" if r["montage_at"] is not None else ""
            lines.append(f"- {kind}: {name(r['clip'])} {r['seconds']}s{at}{ref(r['clip'], r['src'][0])}")
        for r in p["added"]:
            at = f" at FINAL {tc(r['final_at'], fps, frames=True)}" if r["final_at"] is not None else ""
            lines.append(f"- added: {name(r['clip'])} {r['seconds']}s{at}{ref(r['clip'], r['src'][0])}")
        if not p["removed"] and not p["added"]:
            lines.append("- no change")
    if res["moved"]:
        lines.append("## Sequences moved")
        lines += [f"- {m['title']}: {m['montage_rank']} -> {m['final_rank']} (FINAL {tc(m['final_at'], fps, frames=True)})"
                  for m in res["moved"]]
    if res.get("sequences_gone"):
        lines.append("## Sequences gone: " + ", ".join(res["sequences_gone"]))
    if res["on_v2"]:
        lines.append("## Shots on V2 or above")
        lines += [f"- {name(v['clip'])} V{v['track']} {v['seconds']}s at FINAL {tc(v['final_at'], fps, frames=True)}"
                  for v in res["on_v2"]]
    if res["other"]:
        lines.append("## Other items (not rushes of the montage)")
        lines += [f"- {o['name']} V{o['track']} {o['seconds']}s at FINAL {tc(o['final_at'], fps, frames=True)}"
                  for o in res["other"]]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("final")
    ap.add_argument("out")
    ap.add_argument("--clips", help="clips.json: short names and reference timecodes in the report")
    ap.add_argument("--min-frames", type=int, default=2, help="ignore differences shorter than this")
    args = ap.parse_args()
    res = compare(load_json(args.plan), load_json(args.final), args.min_frames)
    text = summary(res, Clips(args.clips, settings={}) if args.clips else None)
    save_json(args.out + ".json", res)
    with open(args.out + ".md", "w", encoding="utf-8") as f:
        f.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
