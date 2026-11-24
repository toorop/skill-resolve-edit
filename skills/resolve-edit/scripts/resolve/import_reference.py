# Run inside Resolve via the MCP tool run_script_unsafe:
#   ARGS = {...}; exec(open(r"<skill>/scripts/resolve/import_reference.py", encoding="utf-8").read())
# Globals provided by the MCP: resolve, project. Sets `result`.
#
# Imports the rushes, creates bins and the REFERENCE timeline (all used rushes end to end, in name order,
# start TC 00:00:00:00), then writes the clips map (clips.json) used by every other script.
#
# ARGS:
#   rushes_dir        folder with the camera files (e.g. G:\...\rushes)
#   exclude           list of rush short names to import but keep OUT of the reference (e.g. ["C0012", "C0015"])
#   clips_out         path of clips.json to write
#   reference_name    default "00 - REFERENCE (ne pas modifier)"
#   extensions        default [".mp4", ".mov", ".mxf"]
# Names must stay ASCII: the scripting bridge double-encodes accents (é -> Ã©) and bins cannot be renamed.
import json
import os
import re

_A = dict({"reference_name": "00 - REFERENCE (ne pas modifier)", "exclude": [],
           "extensions": [".mp4", ".mov", ".mxf"]}, **ARGS)


def _short(n):
    m = re.search(r"C\d{4}", n)
    return m.group(0) if m else os.path.splitext(n)[0]


mp = project.GetMediaPool()
root = mp.GetRootFolder()
subs = {f.GetName(): f for f in root.GetSubFolderList()}
rushes_bin = subs.get("Rushes") or mp.AddSubFolder(root, "Rushes")
tl_bin = subs.get("Timelines") or mp.AddSubFolder(root, "Timelines")
unused_bin = {f.GetName(): f for f in rushes_bin.GetSubFolderList()}.get("Non retenus")

files = sorted(f for f in os.listdir(_A["rushes_dir"]) if os.path.splitext(f)[1].lower() in _A["extensions"])
used = [f for f in files if _short(f) not in _A["exclude"]]
excluded = [f for f in files if _short(f) in _A["exclude"]]
existing = {c.GetName() for c in rushes_bin.GetClipList()}
mp.SetCurrentFolder(rushes_bin)
mp.ImportMedia([os.path.join(_A["rushes_dir"], f) for f in files if f not in existing])
if excluded:
    unused_bin = unused_bin or mp.AddSubFolder(rushes_bin, "Non retenus")
    mp.MoveClips([c for c in rushes_bin.GetClipList() if c.GetName() in excluded], unused_bin)

items = {c.GetName(): c for c in rushes_bin.GetClipList()}
names = [project.GetTimelineByIndex(i + 1).GetName() for i in range(project.GetTimelineCount())]
if _A["reference_name"] in names:
    raise Exception("reference timeline already exists: " + _A["reference_name"])
mp.SetCurrentFolder(tl_bin)
tl = mp.CreateEmptyTimeline(_A["reference_name"])
project.SetCurrentTimeline(tl)
tl.SetStartTimecode("00:00:00:00")
mp.AppendToTimeline([items[f] for f in used])
v = tl.GetItemListInTrack("video", 1)
base = tl.GetStartFrame()
clips = [[it.GetName(), it.GetStart() - base, it.GetEnd() - base] for it in v]
gaps = [k for k in range(1, len(v)) if v[k].GetStart() != v[k - 1].GetEnd()]
expected = sum(int(items[f].GetClipProperty("Frames")) for f in used)
os.makedirs(os.path.dirname(_A["clips_out"]), exist_ok=True)
with open(_A["clips_out"], "w", encoding="utf-8") as fh:
    json.dump(clips, fh)
props = items[used[0]].GetClipProperty()
resolve.GetProjectManager().SaveProject()
result = {"imported": len(files), "in_reference": len(used), "excluded": excluded, "gaps": gaps,
          "frames": tl.GetEndFrame() - base, "expected_frames": expected,
          "timeline_res": [tl.GetSetting("timelineResolutionWidth"), tl.GetSetting("timelineResolutionHeight")],
          "timeline_fps": tl.GetSetting("timelineFrameRate"),
          "rush_format": [props.get("Resolution"), props.get("FPS"), props.get("Audio Ch")],
          "clips_json": _A["clips_out"]}
