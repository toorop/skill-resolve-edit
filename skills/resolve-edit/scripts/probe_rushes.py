"""Step 1: inventory of the rushes, whatever the cameras and however the user sorted them.

Walks RUSHES_DIR and ALL its sub-folders (one folder per camera, per day, or everything together), keeps the video
files, reads each one with ffprobe (rate, resolution, codec, colour transfer, duration, recording time), recognises
its camera (profile "cameras", else its metadata), gives it a short name, and sorts everything by recording time.
Proposes the reference timeline format (the lowest common one: the reference only serves the transcript and the
scene index; the montage format is chosen later) and warns about what needs the user's eye.

Usage: python probe_rushes.py RUSHES_DIR OUT.json [--profile DIR]
Output: OUT.json (read by resolve/import_reference.py) and a table to show the user.

Recording time = the file's creation_time (UTC) + the camera's clock_offset (profile), else the file date (flagged).
Cameras filming at the same time (overlapping recordings) are flagged: simultaneous multicam is not handled yet.
"""
import argparse
import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from fractions import Fraction

from common import add_profile_arg, camera_rules, load_settings, save_json, short_from_pattern

VIDEO_EXT = {".mp4", ".mov", ".mxf", ".mts", ".m2ts", ".avi", ".mkv", ".m4v", ".insv", ".braw", ".r3d", ".crm"}
SIGNATURE_TAGS = ("encoder", "major_brand", "compatible_brands", "com.apple.quicktime.make", "com.apple.quicktime.model",
                  "make", "model", "com.android.manufacturer", "com.android.model", "handler_name", "vendor_id")


def ffprobe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode:
        return None
    return json.loads(out.stdout or "{}")


def parse_utc(value):
    try:
        t = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if t.tzinfo is None:  # no zone given: QuickTime convention is UTC
        t = t.replace(tzinfo=timezone.utc)
    if t.year < 2005:  # camera clock never set (1970, 2000-01-01...)
        return None
    return t.astimezone(timezone.utc)


def rate(text):
    try:
        f = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    return float(f) if f > 0 else None


TRANSFER = {"arib-std-b67": "HLG", "smpte2084": "PQ", "bt709": "", "unknown": "", None: ""}


def fps_label(fps):
    return f"{fps:g}p" if fps else "?"


def describe(path, rel, cams):
    info = ffprobe(path)
    if not info:
        return {"file": rel, "error": "unreadable by ffprobe"}
    fmt = info.get("format", {})
    tags = {k.lower(): v for k, v in (fmt.get("tags") or {}).items()}
    streams = info.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")
             and s.get("codec_name") not in ("mjpeg", "png")]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if not video:
        return {"file": rel, "error": "no video stream"}
    v = video[0]
    sig_parts = [str(tags[k]) for k in SIGNATURE_TAGS if k in tags]
    for s in streams:
        st = {k.lower(): val for k, val in (s.get("tags") or {}).items()}
        sig_parts += [str(st[k]) for k in ("handler_name", "vendor_id", "encoder") if k in st]
    signature = " | ".join(dict.fromkeys(sig_parts))
    cam = next((c for c in cams if c["_match"] and (c["_match"].search(rel) or c["_match"].search(signature))), None)
    if cam is None:
        cam = next((c for c in cams if not c["_match"] and c["_short"] and c["_short"].search(os.path.basename(rel))), None)
    camera = cam["name"] if cam else (tags.get("encoder") or " ".join(
        x for x in (tags.get("com.apple.quicktime.make") or tags.get("make"), tags.get("com.apple.quicktime.model")
                    or tags.get("model")) if x) or tags.get("major_brand") or "unknown").strip()

    created = parse_utc(tags.get("creation_time") or (v.get("tags") or {}).get("creation_time") or
                        tags.get("com.apple.quicktime.creationdate") or "")
    source = "metadata"
    if created is None:
        created = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
        source = "file date (unreliable)"
    offset = float((cam or {}).get("clock_offset") or 0)
    created += timedelta(seconds=offset)

    fps = rate(v.get("r_frame_rate") or "") or rate(v.get("avg_frame_rate") or "")
    avg = rate(v.get("avg_frame_rate") or "")
    duration = float(fmt.get("duration") or v.get("duration") or 0)
    width, height = v.get("width"), v.get("height")
    rot = 0
    for sd in v.get("side_data_list") or []:
        rot = int(sd.get("rotation", 0) or 0) or rot
    if abs(rot) in (90, 270):
        width, height = height, width
    name = os.path.basename(rel)
    short = short_from_pattern(name, cam["_short"]) if cam else None
    return {
        "file": rel, "name": name, "short": short or os.path.splitext(name)[0], "camera": camera,
        "fps": round(fps, 3) if fps else None, "variable_fps": bool(fps and avg and abs(fps - avg) > 0.01 * fps),
        "width": width, "height": height, "codec": v.get("codec_name"), "pix_fmt": v.get("pix_fmt"),
        "transfer": v.get("color_transfer"), "duration": round(duration, 3),
        "audio": [f"{a.get('codec_name')} {a.get('channels')}ch {a.get('sample_rate')}Hz" for a in audio],
        "recorded_utc": created.isoformat().replace("+00:00", "Z"), "time_source": source, "clock_offset": offset,
        "timecode": tags.get("timecode") or (v.get("tags") or {}).get("timecode"), "signature": signature,
    }


