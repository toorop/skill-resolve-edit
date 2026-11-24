# DaVinci Resolve (21.x) via MCP — facts, traps, recipes

## MCP usage
- Two servers may exist ("DaVinci Resolve" and "DaVinci Resolve Studio"); use the one whose `get_resolve_status`
  says running.
- `run_script`: sandboxed (no filesystem). `run_script_unsafe`: filesystem allowed — needed for the resolve/*.py
  (exec pattern in SKILL.md). 60 s max per call.
- Useful: `search_scripting_api`, `get_scripting_api(types=[...])`, `get_whats_new(since=...)`.

## Hard-won facts
- **Render stuck at 0% / Resolve frozen on export** = audio output device missing/frozen (seen with a USB audio
  interface on a powered hub after a Linux dual-boot; Windows shows its endpoints as "Unknown"). Symptom also:
  silent timeline playback. Fix: unplug/replug the interface, restart Resolve. Not the disk, not the GPU, not the
  script. (Also keep the work disk from being full.)
- Audio-only render: only `LoadRenderPreset("Audio Only")` + `SetRenderSettings({... "AudioFormat": "flac"|"wav",
  "ExportVideo": False, ...})` starts; a hand-made config refused. Resolve may append "00000000" to the file name
  even with `UseUniqueFilenames: False` → rename (render_audio.py does it).
- **`AppendToTimeline` endFrame is EXCLUSIVE** (`startFrame: in, endFrame: out` gives out-in frames).
  `recordFrame` + `trackIndex` place clips at an absolute position (used after the title card).
- Timelines created by script start at 01:00:00:00 unless `SetStartTimecode("00:00:00:00")` — we always set 0 so
  timeline frame == transcript seconds × fps.
- **Accents**: strings passed through the bridge are double-encoded (é → Ã©) for bin/timeline/marker names and
  Text+ inputs. Folders can't be renamed. Use ASCII names; for Text+ use
  `comp.Execute("comp:FindTool('Template'):SetInput('StyledText', 'B\\195\\170tisier')")` (Lua decimal escapes).
  `GetInput` readback shows mojibake either way — verify visually.
- `InsertFusionTitleIntoTimeline("Text+")` inserts at the playhead on V1, 125 frames (5 s).
- `TimelineItem.AddTransition({"type": "Cross Fade +3 dB", "category": "audio", "position": "end",
  "alignment": "center", "duration": 4})`; fallback alignment "left" when there are no handles.
- `SetFades` = fade dips (NOT what the user wants at cuts).
- `Timeline.NormalizeAudioLevel(items, {"normalizationMode": "YouTube", "setLevelMode":
  resolve.NORMALIZE_AUDIO_SET_LEVEL_RELATIVE})`; modes via `GetNormalizeAudioModes()`.
- `MediaPool.MoveClips([timeline_media_pool_item], bin)` moves timelines into the "Timelines" bin.
- `Timeline.DuplicateTimeline(name)` → copy with markers/transitions/volumes.
- `project.ExportCurrentFrameAsStill(path)` (run_script_unsafe) → look at frames (title check, silent passages).
- Markers: `timeline.AddMarker(frame, color, name, note, duration)`; colors: Blue, Cyan, Green, Yellow, Red, Pink,
  Purple, Fuchsia, Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream.
- Deleting a timeline: `MediaPool.DeleteTimelines([tl])` (only your own test timelines, never user work).

## Project conventions
- Bins: `Rushes/` (used), `Rushes/Non retenus/` (excluded), `Timelines/`.
- Timelines: `00 - REFERENCE (ne pas modifier)`, `01 - LINEAIRE vN`, `02 - MONTAGE vN`, `03 - FINAL` (user's
  manual pass: never rebuild it; read it with dump_timeline.py). Test timelines: `ZZ - ...` and delete them.
- The user may move shots to V2 as overlays in FINAL (an arrival shot over the intro): tools must read all tracks.
