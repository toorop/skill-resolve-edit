"""Thumbnail search at low token cost: the transcript preselects moments where the presenter SHOWS something
(cues from the channel profile), only moments still present in the FINAL timeline are kept, with their FINAL frame.
Resolve renders them (resolve/export_frames.py on "03 - FINAL", so with the grade, sizing and titles of the FINAL)
into one or two labelled contact sheets that the USER looks at and picks from; then the picks are exported full
size. The user retouches the chosen frame for the thumbnail anyway (more saturation, warmer, stronger lines).

Usage:
  python thumbnail_candidates.py TRANSCRIPT.json CLIPS.json FINAL_DUMP.json OUT_DIR [--max 20] [--profile DIR]
  python thumbnail_candidates.py TRANSCRIPT.json CLIPS.json FINAL_DUMP.json OUT_DIR --export 3,7,12
Output: OUT_DIR/candidates.json (id, FINAL tc, reference tc, rush, cue, context) and OUT_DIR/sheet_frames.json;
  with --export: OUT_DIR/export_frames.json. Then resolve/export_frames.py, timeline "03 - FINAL":
  sheets:  {"frames_json": OUT_DIR/sheet_frames.json, "out_dir": OUT_DIR}                     -> sheet_N.jpg
  picks:   {"frames_json": OUT_DIR/export_frames.json, "out_dir": OUT_DIR, "mode": "single"}  -> vignette_NN_TC.png
"""
import argparse
import os
import re

from common import Clips, add_profile_arg, fps_arg, load_json, load_settings, load_words, save_json, tc

# From the channel profile's settings.json "thumbnail":
#   cues        [[regex, weight], ...] moments where an object is shown / the scene is striking (language-specific)
#   show_delay  seconds after the cue (the object is usually in frame by then), default 1.5
CFG = {}


def final_position(final_items, clip, src_frame):
    hits = [it for it in final_items if it[1] == clip and it[5] <= src_frame < it[5] + (it[4] - it[3])]
    if not hits:
        return None
    it = max(hits, key=lambda x: x[0])  # topmost track
    return it[3] + src_frame - it[5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("clips")
    ap.add_argument("final")
    ap.add_argument("out")
    ap.add_argument("--max", type=int, default=20)
    fps_arg(ap)
    ap.add_argument("--export", default="")
    add_profile_arg(ap)
    args = ap.parse_args()
    settings = load_settings(args.profile)
    CFG.update(settings.get("thumbnail") or {})
    args.out = os.path.abspath(args.out)
    os.makedirs(args.out, exist_ok=True)
    clips = Clips(args.clips, args.fps, settings)
    fps = clips.fps

    if args.export:
        cands = {c["id"]: c for c in load_json(os.path.join(args.out, "candidates.json"))}
        picks = []
        ids = [int(x) for x in args.export.split(",")]
        unknown = [i for i in ids if i not in cands]
        if unknown:
            raise SystemExit(f"no candidate {unknown} (ids are 1 to {max(cands)})")
        for i in ids:
            c = cands[i]
            h, m, sec, f = (int(x) for x in c["final_tc"].split(":"))  # tc() counts frames on the nominal rate
            frame = ((h * 60 + m) * 60 + sec) * int(round(fps)) + f
            picks.append({"frame": frame, "name": f"vignette_{i:02d}_{c['final_tc'].replace(':', '')}.png"})
        save_json(os.path.join(args.out, "export_frames.json"), picks)
        print(f"{os.path.join(args.out, 'export_frames.json')}: {len(picks)} frame(s); export them with "
              'resolve/export_frames.py (timeline "03 - FINAL", mode "single")')
        return

    words = load_words(args.transcript)
    final = load_json(args.final)
    titles = [it[3] for it in final["items"] if it[1] == "Text+"]
    items = [it for it in final["items"] if it[2] == "video" and it[1] != "Text+"
             and (not titles or it[3] < min(titles))]  # ignore bloopers

    text, index = "", []
    for w in words:
        index.append(len(text))
        text += w["text"].lower() + " "
    cues = CFG.get("cues") or []
    if not cues:
        raise SystemExit('No thumbnail "cues" in the channel profile settings.json: nothing to preselect.')
    delay = CFG.get("show_delay", 1.5)
    found = []
    for pat, weight in cues:
        for m in re.finditer(pat, text):
            wi = max(i for i, off in enumerate(index) if off <= m.start())
            t = words[wi]["start"] + delay
            clip = clips.at(t)
            if not clip:
                continue
            src = round(t * fps) - clips.start[clip]
            ffr = final_position(items, clip, src)
            if ffr is None:
                continue
            ctx = " ".join(w["text"] for w in words[max(0, wi - 4):wi + 10])
            found.append({"weight": weight, "ref": t, "final_frame": ffr, "rush": clip, "src_seconds": src / fps,
                          "cue": m.group(0), "context": ctx})
    found.sort(key=lambda c: (-c["weight"], c["ref"]))
    chosen = []
    for c in found:  # one candidate per 15 s window, strongest first
        if all(abs(c["ref"] - k["ref"]) > 15 for k in chosen):
            chosen.append(c)
        if len(chosen) >= args.max:
            break
    chosen.sort(key=lambda c: c["final_frame"])

    cands, sheet = [], []
    for i, c in enumerate(chosen, 1):
        final_tc = tc(c["final_frame"], fps, frames=True)
        sheet.append({"frame": c["final_frame"], "label": f"{i}  {final_tc[3:8]}"})
        cands.append({"id": i, "final_tc": final_tc, "reference_tc": tc(c["ref"], fps), "rush": c["rush"],
                      "rush_short": clips.short(c["rush"]), "src_seconds": round(c["src_seconds"], 3),
                      "cue": c["cue"], "weight": c["weight"], "context": c["context"]})
    save_json(os.path.join(args.out, "candidates.json"), cands, indent=1)
    save_json(os.path.join(args.out, "sheet_frames.json"), sheet)
    print(f"{len(cands)} candidates in {args.out}; render the sheet(s) with resolve/export_frames.py "
          '(timeline "03 - FINAL", frames_json = sheet_frames.json)')
    for c in cands:
        print(f"  {c['id']:2d} FINAL {c['final_tc']} {c['rush_short']} [{c['cue']}] {c['context'][:70]}")


if __name__ == "__main__":
    main()
