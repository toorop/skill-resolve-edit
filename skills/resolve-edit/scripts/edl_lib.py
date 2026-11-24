"""Edit-list logic shared by build_linear_edl.py and build_montage.py.

All times are REFERENCE timeline seconds; pieces are [clip_name, src_in, src_out) in frames (src_out exclusive,
which is exactly what Resolve's AppendToTimeline endFrame expects).
"""
from common import Clips, ascii_only, is_spoken, parse_time, tc

# Generic defaults. Layering: these < channel profile settings.json "linear" < the video's decisions.json "linear".
LINEAR_DEFAULTS = {
    "gap_min": 2.0,        # gaps shorter than this are never touched (breaths, air)
    "keep_air": 0.5,       # kept after the last word and before the next one when a long gap is shortened
    "head_pad": 0.3,       # each raw rush starts this long before the presenter's first word (camera start / framing)
    "tail_pad": 0.5,       # ...and ends this long after the last word
    "min_piece_frames": 3,  # drop slivers shorter than this
    "min_isolated": 1.5,   # a piece shorter than this, cut on both sides (rush change = cut), is a parasite flash -> dropped
    "demo_cues": [],       # words before a long gap that suggest a silent demonstration (language-specific: profile)
    "keep_head": [],       # rush short names whose head is kept as is (e.g. car arrival, sentence continuation)
    "keep_tail": [],
    "remove": [],          # [{"label", "start", "end"}] validated removals (seconds or HH:MM:SS:FF)
}


