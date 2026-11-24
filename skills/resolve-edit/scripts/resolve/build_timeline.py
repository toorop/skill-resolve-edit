# Run inside Resolve via run_script_unsafe:  ARGS = {...}; exec(open(r"<...>/build_timeline.py", encoding="utf-8").read())
# Builds a NEW timeline from a plan produced by build_linear_edl.py or build_montage.py, then:
#   title card (Text+) + tail pieces (bloopers), audio cross fades, YouTube loudness normalization, review markers,
#   and a full verification (every piece: right rush, source in, duration; video/audio aligned; no gaps).
#
# ARGS:
#   plan              path of the plan JSON
#   name              timeline name (ASCII only!)
#   crossfade_frames  default 4 ("Cross Fade +3 dB", centered; falls back to left-aligned without handles)
#   normalize         default "YouTube" (mode of Timeline.NormalizeAudioLevel, RELATIVE set-level); None to skip
#   markers           default True
#
# API facts this relies on: AppendToTimeline endFrame is EXCLUSIVE; InsertFusionTitleIntoTimeline("Text+") inserts
# at the playhead on V1 (125 frames); accented Text+ text must go through comp.Execute Lua with decimal escapes.
import json

_A = dict({"crossfade_frames": 4, "normalize": "YouTube", "markers": True}, **ARGS)
with open(_A["plan"], encoding="utf-8") as _f:
    _P = json.load(_f)


def _lua_str(s):
    out = []
    for ch in s:
        if ch.isascii() and ch not in "\\'\n":
            out.append(ch)
        else:
            out.extend("\\%d" % b for b in ch.encode("utf-8"))
    return "'" + "".join(out) + "'"


def _all_clips(folder):
    res = {c.GetName(): c for c in folder.GetClipList()}
    for sub in folder.GetSubFolderList():
        res.update(_all_clips(sub))
    return res


mp = project.GetMediaPool()
subs = {f.GetName(): f for f in mp.GetRootFolder().GetSubFolderList()}
items = _all_clips(subs["Rushes"])
names = [project.GetTimelineByIndex(i + 1).GetName() for i in range(project.GetTimelineCount())]
if _A["name"] in names:
    raise Exception("timeline already exists: " + _A["name"])
mp.SetCurrentFolder(subs["Timelines"])
tl = mp.CreateEmptyTimeline(_A["name"])
project.SetCurrentTimeline(tl)
tl.SetStartTimecode("00:00:00:00")
base = tl.GetStartFrame()
mp.AppendToTimeline([{"mediaPoolItem": items[n], "startFrame": i, "endFrame": o} for n, i, o in _P["pieces"]])
main_frames = sum(o - i for _, i, o in _P["pieces"])

markers = list(_P.get("markers", []))
title_len = 0
if _P.get("title"):
    f = main_frames
    tl.SetCurrentTimecode("%02d:%02d:%02d:%02d" % (f // 90000, f // 1500 % 60, f // 25 % 60, f % 25))
    title = tl.InsertFusionTitleIntoTimeline("Text+")
    title_len = title.GetDuration()
    comp = title.GetFusionCompByIndex(1)
    tpl = [t for t in comp.GetToolList(False).values() if t.GetAttrs()["TOOLS_RegID"] == "TextPlus"][0]
    comp.Execute("comp:FindTool('%s'):SetInput('StyledText', %s)" % (tpl.GetAttrs()["TOOLS_Name"], _lua_str(_P["title"]["text"])))
    markers.append([main_frames, "Pink", "Titre", "Text+ " + str(title_len) + " images"])
    pos = main_frames + title_len
    tail = []
    for n, i, o in _P["tail_pieces"]:  # recordFrame places them after the (silent) title, keeping audio in sync
        tail.append({"mediaPoolItem": items[n], "startFrame": i, "endFrame": o, "recordFrame": base + pos, "trackIndex": 1})
        pos += o - i
    mp.AppendToTimeline(tail)
    markers += [[main_frames + title_len + off, c, n, t] for off, c, n, t in _P.get("tail_markers", [])]

# verification
v = [x for x in tl.GetItemListInTrack("video", 1) if x.GetName() != "Text+"]
a = [x for x in tl.GetItemListInTrack("audio", 1) if x.GetType() == "audio"]
expected = _P["pieces"] + _P.get("tail_pieces", [])
bad = [k for k, ((n, i, o), x, y) in enumerate(zip(expected, v, a))
       if x.GetName() != n or x.GetLeftOffset() != i or x.GetDuration() != o - i
       or y.GetLeftOffset() != i or y.GetDuration() != o - i or y.GetStart() != x.GetStart()]
allv = tl.GetItemListInTrack("video", 1)
gaps = [k for k in range(1, len(allv)) if allv[k].GetStart() != allv[k - 1].GetEnd()]

# audio cross fades at every contiguous cut
xf = {"centered": 0, "left": 0, "failed": 0}
if _A["crossfade_frames"]:
    for k in range(len(a) - 1):
        if a[k + 1].GetStart() != a[k].GetEnd():
            continue
        done = False
        for al in ("center", "left", "right"):
            if a[k].AddTransition({"type": "Cross Fade +3 dB", "category": "audio", "position": "end",
                                   "alignment": al, "duration": _A["crossfade_frames"]}):
                xf["centered" if al == "center" else "left"] += 1
                done = True
                break
        xf["failed"] += 0 if done else 1

norm = None
if _A["normalize"]:
    norm = tl.NormalizeAudioLevel(a, {"normalizationMode": _A["normalize"],
                                      "setLevelMode": resolve.NORMALIZE_AUDIO_SET_LEVEL_RELATIVE})
    norm = sorted({x.GetProperty().get("AudioVolume") for x in a})

nm = 0
if _A["markers"]:
    for f, col, n, t in markers:
        nm += 1 if tl.AddMarker(int(f), col, n, t, 1) else 0

resolve.GetProjectManager().SaveProject()
result = {"timeline": _A["name"], "frames": tl.GetEndFrame() - base,
          "expected_frames": main_frames + title_len + sum(o - i for _, i, o in _P.get("tail_pieces", [])),
          "pieces": len(v), "bad_pieces": bad, "gaps": gaps, "title_frames": title_len,
          "crossfades": xf, "normalized_volume_db": norm, "markers": nm}
