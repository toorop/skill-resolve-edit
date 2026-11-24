# Run inside Resolve via run_script_unsafe:  ARGS = {...}; exec(open(r"<...>/dump_timeline.py", encoding="utf-8").read())
# Writes the REAL current state of a timeline (e.g. "03 - FINAL" after the user's manual tweaks) to JSON,
# so chapters / later edits never rely on stale plans.
#
# ARGS: timeline (name), out (path)
# Output: {"fps", "frames", "items": [[track, name, type, start, end, left_offset], ...], "markers": {frame: {...}}}
import json

_tls = {project.GetTimelineByIndex(i + 1).GetName(): project.GetTimelineByIndex(i + 1)
        for i in range(project.GetTimelineCount())}
_tl = _tls[ARGS["timeline"]]
_base = _tl.GetStartFrame()
_items = []
for _k in range(1, _tl.GetTrackCount("video") + 1):
    for _it in _tl.GetItemListInTrack("video", _k) or []:
        _items.append([_k, _it.GetName(), _it.GetType(), _it.GetStart() - _base, _it.GetEnd() - _base, _it.GetLeftOffset()])
_out = {"timeline": ARGS["timeline"], "fps": float(_tl.GetSetting("timelineFrameRate")),
        "frames": _tl.GetEndFrame() - _base, "items": _items,
        "markers": {str(int(f)): m for f, m in (_tl.GetMarkers() or {}).items()}}
with open(ARGS["out"], "w", encoding="utf-8") as _fh:
    json.dump(_out, _fh, ensure_ascii=False, indent=1)
result = {"items": len(_items), "frames": _out["frames"], "out": ARGS["out"]}
