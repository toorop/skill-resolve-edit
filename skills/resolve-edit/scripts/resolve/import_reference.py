# Run inside Resolve via the MCP tool run_script_unsafe:
#   ARGS = {...}; exec(open(r"<skill>/scripts/resolve/import_reference.py", encoding="utf-8").read())
# Globals provided by the MCP: resolve, project. Sets `result`.
#
# Imports the rushes, creates bins and the REFERENCE timeline (all used rushes end to end, in the order of the
# inventory written by probe_rushes.py = recording time, start TC 00:00:00:00), then writes the clips map
# (clips.json) used by every other script. Rushes may have different rates and sizes: Resolve plays each one at
# its real speed in the timeline; clips.json records each rush's own rate.
#
# ARGS:
#   rushes_json       inventory from probe_rushes.py (order, sub-folder paths, short names, cameras)
#   exclude           list of rush short names to import but keep OUT of the reference (e.g. ["C0012", "DJI0043"])
#   clips_out         path of clips.json to write
#   fps, width, height  reference timeline format (default: the inventory's proposal, validated by the user)
#   reference_name    default "00 - REFERENCE (ne pas modifier)"
#   rushes_dir        only without rushes_json: every video file of this folder and its sub-folders, in name order
# Names must stay ASCII: the scripting bridge double-encodes accents (é -> Ã©) and bins cannot be renamed.
import json
import os

_A = dict({"reference_name": "00 - REFERENCE (ne pas modifier)", "exclude": [], "rushes_json": None,
           "fps": None, "width": None, "height": None}, **ARGS)
_VIDEO_EXT = {".mp4", ".mov", ".mxf", ".mts", ".m2ts", ".avi", ".mkv", ".m4v", ".insv", ".braw", ".r3d", ".crm"}


def _norm(p):
    return os.path.normcase(os.path.normpath(p))


def _num(x):
    x = float(x)
    return int(x) if x == int(x) else x


if _A["rushes_json"]:
    with open(_A["rushes_json"], encoding="utf-8") as _fh:
        _inv = json.load(_fh)
    _root = _inv["rushes_dir"]
    _rushes = _inv["rushes"]
    _fmt = dict(_inv["timeline"])
else:
    _root = _A["rushes_dir"]
    _rushes = []
    for _d, _dirs, _files in os.walk(_root):
        _dirs.sort()
        for _f in sorted(_files):
            if os.path.splitext(_f)[1].lower() in _VIDEO_EXT and not _f.startswith("."):
                _rel = os.path.relpath(os.path.join(_d, _f), _root).replace("\\", "/")
                _rushes.append({"file": _rel, "name": _f, "short": os.path.splitext(_f)[0], "camera": None})
    _fmt = {}
for _k in ("fps", "width", "height"):
    if _A[_k]:
        _fmt[_k] = _A[_k]

for _r in _rushes:
    _r["path"] = os.path.join(_root, _r["file"])
used = [r for r in _rushes if r["short"] not in _A["exclude"]]
excluded = [r for r in _rushes if r["short"] in _A["exclude"]]

mp = project.GetMediaPool()
root = mp.GetRootFolder()
subs = {f.GetName(): f for f in root.GetSubFolderList()}
rushes_bin = subs.get("Rushes") or mp.AddSubFolder(root, "Rushes")
tl_bin = subs.get("Timelines") or mp.AddSubFolder(root, "Timelines")
unused_bin = {f.GetName(): f for f in rushes_bin.GetSubFolderList()}.get("Non retenus")


def _by_path():
    res = {}
    for folder in [rushes_bin] + list(rushes_bin.GetSubFolderList()):
        for c in folder.GetClipList():
            res[_norm(c.GetClipProperty("File Path"))] = c
    return res


names = [project.GetTimelineByIndex(i + 1).GetName() for i in range(project.GetTimelineCount())]
if _A["reference_name"] in names:
    raise Exception("reference timeline already exists: " + _A["reference_name"])

