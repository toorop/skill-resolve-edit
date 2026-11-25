# Run inside Resolve via the MCP tool run_script_unsafe:
#   ARGS = {...}; exec(open(r"<skill>/scripts/resolve/export_frames.py", encoding="utf-8").read())
# Globals provided by the MCP: resolve, project. Sets `result`.
#
# Every image the skill needs, rendered by Resolve (Timeline / MediaPoolItem .ExportThumbnails / .ExportFrame,
# 21.2): labelled contact sheets for Claude or the user, or single full-size frames.
# From a TIMELINE the image is what the timeline shows (grade, group pre/post-clip, titles, Fusion, sizing); from a
# RUSH (media pool clip) it is the source image, ungraded. Ungraded log / HLG footage comes out flat but readable:
# fine for seeing what happens; the skill never touches colour.
#
# ARGS:
#   out_dir        output folder (created)
#   timeline       timeline name (default: the current timeline)       } frames count from the timeline start,
#   rush           OR a media pool clip name (frames = the rush's own)  } in the timeline's / rush's own frames
#   mode           "sheet" (default): contact sheets of `per_sheet` frames, labelled
#                  "single": one image per frame (entry "name" = file name, else frame_<n>.png)
#                  "cuts": sheets of every cut of video track `track`: last frame before / first frame after,
#                  labelled "<n>a|b <timecode> <clip>" (no `frames` needed)
#   frames         list of frame numbers, or of {"frame": n | "tc": "HH:MM:SS:FF", "label": str, "name": str};
#                  "tc" is a timecode of the timeline (its own start timecode counts)
#   frames_json    OR the path of a JSON file holding that list (written by thumbnail_candidates.py)
#   name           base name of the sheets (default "sheet" -> sheet_1.jpg, sheet_2.jpg...)
#   per_sheet      frames per sheet (default 20; Resolve picks the grid)
#   max_dimension  longer edge in pixels: sheets default 1920 (whole sheet), single frames default 0 (full size)
#   quality        JPEG quality of the sheets (default 85); single frames are PNG unless "name" says .jpg
#   track          video track for "cuts" (default 1)
#   clips_json     optional clips.json: "cuts" labels then use the rushes' short names (DJI0030) instead of file
#                  names, which are cut off when long
import json
import os
import time

_A = dict({"timeline": None, "rush": None, "mode": "sheet", "frames": None, "frames_json": None, "name": "sheet",
           "per_sheet": 20, "max_dimension": None, "quality": 85, "track": 1, "clips_json": None}, **ARGS)
_t0 = time.time()
_short = {}
if _A["clips_json"]:
    with open(_A["clips_json"], encoding="utf-8") as _fh:
        _cj = json.load(_fh)
    if isinstance(_cj, dict):
        _short = {c["name"]: c.get("short") or c["name"] for c in _cj["clips"]}


def _label_name(name):
    name = _short.get(name, os.path.splitext(name)[0])
    return name if len(name) <= 14 else "..." + name[-11:]


def _all_clips(folder):
    res = list(folder.GetClipList())
    for sub in folder.GetSubFolderList():
        res.extend(_all_clips(sub))
    return res


def _tc_frames(tc, base):
    h, m, s, f = (int(x) for x in tc.replace(";", ":").split(":"))
    return ((h * 60 + m) * 60 + s) * base + f


def _tc(frames, base):
    frames %= 24 * 3600 * base
    return "%02d:%02d:%02d:%02d" % (frames // (3600 * base), frames // (60 * base) % 60, frames // base % 60,
                                    frames % base)


if _A["rush"]:
    _matches = [c for c in _all_clips(project.GetMediaPool().GetRootFolder()) if c.GetName() == _A["rush"]]
    if len(_matches) != 1:
        raise Exception("%d media pool clips named %s" % (len(_matches), _A["rush"]))
    src = _matches[0]
    _base = int(round(float(src.GetClipProperty("FPS"))))
    _start_tc = _tc_frames(src.GetClipProperty("Start TC") or "00:00:00:00", _base)
    _length = int(src.GetClipProperty("Frames"))
    _items = None