def propose_format(rushes):
    """Lowest common format: the smallest rate that divides all the others (else the rate with the most footage),
    the smallest frame size."""
    fpss = sorted({r["fps"] for r in rushes if r["fps"]})
    weight = Counter()
    for r in rushes:
        weight[r["fps"]] += r["duration"]
    common = next((f for f in fpss if all(abs(g / f - round(g / f)) < 1e-3 for g in fpss)), None)
    fps = common or weight.most_common(1)[0][0]
    why = ("single rate" if len(fpss) == 1 else
           f"lowest common rate of {', '.join(fps_label(f) for f in fpss)}" if common else
           f"rates {', '.join(fps_label(f) for f in fpss)} have no common divisor: rate with the most footage, ASK THE USER")
    smallest = min(rushes, key=lambda r: (r["width"] or 0) * (r["height"] or 0))
    fps_out = int(fps) if fps == int(fps) else fps
    return {"fps": fps_out, "width": smallest["width"], "height": smallest["height"], "why": why}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rushes")
    ap.add_argument("out")
    add_profile_arg(ap)
    args = ap.parse_args()
    settings = load_settings(args.profile)
    cams = camera_rules(settings)
    ignore = [re.compile(p, re.I) for p in (settings.get("rushes") or {}).get("ignore") or []]
    root = os.path.abspath(args.rushes)

    rushes, skipped, errors = [], Counter(), []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(d, f), root).replace("\\", "/")
            ext = os.path.splitext(f)[1].lower()
            if f.startswith(".") or ext not in VIDEO_EXT or any(p.search(rel) for p in ignore):
                skipped[ext or f] += 1
                continue
            r = describe(os.path.join(d, f), rel, cams)
            (errors if "error" in r else rushes).append(r)
    if not rushes:
        raise SystemExit(f"No video file found in {root} (sub-folders included).")
    rushes.sort(key=lambda r: (r["recorded_utc"], r["file"]))

    warnings = []
    names = Counter(r["name"] for r in rushes)
    for n, k in names.items():
        if k > 1:
            warnings.append(f"{k} files are named {n} (different folders): Resolve would mix them up; rename them first")
    shorts = Counter(r["short"] for r in rushes)
    for r in rushes:
        if shorts[r["short"]] > 1:
            r["short"] = os.path.splitext(r["name"])[0]
    for s, k in Counter(r["short"] for r in rushes).items():
        if k > 1:
            warnings.append(f"short name {s} is not unique")
    for r in rushes:
        if r["time_source"] != "metadata":
            warnings.append(f"{r['file']}: no recording time in the file, file date used (order to check)")
        if r["variable_fps"]:
            warnings.append(f"{r['file']}: variable frame rate (phone?): Resolve may drift; check sync")
    for a, b in zip(rushes, rushes[1:]):
        end_a = datetime.fromisoformat(a["recorded_utc"].replace("Z", "+00:00")) + timedelta(seconds=a["duration"])
        start_b = datetime.fromisoformat(b["recorded_utc"].replace("Z", "+00:00"))
        if (end_a - start_b).total_seconds() > 2:
            what = ("cameras filming AT THE SAME TIME (multicam is not handled yet: keep one, or check the clocks)"
                    if a["camera"] != b["camera"] else "overlapping recordings of one camera (clock changed?)")
            warnings.append(f"{a['short']} ({a['camera']}) and {b['short']} ({b['camera']}) overlap by "
                            f"{(end_a - start_b).total_seconds():.0f}s: {what}")
    cams_used = list(dict.fromkeys(r["camera"] for r in rushes))
    if len(cams_used) > 1:
        warnings.append("several cameras: the order relies on their clocks; ask the user to check it in the table")
    timeline = propose_format(rushes)
    if len({(r["width"], r["height"]) for r in rushes}) > 1:
        warnings.append("mixed frame sizes: the reference uses the smallest; the montage format is chosen later")
    if any(r["width"] and r["height"] and r["width"] < r["height"] for r in rushes) and \
            any(r["width"] and r["height"] and r["width"] > r["height"] for r in rushes):
        warnings.append("vertical and horizontal rushes mixed: ask the user how to frame the vertical ones")

    save_json(args.out, {"rushes_dir": root, "timeline": timeline, "cameras": cams_used, "rushes": rushes,
                         "unreadable": errors, "skipped": dict(skipped), "warnings": warnings})

    print(f"{len(rushes)} rushes from {len(cams_used)} camera(s) in {root}"
          + (f"; skipped: {', '.join(f'{k} x{v}' for k, v in sorted(skipped.items()))}" if skipped else ""))
    print(f"Proposed reference timeline: {fps_label(timeline['fps'])} {timeline['width']}x{timeline['height']} "
          f"({timeline['why']})\n")
    rows = []
    for k, r in enumerate(rushes, 1):
        local = datetime.fromisoformat(r["recorded_utc"].replace("Z", "+00:00")).astimezone()
        fmt = f"{r['width']}x{r['height']} {fps_label(r['fps'])} {r['codec']} {TRANSFER.get(r['transfer'], r['transfer'])}"
        m, s = divmod(int(round(r["duration"])), 60)
        rows.append((str(k), f"{local:%Y-%m-%d %H:%M:%S}", r["camera"], r["short"], fmt.strip(), f"{m}:{s:02d}", r["file"]))
    head = ("#", "recorded (local time)", "camera", "short", "format", "length", "file")
    w = [max(len(x[i]) for x in rows + [head]) for i in range(len(head))]
    for row in [head] + rows:
        print("  ".join(c.rjust(w[i]) if i in (0, 5) else c.ljust(w[i]) for i, c in enumerate(row)).rstrip())
    for e in errors:
        print(f"UNREADABLE: {e['file']}: {e['error']}")
    for w in warnings:
        print(f"WARNING: {w}")


if __name__ == "__main__":
    main()