def compute_linear(decisions, words, clips: Clips, settings=None):
    fps = clips.fps
    cfg = {**LINEAR_DEFAULTS, **(settings or {}).get("linear", {}), **decisions.get("linear", {})}
    remove = [(r["label"], parse_time(r["start"], fps), parse_time(r["end"], fps)) for r in cfg["remove"]]

    def removed(t):
        return any(a <= t <= b for _, a, b in remove)

    cuts = list(remove)
    demos, shortened = [], []
    for i in range(len(words) - 1):
        a, b = words[i], words[i + 1]
        gap = b["start"] - a["end"]
        if gap < cfg["gap_min"] or clips.at(a["end"]) != clips.at(b["start"]) or removed(a["end"]) or removed(b["start"]):
            continue
        ctx = " ".join(w["text"] for w in words[max(0, i - 5):i + 1]).lower()[-40:]
        if any(c in ctx for c in cfg["demo_cues"]):
            demos.append({"at": a["end"], "until": b["start"], "gap": round(gap, 1), "context": ctx[-30:]})
            continue
        cuts.append((f"blanc {gap:.1f}s", a["end"] + cfg["keep_air"], b["start"] - cfg["keep_air"]))
        shortened.append({"at": a["end"], "gap": round(gap, 1)})

    trimmed = []
    for name, s, e in clips.items:
        inside = [w for w in words if s <= w["start"] * fps < e and not removed(w["start"]) and is_spoken(w)]
        if not inside:
            continue
        sh = clips.short(name)
        if sh not in cfg["keep_head"]:
            head_end = inside[0]["start"] - cfg["head_pad"]
            if head_end > s / fps:
                cuts.append((f"debut de rush {sh}", s / fps, head_end))
                trimmed.append(f"head {sh} {head_end - s / fps:.2f}s")
        if sh not in cfg["keep_tail"]:
            tail_start = inside[-1]["end"] + cfg["tail_pad"]
            if tail_start < e / fps:
                cuts.append((f"fin de rush {sh}", tail_start, e / fps))
                trimmed.append(f"tail {sh} {e / fps - tail_start:.2f}s")

    cut_frames = sorted((round(a * fps), round(b * fps)) for _, a, b in cuts if b > a)
    keep, pos = [], 0
    for a, b in cut_frames:
        if a > pos:
            keep.append([pos, a])
        pos = max(pos, b)
    if pos < clips.total_frames:
        keep.append([pos, clips.total_frames])

    ref = []  # clean ranges in reference frames, split on rush boundaries
    for a, b in keep:
        for n, i, o in clips.split(a, b):
            if o - i >= cfg["min_piece_frames"]:
                s = clips.start[n]
                if ref and ref[-1][1] == s + i and clips.at_frame(ref[-1][0]) == n:
                    ref[-1][1] = s + o
                else:
                    ref.append([s + i, s + o])

    # Isolated slivers. A rush change is a visual cut too, so pieces are "joined" only when contiguous in the SAME
    # rush. Lesson from a real edit: a 1.1 s "So, let's do" between a shortened gap and a rush change was a visible
    # break that the user removed, together with the orphan end of that sentence at the head of the next rush.
    def same_rush_joined(x, y):
        return x[1] == y[0] and clips.at_frame(x[0]) == clips.at_frame(y[0])

    dropped = []
    for k in range(len(ref) - 1, -1, -1):
        a, b = ref[k]
        joined_before = k > 0 and same_rush_joined(ref[k - 1], ref[k])
        joined_after = k + 1 < len(ref) and same_rush_joined(ref[k], ref[k + 1])
        if b - a < cfg["min_isolated"] * fps and not joined_before and not joined_after:
            dropped.append(f"{tc(a, fps, frames=True)} ({b - a} frames)")
            inside = [w for w in words if a <= w["start"] * fps < b and is_spoken(w)]
            continues = inside and not inside[-1]["text"].rstrip().endswith((".", "!", "?", "…"))
            nxt = ref[k + 1] if k + 1 < len(ref) else None
            del ref[k]
            if continues and nxt and nxt[0] == b:  # sentence carried on in the next rush: drop the orphan fragment
                head = [w for w in words if b <= w["start"] * fps < b + 2.5 * fps and is_spoken(w)]
                for i, w in enumerate(head[:-1]):
                    if w["text"].rstrip().endswith((",", ".", "!", "?", "…", ";", ":")):
                        new_start = round((head[i + 1]["start"] - cfg["head_pad"]) * fps)
                        if new_start > nxt[0]:
                            dropped.append(f"orphan fragment {tc(nxt[0], fps, frames=True)} "
                                           f"'{' '.join(x['text'] for x in head[:i + 1])}'")
                            nxt[0] = new_start
                        break

    report = {
        "removed_ranges": [(l, tc(a, fps), tc(b, fps), round(b - a, 2)) for l, a, b in remove],
        "gaps_shortened": [(tc(g["at"], fps), g["gap"]) for g in shortened],
        "gaps_kept_as_demo": [(tc(d["at"], fps), d["gap"], d["context"]) for d in demos],
        "heads_tails_trimmed": trimmed,
        "isolated_slivers_dropped": dropped,
    }
    return ref, [(l, round(a, 3), round(b, 3)) for l, a, b in cuts if b > a], demos, report


def review_markers(placed, cuts, demos, fps):
    """placed = [(ref_a, ref_b, timeline_frame), ...] consecutive pieces of ONE sequence.
    Returns markers [frame, color, name, note]: Red = removed passage, Blue = shortened gap, Green = demo gap kept."""
    markers = []
    for (a0, b0, _), (a1, _, t1) in zip(placed, placed[1:]):
        if b0 == a1:
            continue
        why = [c for c in cuts if c[1] < a1 / fps and c[2] > b0 / fps]
        removed = [c for c in why if not c[0].startswith(("blanc", "debut de rush", "fin de rush"))]
        gaps = [c for c in why if c[0].startswith("blanc")]
        if removed:
            markers.append([t1, "Red", "Passage retire", ascii_only("; ".join(c[0] for c in removed))])
        elif gaps:
            markers.append([t1, "Blue", "Blanc raccourci", ascii_only(gaps[0][0] + " -> 1 s")])
    for d in demos:
        f = round(d["at"] * fps)
        for a, b, t in placed:
            if a <= f < b:
                markers.append([t + f - a, "Green", "Blanc garde (demo ?)", ascii_only(f"{d['gap']}s apres: ...{d['context']}")])
    return markers