else:
    if _A["timeline"]:
        _tls = [project.GetTimelineByIndex(i + 1) for i in range(project.GetTimelineCount())]
        _named = [t for t in _tls if t.GetName() == _A["timeline"]]
        if not _named:
            raise Exception("no timeline named %s" % _A["timeline"])
        src = _named[0]
    else:
        src = project.GetCurrentTimeline()
    _base = int(round(float(src.GetSetting("timelineFrameRate"))))
    _start_tc = _tc_frames(src.GetStartTimecode(), _base)
    _length = src.GetEndFrame() - src.GetStartFrame()


def _entry(e):
    if not isinstance(e, dict):
        e = {"frame": int(e)}
    e = dict(e)
    if "frame" not in e:
        e["frame"] = _tc_frames(e["tc"], _base) - _start_tc
    e["frame"] = int(e["frame"])
    e.setdefault("label", _tc(_start_tc + e["frame"], _base))
    return e


if _A["mode"] == "cuts":
    if _A["rush"]:
        raise Exception("cuts needs a timeline")
    _first = src.GetStartFrame()
    _its = [it for it in (src.GetItemListInTrack("video", _A["track"]) or [])]
    _frames, _n = [], 0
    for _a, _b in zip(_its, _its[1:]):
        _n += 1
        _ea, _sb = _a.GetEnd() - _first, _b.GetStart() - _first
        gap = "" if _sb == _ea else " (gap %d)" % (_sb - _ea)
        _frames.append({"frame": _ea - 1, "label": "%da %s %s" % (_n, _tc(_start_tc + _ea - 1, _base), _label_name(_a.GetName()))})
        _frames.append({"frame": _sb, "label": "%db %s %s%s" % (_n, _tc(_start_tc + _sb, _base), _label_name(_b.GetName()), gap)})
else:
    _raw = _A["frames"]
    if _A["frames_json"]:
        with open(_A["frames_json"], encoding="utf-8") as _fh:
            _raw = json.load(_fh)
    if not _raw:
        raise Exception("no frames given")
    _frames = [_entry(e) for e in _raw]

_bad = [f["frame"] for f in _frames if not 0 <= f["frame"] < _length]
if _bad:
    raise Exception("frames outside the %s (0-%d): %s" % ("rush" if _A["rush"] else "timeline", _length - 1, _bad[:10]))
os.makedirs(_A["out_dir"], exist_ok=True)
files, errors = [], []
if _A["mode"] == "single":
    for f in _frames:
        path = os.path.join(_A["out_dir"], f.get("name") or "frame_%06d.png" % f["frame"])
        r = src.ExportFrame(f["frame"], {"outputType": "file", "filePath": path, "maxDimension": _A["max_dimension"] or 0,
                                         "quality": 100})
        (files if r.get("success") else errors).append(path if r.get("success") else [path, r.get("error")])
else:
    per = int(_A["per_sheet"])
    if _A["mode"] == "cuts" and per % 2:
        per += 1  # keep the a / b frames of a cut on the same sheet
    for k in range(0, len(_frames), per):
        path = os.path.join(_A["out_dir"], "%s_%d.jpg" % (_A["name"], k // per + 1))
        chunk = [{"frameOffset": f["frame"], "label": f["label"]} for f in _frames[k:k + per]]
        r = src.ExportThumbnails(chunk, {"outputType": "file", "filePath": path, "quality": int(_A["quality"]),
                                         "maxDimension": _A["max_dimension"] or 1920})
        if r.get("success"):
            files.append([path, "%dx%d" % (r["columns"], r["rows"])])
        else:
            errors.append([path, r.get("error")])
result = {"source": src.GetName(), "mode": _A["mode"], "frames": len(_frames), "files": files, "errors": errors,
          "seconds": round(time.time() - _t0, 1)}
if _A["mode"] == "cuts":
    result["cuts"] = len(_frames) // 2