# Timeline format: project settings while the project has no timeline yet, else the timeline's own settings.
_format_set = {}
if _fmt and project.GetTimelineCount() == 0:
    if _fmt.get("fps"):
        _format_set["project_fps"] = project.SetSetting("timelineFrameRate", str(_fmt["fps"]))
    if _fmt.get("width"):
        _format_set["project_res"] = (project.SetSetting("timelineResolutionWidth", str(_fmt["width"])) and
                                      project.SetSetting("timelineResolutionHeight", str(_fmt["height"])))

existing = _by_path()
mp.SetCurrentFolder(rushes_bin)
_new = [r["path"] for r in _rushes if _norm(r["path"]) not in existing]
if _new:
    mp.ImportMedia(_new)
items = _by_path()
missing = [r["file"] for r in _rushes if _norm(r["path"]) not in items]
if missing:
    raise Exception("not imported by Resolve: %s" % missing)
if excluded:
    unused_bin = unused_bin or mp.AddSubFolder(rushes_bin, "Non retenus")
    mp.MoveClips([items[_norm(r["path"])] for r in excluded], unused_bin)

mp.SetCurrentFolder(tl_bin)
tl = mp.CreateEmptyTimeline(_A["reference_name"])
project.SetCurrentTimeline(tl)
if _fmt.get("fps") and float(tl.GetSetting("timelineFrameRate")) != float(_fmt["fps"]):
    _format_set["timeline_custom"] = tl.SetSetting("useCustomSettings", "1")
    _format_set["timeline_fps"] = tl.SetSetting("timelineFrameRate", str(_fmt["fps"]))
if _fmt.get("width") and int(tl.GetSetting("timelineResolutionWidth")) != int(_fmt["width"]):
    _format_set["timeline_custom"] = tl.SetSetting("useCustomSettings", "1")
    _format_set["timeline_res"] = (tl.SetSetting("timelineResolutionWidth", str(_fmt["width"])) and
                                   tl.SetSetting("timelineResolutionHeight", str(_fmt["height"])))
tl.SetStartTimecode("00:00:00:00")
tl_fps = float(tl.GetSetting("timelineFrameRate"))
mp.AppendToTimeline([items[_norm(r["path"])] for r in used])

v = tl.GetItemListInTrack("video", 1)
base = tl.GetStartFrame()
gaps = [k for k in range(1, len(v)) if v[k].GetStart() != v[k - 1].GetEnd()]
clips, length_check = [], []
for r, it in zip(used, v):
    mpi = items[_norm(r["path"])]
    src_fps = float(mpi.GetClipProperty("FPS") or tl_fps)
    src_frames = int(mpi.GetClipProperty("Frames"))
    expect = src_frames * tl_fps / src_fps  # Resolve plays every rush at its real speed
    got = it.GetEnd() - it.GetStart()
    if abs(got - expect) > 1:
        length_check.append([r["short"], got, round(expect, 2)])
    clips.append({"name": it.GetName(), "start": it.GetStart() - base, "end": it.GetEnd() - base, "short": r["short"],
                  "camera": r.get("camera"), "fps": _num(src_fps), "file": r["file"]})
if [c["name"] for c in clips] != [r["name"] for r in used]:
    raise Exception("timeline order differs from the inventory")
out = {"version": 2, "fps": _num(tl_fps), "width": int(tl.GetSetting("timelineResolutionWidth")),
       "height": int(tl.GetSetting("timelineResolutionHeight")), "rushes_dir": _root, "clips": clips}
os.makedirs(os.path.dirname(_A["clips_out"]), exist_ok=True)
with open(_A["clips_out"], "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
resolve.GetProjectManager().SaveProject()
result = {"imported": len(_new), "in_reference": len(used), "excluded": [r["short"] for r in excluded], "gaps": gaps,
          "frames": tl.GetEndFrame() - base, "rush_length_mismatch": length_check,
          "timeline_format": [out["width"], out["height"], out["fps"]], "wanted_format": _fmt,
          "format_settings": _format_set, "rush_rates": sorted({c["fps"] for c in clips}), "clips_json": _A["clips_out"]}
