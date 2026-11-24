---
name: resolve-edit
description: Edit a YouTube video in DaVinci Resolve through the Resolve MCP, following a channel profile (editing style, editorial policy, video types, publication format) — from raw rushes to a reference timeline, word-level transcript (ElevenLabs Scribe v2 via fal.ai), dérushage report, linear cut, re-ordered montage (bloopers, audio cross fades, YouTube loudness), and the YouTube publication package (titles, thumbnail text and image candidates, description with chapters, tags). Use whenever the user wants to start a new video ("nouvelle vidéo", "on attaque une nouvelle vidéo YouTube", "j'ai mis les rushs"), edit / monter / dérusher a video in Resolve, transcribe its audio, prepare its YouTube upload (titres, description, vignette), resume such a job, or create a channel profile for it.
---

# Resolve edit — profile-driven editing workflow

You edit YouTube videos in DaVinci Resolve through its MCP and the scripts of this skill. The user films and
does the final pass; you prepare everything up to a montage ready for their manual pass, then the publication
package. Everything that is specific to a channel (audience, style, editorial line, video types, publication
format, thresholds, keyword lists, hardware traps) lives in its **channel profile**, never in this skill.
Speak the user's language (the profile says which).

## Non-negotiable working rules

1. **One step at a time.** Never start a step without the user's explicit go-ahead. After each step, report what
   was done AND what you verified, then stop.
2. **Ask questions one at a time**, never as a list. Give a recommendation with each question.
3. **The reference timeline is never modified.** Every edit is a NEW timeline built from the rushes.
4. **Names in Resolve are ASCII only** (bins, timelines, markers): the scripting bridge double-encodes accents
   and bins cannot be renamed. Accented on-screen text goes through `build_timeline.py` (Lua escapes).
5. **Always say which timeline a timecode refers to** (reference vs. linear vs. montage). Ask the user for
   timecodes of the timeline they are watching, and map them back to the reference yourself.
6. **Never read the raw transcript JSON** (megabytes). Read the condensed `transcript_lisible.txt`; let scripts
   handle word-level precision.
7. **Never store, print or ask for the fal.ai key.** It lives in the Windows Credential Manager (`fal_key.py`).
8. **The profile's style wins.** Never apply a "fast YouTube" style by default; never add video transitions,
   color or audio processing unless the profile says so.
9. Keep a short log of decisions in the video folder (`decisions.json` is the source of truth for cuts/order).

## Paths

- `SKILL` = the folder containing this file. Scripts: `SKILL/scripts/` (Python 3, stdlib only, plus ffmpeg).
- Run local scripts with `python "SKILL/scripts/<script>.py" ...` from the video folder. They find the channel
  profile by themselves (see below); `--profile DIR` overrides.
- Resolve-side scripts run inside Resolve with the MCP tool **`run_script_unsafe`**:
  ```python
  ARGS = {...}
  exec(open(r"<SKILL>\scripts\resolve\<script>.py", encoding="utf-8").read())
  ```
  They set `result`. Each call has a 60 s limit.

## Channel profile

A folder found through a pointer file **`resolve-edit.json`** (`{"profile": "<folder>"}`, relative to the pointer)
placed in the video folder or any parent — typically the channel folder that holds all the video folders — or
through the `RESOLVE_EDIT_PROFILE` environment variable. It contains:
- **`profile.md`** — the entry point: channel, audience, presenter, language, shooting setup, workstation traps,
  where to write the per-video notes, and the list of the other files with when to read them.
- **`settings.json`** — numbers and keyword lists read by the scripts (JSON with `//` comment lines).
- the channel's own documents (style, editorial policy, video types, publication, description footer...), with
  free names, listed in `profile.md`.

Format, settings keys and how to create one: `references/profile.md`; empty profile to start from:
`templates/profile/`. If no profile is found, stop and offer to create one with the user (questions one at a time)
before Step 1 — or, if the video folder is stored outside the channel folder, ask where the profile is.

## Video working folder = the session's working directory

For each video the user creates a folder, puts the camera files in `rushes/`, and opens Claude IN that folder.
Everything you produce goes in it. Your auto-memory is per folder, so a new video starts with EMPTY memory:
this skill, its references and the channel profile are the only carried-over knowledge (keep them up to date,
see Step 9).

```
<video folder>/            (= working directory; the profile pointer is here or in a parent folder)
  rushes/                  camera files (e.g. Sony C####.MP4 + XML sidecars)
  audio/                   reference audio export + 16 kHz parts for transcription
  transcripts/             clips.json, transcript.json (merged), transcript_lisible.txt, flags.txt
  edl/                     plans (linear_vN.json, montage_vN.json), final_dump.json
  publication/             youtube.md (copy-paste package)
  decisions.json           per-video decisions (start from the profile's example, else templates/decisions.example.json)
```

## Workflow

### Step 0 — Check the setup and load the profile
- Find and read the channel profile: `profile.md` entirely, then the files it says to read at this step.
- `get_resolve_status` on the Resolve MCP; confirm the open project with the user.
- `ffmpeg -version`, and that the fal.ai key exists: `python SKILL/scripts/fal_key.py check` (prints only its
  length). If missing, ask the user to run `python SKILL/scripts/fal_key.py set` THEMSELVES in a terminal (hidden
  input, stored in the Windows Credential Manager). Never ask for the key in chat.
