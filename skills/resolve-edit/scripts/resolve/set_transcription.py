# Run inside Resolve via the MCP tool run_script_unsafe:
#   ARGS = {...}; exec(open(r"<skill>/scripts/resolve/set_transcription.py", encoding="utf-8").read())
# Globals provided by the MCP: resolve, project. Sets `result`.
#
# Puts the Scribe transcript in Resolve: one transcription per rush of the "Rushes" bin, from the file written by
# split_transcript.py (frames of each rush, frame 0 = first frame). Adds each clip's Start TC, calls
# MediaPoolItem.SetTranscription (Resolve Studio 21.1.2 or later), then reads it back with GetTranscription and
# compares words, texts and timecodes. Nothing to pay, nothing sent anywhere.
#
# ARGS:
#   transcription     path of the file written by split_transcript.py
#   overwrite         default False: a rush that already has a transcription is left as it is (listed in "kept");
#                     True replaces it
#   only              optional list of rush names (or short names) to set, e.g. for a first try on one rush
#
# Clips are found by file path (rushes_dir + file) when the file has them, else by clip name.
# Drop-frame timecode (29.97 / 59.94 with ";") is refused: never tested.
import json
import os

_A = dict({"overwrite": False, "only": None}, **ARGS)
with open(_A["transcription"], encoding="utf-8") as _fh:
    _T = json.load(_fh)


def _norm(p):
    return os.path.normcase(os.path.normpath(p))


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


if "Studio" not in resolve.GetProductName():
    raise Exception("SetTranscription needs DaVinci Resolve Studio (this is %s)" % resolve.GetProductName())
_ver = resolve.GetVersion()
if tuple(_ver[:3]) < (21, 1, 2):
    raise Exception("SetTranscription needs Resolve 21.1.2 or later (this is %s)" % _ver)

mp = project.GetMediaPool()
_subs = {f.GetName(): f for f in mp.GetRootFolder().GetSubFolderList()}
_clips = _all_clips(_subs["Rushes"])
_by_path = {_norm(c.GetClipProperty("File Path")): c for c in _clips}
_by_name = {}
for _c in _clips:
    _by_name.setdefault(_c.GetName(), []).append(_c)

done, kept, skipped, missing, mismatch, no_speech = [], [], [], [], [], []
for rush in _T["clips"]:
    if _A["only"] and rush["name"] not in _A["only"] and rush["short"] not in _A["only"]:
        continue
    if not rush["segments"]:
        no_speech.append(rush["short"])
        continue
    mpi = None
    if _T.get("rushes_dir"):
        mpi = _by_path.get(_norm(os.path.join(_T["rushes_dir"], rush["file"])))
    if mpi is None and len(_by_name.get(rush["name"], [])) == 1:
        mpi = _by_name[rush["name"]][0]
    if mpi is None:
        missing.append(rush["short"])
        continue
    start_tc = mpi.GetClipProperty("Start TC") or "00:00:00:00"
    fps = float(mpi.GetClipProperty("FPS") or rush["fps"])
    if ";" in start_tc:
        skipped.append([rush["short"], "drop-frame timecode " + start_tc])
        continue
    if abs(fps - float(rush["fps"])) > 0.01:
        skipped.append([rush["short"], "rate %s in Resolve, %s in the file" % (fps, rush["fps"])])
        continue
    old = mpi.GetTranscription() or {}
    if old.get("segments") and not _A["overwrite"]:
        kept.append(rush["short"])
        continue
    base = int(round(fps))
    t0 = _tc_frames(start_tc, base)
    segments = []
    for sg in rush["segments"]:
        seg = {"start": _tc(t0 + sg["start"], base), "end": _tc(t0 + sg["end"], base), "text": sg["text"],
               "words": [{"text": w["text"], "start": _tc(t0 + w["start"], base), "end": _tc(t0 + w["end"], base)}
                         for w in sg["words"]]}
        if sg.get("speaker"):
            seg["speaker"] = sg["speaker"]
        segments.append(seg)
    want = {"segments": segments}
    if _T.get("language"):
        want["language"] = _T["language"]
    if not mpi.SetTranscription(want):
        skipped.append([rush["short"], "SetTranscription returned False"])
        continue
    # Read back: same words (silences "(...)" are Resolve's own), same texts, same timecodes.
    got = [w for sg in (mpi.GetTranscription() or {}).get("segments", []) for w in sg.get("words", [])
           if w.get("text", "").strip() != "(...)"]
    sent = [w for sg in segments for w in sg["words"]]
    diffs = []
    if len(got) != len(sent):
        diffs.append("%d words sent, %d read back" % (len(sent), len(got)))
    for a, b in zip(sent, got):
        if a["text"].strip() != b.get("text", "").strip():
            diffs.append("text %r -> %r" % (a["text"], b.get("text")))
        elif (a["start"], a["end"]) != (b.get("start"), b.get("end")):
            diffs.append("%s %s-%s -> %s-%s" % (a["text"].strip(), a["start"], a["end"], b.get("start"), b.get("end")))
        if len(diffs) >= 5:
            break
    if diffs:
        mismatch.append([rush["short"], diffs])
    done.append([rush["short"], len(sent), start_tc])

resolve.GetProjectManager().SaveProject()
result = {"set": len(done), "words": sum(d[1] for d in done), "kept_existing": kept, "skipped": skipped,
          "not_found": missing, "no_speech": no_speech, "readback_mismatch": mismatch, "rushes": done}
