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
- **Mixed rates** (measured on Studio 21.2.0.6, 2026-11-24): a 50p clip in a 25p timeline plays at real speed (each
  rush keeps its rate; project setting `timelineFrameRateMismatchBehavior` = "resolve"). `AppendToTimeline`
  `startFrame`/`endFrame` are in the CLIP's own frames (500-750 of a 50p clip = 125 timeline frames), while
  `GetLeftOffset`, `GetDuration`, `GetStart` are in TIMELINE frames (left offset 250). `GetSourceStartFrame` is in
  clip frames; `GetSourceEndFrame` is inconsistent (exclusive after an Append with endFrame, inclusive-ish for a
  whole clip): don't rely on it. Clip properties `FPS` (e.g. 50.0) and `Frames` (clip frames). build_timeline.py
  converts plan frames with each rush's rate; dump/chapters/thumbnails stay in timeline frames. Verified to the
  frame by comparing an exported still with ffmpeg frames of the rush (PSNR 48 dB at the expected time, 25 dB one
  frame off).
- **`MediaPoolItem.SetTranscription(dict)`** (Studio, 21.1.2+; measured on 21.2.0.6, 2026-11-25): the dict of
  `GetTranscription()`, `{language, segments: [{start, end, text, speaker, words: [{text, start, end}]}]}`, with
  SOURCE timecodes (clip `Start TC` + frames, e.g. Sony time of day `02:25:09:03`). Words carry a leading space
  like Resolve's own; words may share a boundary frame (Resolve's own do), never overlap. Accents go through
  correctly (no double encoding, unlike names; checked by eye in the Transcription window). Resolve adds its own
  `(...)` silence words and segments; everything else reads back exactly as sent. Clip property
  `Transcription Status` becomes "Transcribed". Unknown speakers ("Speaker 1") are enrolled. 31 rushes, 5 568 words:
  0.2 s. A timeline's transcription cannot be set (it comes from its clips); right after, a reference timeline of
  those clips still reads back empty with `GetTranscription(True)` on its media pool item. `split_transcript.py` +
  `resolve/set_transcription.py` do it from the Scribe transcript.
  For the user: there is no "Open" entry. On a clip that is already transcribed, Media Pool right-click >
  **AI Tools > Audio Transcription > Transcribe** opens the Transcription window without transcribing again
  (manual, chapter "Text Based Editing"); a transcribed clip shows a speech balloon on its thumbnail.
- Timeline format: `project.SetSetting("timelineFrameRate"/"timelineResolutionWidth"/...)` works while the project
  has no timeline; afterwards a timeline gets its own size with `tl.SetSetting("useCustomSettings", "1")` then
  `timelineResolutionWidth/Height` (verified: a 1080p montage in a UHD project).
- New in the 21.2 stubs (not used yet): `TimelineItem.SetLeftOffset/SetRightOffset` (trim), `SetPosition`,
  `Timeline.MoveItems` (move, e.g. J-cuts), `SetSpeed`, `Timeline.AutoAlignClips`, and for simultaneous cameras
  `MediaPool.AutoSyncAudio` and `MediaPool.CreateMulticamClip`. The MCP changelog stops at 21.0.4: read the stubs
  (`get_scripting_api` with `as_file`) after each Resolve update.
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
- Bins: `Rushes/` (used, all cameras together; clips are matched by file path), `Rushes/Non retenus/` (excluded),
  `Timelines/`. Two rushes with the same file name in different sub-folders are flagged by probe_rushes.py (rename
  one first: Resolve timelines identify clips by name).
- Timelines: `00 - REFERENCE (ne pas modifier)`, `01 - LINEAIRE vN`, `02 - MONTAGE vN`, `03 - FINAL` (user's
  manual pass: never rebuild it; read it with dump_timeline.py). Test timelines: `ZZ - ...` and delete them.
- The user may move shots to V2 as overlays in FINAL (an arrival shot over the intro): tools must read all tracks.
