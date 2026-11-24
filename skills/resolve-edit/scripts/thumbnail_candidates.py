"""Thumbnail search at low token cost: the transcript preselects moments where the presenter SHOWS something
(cues from the channel profile), ffmpeg extracts one frame per moment from the rushes (through the viewing LUT of
the rush's camera for log / HLG footage, if the profile gives one) and tiles them into contact
sheets. Claude looks at 1-2 sheets (not dozens of images), picks 3-5 candidates, then exports them full size
for the user (who makes the real thumbnail from the graded image in Resolve).

Only moments still present in the FINAL timeline are kept, with their FINAL timecode.

Usage:
  python thumbnail_candidates.py TRANSCRIPT.json CLIPS.json FINAL_DUMP.json RUSHES_DIR OUT_DIR [--max 20] [--profile DIR]
  python thumbnail_candidates.py ... OUT_DIR --export 3,7,12      (full-size PNGs of chosen candidates)
Output: OUT_DIR/sheet_N.png, OUT_DIR/candidates.json (id, FINAL tc, reference tc, rush, cue, context)
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

from common import Clips, add_profile_arg, camera_rules, fps_arg, load_json, load_settings, load_words, save_json, tc

FONT = r"C:\Windows\Fonts\arial.ttf"
# From the channel profile's settings.json "thumbnail":
#   cues        [[regex, weight], ...] moments where an object is shown / the scene is striking (language-specific)
#   show_delay  seconds after the cue (the object is usually in frame by then), default 1.5
#   lut         viewing LUT (.cube) for rushes of a camera without its own "lut", or null
#   font        font file for the labels (default Arial)
# and from "cameras": [{"name", "match", "short_name", "lut"}, ...]: the viewing LUT of each camera (log, HLG...).
CFG = {}
LUTS = {}  # LUT path -> helper file name copied next to the outputs


def lut_for(clips, cams, name):
    """Viewing LUT of a rush: its camera's "lut" (camera recorded in clips.json, else the first camera whose
    short_name / match pattern fits the file name), else thumbnail.lut. An explicit "lut": null means none."""
    cam = next((c for c in cams if c.get("name") and c["name"] == clips.camera(name)), None)
    if cam is None and not clips.camera(name):
        cam = next((c for c in cams if (c["_short"] and c["_short"].search(name))
                    or (c["_match"] and c["_match"].search(name))), None)
    path = cam["lut"] if cam is not None and "lut" in cam else CFG.get("lut")
    if path and path not in LUTS:
        LUTS[path] = f"_lut{len(LUTS)}.cube"
    return LUTS.get(path) if path else None


def final_position(final_items, clip, src_frame):
    hits = [it for it in final_items if it[1] == clip and it[5] <= src_frame < it[5] + (it[4] - it[3])]
    if not hits:
        return None
    it = max(hits, key=lambda x: x[0])  # topmost track
    return it[3] + src_frame - it[5]


def ffmpeg_frame(rush, seconds, out, width, label, workdir, lut=None):
    if lut and not os.path.exists(os.path.join(workdir, lut)):  # copied next to the outputs: no path escaping
        shutil.copy(next(p for p, f in LUTS.items() if f == lut), os.path.join(workdir, lut))
    vf = (f"lut3d={lut}," if lut else "") + f"scale={width}:-2"
    if label:
        label = label.replace(":", r"\:")  # ':' separates filter options
        vf += (f",drawtext=fontfile=_font.ttf:text='{label}':x=10:y=10:fontsize={width // 14}:"
               "fontcolor=yellow:box=1:boxcolor=black@0.6:boxborderw=6")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{seconds:.3f}", "-i", rush, "-frames:v", "1",
                    "-vf", vf, out], check=True, cwd=workdir)


def main():
    try:
        run()
    finally:  # remove the helper copies (LUT, font) from the output folder
        out = os.path.abspath(sys.argv[5]) if len(sys.argv) > 5 else None
        for f in os.listdir(out) if out and os.path.isdir(out) else []:
            if f == "_font.ttf" or (f.startswith("_lut") and f.endswith(".cube")):
                os.remove(os.path.join(out, f))


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("clips")
    ap.add_argument("final")
    ap.add_argument("rushes")
    ap.add_argument("out")
    ap.add_argument("--max", type=int, default=20)
    fps_arg(ap)
    ap.add_argument("--export", default="")
    add_profile_arg(ap)
    args = ap.parse_args()
    settings = load_settings(args.profile)
    CFG.update(settings.get("thumbnail") or {})
    cams = camera_rules(settings)
    args.out, args.rushes = os.path.abspath(args.out), os.path.abspath(args.rushes)  # ffmpeg runs with cwd=out
    os.makedirs(args.out, exist_ok=True)
    shutil.copy(CFG.get("font") or FONT, os.path.join(args.out, "_font.ttf"))
    clips = Clips(args.clips, args.fps, settings)
    fps = clips.fps

    if args.export:
        cands = {c["id"]: c for c in load_json(os.path.join(args.out, "candidates.json"))}
        for i in (int(x) for x in args.export.split(",")):
            c = cands[i]
            out = os.path.join(args.out, f"vignette_{i:02d}_{c['final_tc'].replace(':', '')}.png")
            ffmpeg_frame(os.path.join(args.rushes, clips.file(c["rush"])), c["src_seconds"], out, 1920, None, args.out,
                         lut_for(clips, cams, c["rush"]))
            print(out)
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

    cands = []
    for i, c in enumerate(chosen, 1):
        final_tc = tc(c["final_frame"], fps, frames=True)
        ffmpeg_frame(os.path.join(args.rushes, clips.file(c["rush"])), c["src_seconds"],
                     os.path.join(args.out, f"_t{i:02d}.png"), 384, f"{i}  {final_tc[3:8]}", args.out,
                     lut_for(clips, cams, c["rush"]))
        cands.append({"id": i, "final_tc": final_tc, "reference_tc": tc(c["ref"], fps), "rush": c["rush"],
                      "rush_short": clips.short(c["rush"]), "src_seconds": round(c["src_seconds"], 3),
                      "cue": c["cue"], "weight": c["weight"], "context": c["context"]})
    save_json(os.path.join(args.out, "candidates.json"), cands, indent=1)
    per = 20
    for s in range((len(cands) + per - 1) // per):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-start_number", str(s * per + 1), "-i", "_t%02d.png",
                        "-frames:v", "1", "-vf", "tile=5x4:padding=4:color=white", f"sheet_{s + 1}.png"],
                       check=True, cwd=args.out)
    for f in os.listdir(args.out):
        if f.startswith("_t") and f.endswith(".png"):
            os.remove(os.path.join(args.out, f))
    print(f"{len(cands)} candidates, {(len(cands) + per - 1) // per} sheet(s) in {args.out}")
    for c in cands:
        print(f"  {c['id']:2d} FINAL {c['final_tc']} {c['rush_short']} [{c['cue']}] {c['context'][:70]}")


if __name__ == "__main__":
    main()