- Ask the user to check that **timeline playback has sound**: a missing or frozen audio output device makes every
  render hang at 0% (`references/resolve.md`; the profile may name the device and its fix).
- Ask (one by one): video type (from the profile's video types), rushes to exclude, anything special.

### Step 1 — Import and reference timeline
Read one camera sidecar (if any) for format info (resolution, fps, log profile). Then run
`resolve/import_reference.py` with `rushes_dir`, `exclude`, `clips_out = transcripts/clips.json`.
Check: frames == sum of rushes, no gaps, timeline format == rushes, start TC 00:00:00:00. Never touch color nor
audio processing (done by the user unless the profile says otherwise).

### Step 2 — Audio export
`resolve/render_audio.py` (`target_dir = audio`, FLAC 16-bit). A full 35 min export takes ~40 s. If still
rendering, call again with `{"job": <id>}`. If stuck at 0%: audio device trap (Step 0). Verify duration == reference.

### Step 3 — Transcription (costs ~0.008 $/min — tell the user the estimate before starting)
```
python SKILL/scripts/prepare_audio.py audio/00_REFERENCE_audio.flac transcripts/clips.json audio/parts
python SKILL/scripts/transcribe_fal.py audio/parts/manifest.json transcripts/transcript.json
python SKILL/scripts/readable_transcript.py transcripts/transcript.json transcripts/clips.json transcripts/transcript_lisible.txt
python SKILL/scripts/flag_passages.py transcripts/transcript.json transcripts/clips.json > transcripts/flags.txt
```
Language and keyterms come from the profile (`--language`, `--keyterm` override). Parts are split at rush
boundaries under 20 min (fal limit). Details: `references/transcription.md`.

### Step 4 — Dérushage report (read `transcript_lisible.txt` + `flags.txt`)
Present, with reference timecodes: failed takes and retakes, off-topic passages (passers-by, cameraman),
false starts, topics explained twice, passages the profile's editorial policy asks to flag, repeated
interjections, and the list of sequences (one per object/topic). Then ask the user, ONE question at a time, what
to remove. Silent visual moments (arrivals, demonstrations) are invisible in the transcript: when in doubt,
export stills (`project.ExportCurrentFrameAsStill`) and look, or ask. Record validated removals in
`decisions.json` → `linear.remove`.

### Step 5 — Linear cut
`python SKILL/scripts/build_linear_edl.py decisions.json transcripts/transcript.json transcripts/clips.json edl/linear_v1.json`
then `resolve/build_timeline.py` with `plan = edl/linear_v1.json`, `name = "01 - LINEAIRE v1"`.
Report pieces, duration, what was removed, and the markers legend. The user spot-checks via markers
(Shift+Up/Down). Corrections → update `decisions.json` → new version (never edit a built timeline).
Rules and thresholds: `references/editing-method.md` + the profile's style and `settings.json` → `linear`.

### Step 6 — Montage proposal (propose BEFORE building; the user will watch it entirely)
From the sequences, propose an order following `references/editing-method.md` and the profile's style (hook
early, alternate topics, reconnect material shot at different times, the presenter's own structural phrases at
the right place, crescendo to the best pieces, outro last, optional bloopers with a title). Watch for sentences
that continue across rushes (keep those rushes adjacent). Respect the video type (some keep the shooting order).
Present it as a table with approximate durations; validate; write `decisions.json` → `montage.sequences` /
`bloopers`.

### Step 7 — Build the montage
`build_montage.py` → `resolve/build_timeline.py` (`name = "02 - MONTAGE v1"`). It adds the title card,
bloopers, audio cross fades (4 frames), YouTube loudness normalization (relative) and markers, and verifies
everything. Then offer to duplicate it as `"03 - FINAL"` (`timeline.DuplicateTimeline`) for the user's manual
pass, and remind them of their audio finishing chain if the profile documents one.

### Step 8 — Publication package
After the user's manual pass: `resolve/dump_timeline.py` on "03 - FINAL" → `chapters.py` (works on all tracks,
ignores bloopers) → write `publication/youtube.md` per `references/publication.md` and the profile's publication
rules: title proposals, thumbnail text + image candidates (`thumbnail_candidates.py`: one contact sheet the USER
looks at and picks from — don't view it yourself), full description with rewritten chapter titles and the
profile's fixed footer, tags.

### Step 9 — Lessons learned and video note (end of every video)
- Ask the user what they changed by hand in "03 - FINAL" and why (diff it against "02 - MONTAGE" with
  dump_timeline.py).
- **Channel lessons** (style, editorial line, video type, publication) → update the profile's files.
- **Generic lessons** (Resolve API, scripts, method) → this skill's source repo, as `profile.md` says (reinstall,
  update the project status, commit and push).
- If `profile.md` names a notes folder, write the video note there (format in `references/profile.md`): what
  was published, what was changed by hand and why, lessons, and the small files worth archiving — the work drive
  is often wiped once a video is out.

## References
- `references/profile.md` — channel profile format, settings keys, per-video note, how to create a profile
- `references/editing-method.md` — when to cut, linear cut mechanics, montage principles, markers, audio finishing
- `references/transcription.md` — fal.ai / Scribe v2 facts and pitfalls
- `references/resolve.md` — Resolve API facts, traps, verified recipes
- `references/publication.md` — YouTube package structure and thumbnail search
