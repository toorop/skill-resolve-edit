# Run inside Resolve via run_script_unsafe:  ARGS = {...}; exec(open(r"<...>/render_audio.py", encoding="utf-8").read())
# Exports the audio of a whole timeline (default: the reference) as FLAC 16-bit 48 kHz.
#
# ARGS:
#   target_dir     output folder (e.g. G:\...\audio)
#   name           output file name without extension (default "00_REFERENCE_audio")
#   timeline       timeline name (default "00 - REFERENCE (ne pas modifier)")
#   wait           seconds to wait for completion in this call (default 50; the MCP call times out at 60)
#   job            (optional) poll an existing job id instead of starting a new one
#
# KNOWN TRAP: if the render stays at 0% and nothing is written, Resolve's audio output device is missing/frozen
# (e.g. a USB audio interface left in a bad state by a Linux dual-boot). Timeline playback is then silent too.
# Fix: unplug/replug the interface, restart Resolve. Do NOT keep waiting and do not cancel repeatedly (Resolve can freeze).
# Only the "Audio Only" preset + SetRenderSettings works; a hand-made audio-only config refused to start.
import os
import time

_A = dict({"name": "00_REFERENCE_audio", "timeline": "00 - REFERENCE (ne pas modifier)", "wait": 50, "job": None},
          **ARGS)

if not _A["job"]:
    tls = {project.GetTimelineByIndex(i + 1).GetName(): project.GetTimelineByIndex(i + 1)
           for i in range(project.GetTimelineCount())}
    project.SetCurrentTimeline(tls[_A["timeline"]])
    for j in project.GetRenderJobList():
        if j.get("OutputFilename", "").startswith(_A["name"]):
            project.DeleteRenderJob(j["JobId"])
    project.LoadRenderPreset("Audio Only")
    project.SetRenderSettings({"SelectAllFrames": True, "ExportVideo": False, "ExportAudio": True,
                               "AudioFormat": "flac", "AudioBitDepth": 16, "AudioSampleRate": 48000,
                               "UseUniqueFilenames": False, "TargetDir": _A["target_dir"], "CustomName": _A["name"]})
    _A["job"] = project.AddRenderJob()
    project.StartRendering([_A["job"]])

_t0 = time.time()
_hist = []
while time.time() - _t0 < _A["wait"]:
    _st = project.GetRenderJobStatus(_A["job"])
    _hist.append(_st.get("CompletionPercentage"))
    if _st.get("JobStatus") in ("Complete", "Failed", "Cancelled"):
        break
    time.sleep(2)
_st = project.GetRenderJobStatus(_A["job"])
_final = None
if _st.get("JobStatus") == "Complete":
    # Resolve may append a numeric suffix (e.g. 00000000) even with unique filenames off
    for f in os.listdir(_A["target_dir"]):
        if f.startswith(_A["name"]) and f.lower().endswith(".flac"):
            src = os.path.join(_A["target_dir"], f)
            _final = os.path.join(_A["target_dir"], _A["name"] + ".flac")
            if src != _final:
                if os.path.exists(_final):
                    os.replace(src, _final)
                else:
                    os.rename(src, _final)
            break
    project.DeleteRenderJob(_A["job"])
_warn = None
if _st.get("JobStatus") == "Rendering" and max(_hist or [0]) == 0 and time.time() - _t0 > 15:
    _warn = "Stuck at 0%: check the audio output device - see render_audio.py header."
result = {"job": _A["job"], "status": _st, "file": _final, "warning": _warn}
