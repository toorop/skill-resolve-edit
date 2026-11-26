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

For each video the user creates a folder, puts the camera files in a rushes sub-folder (usually `rushes/`, any
name and any case; if there is no obvious one, ask), and opens Claude IN the video folder. Inside the rushes folder
the layout is free: everything together, one sub-folder per camera, per day... every sub-folder is searched.
Everything you produce goes in it. Your auto-memory is per folder, so a new video starts with EMPTY memory:
this skill, its references and the channel profile are the only carried-over knowledge (keep them up to date,
see Step 9).

```
<video folder>/            (= working directory; the profile pointer is here or in a parent folder)
  rushes/                  camera files, any cameras, any sub-folders (sidecars and proxies are skipped)
  audio/                   reference audio export + 16 kHz parts for transcription
  transcripts/             rushes.json (inventory), clips.json, transcript.json (merged), transcript_lisible.txt, flags.txt,
                           resolve_transcription.json (per rush, for Resolve)
  edl/                     plans (linear_vN.json, montage_vN.json), final_dump.json
  publication/             youtube.md (copy-paste package)
  history/                 what you proposed and what the user validated (history.py), FINAL changes, meta.json
  decisions.json           per-video decisions (start from the profile's example, else templates/decisions.example.json)
```

## Workflow

### Keeping the history (every video)
What you propose and what the user decides is kept in `history/` (the future data set to compare models; it never
changes the edit). Run from the video folder, `--model` = your model id:
`python SKILL/scripts/history.py save <kind> <file> --model <id>`. Save each proposal EXACTLY as presented, BEFORE
the user answers; write the file in the scratchpad or `history/` first. Kinds: `derushage_proposal` (Step 4: the
report .md, and a .json in the decisions.json format with a `reason` per removal), `decisions_linear` and
`decisions_montage` (decisions.json at each build), `montage_proposal` (Step 6: .md table + .json),
`publication_proposal` (Step 8: the youtube.md as first proposed), `published` (Step 9).


### Looking at images (any step)
All images come from Resolve: `resolve/export_frames.py` renders labelled contact sheets (20 frames ≈ 2 s) or
single frames, from a timeline (what it shows: grade, titles, sizing) or from a rush (its ungraded source).
Frames are given as frame numbers from the timeline start or as `{"tc": "HH:MM:SS:FF", "label": ...}`. The skill
never touches colour: ungraded log / HLG footage is flat but readable, enough to see what happens. Look at one
small sheet at a time; never sweep every rush by default.

### Step 0 — Check the setup and load the profile
- Find and read the channel profile: `profile.md` entirely, then the files it says to read at this step.
- `get_resolve_status` on the Resolve MCP; confirm the open project with the user.
- `python SKILL/scripts/check_setup.py` (from the video folder): Python, ffmpeg / ffprobe and the features the
  scripts need, the fal.ai key (presence and length only), HTTPS access to fal.ai, the profile.
  For each missing tool it prints the install command for this system (winget / brew / apt): give it to the user
  and ask them to install it, then to restart Claude Code (a running session does not see a new PATH). If `python`
  itself is missing, the same commands are in the README. If the key is missing, ask the user to run
  `python SKILL/scripts/fal_key.py set` THEMSELVES in a terminal (hidden input, stored in the Windows Credential
  Manager; other systems: the `FAL_KEY` environment variable). Never ask for the key in chat.
- On macOS or Linux, tell the user the skill is tested on Windows only, and report what breaks.
- Ask (one by one): video type (from the profile's video types), rushes to exclude, anything special.
- If several cameras were used (or the rushes folder suggests it), ask whether their clocks were right: the
  reference is sorted by recording time. A camera with a wrong clock gets a `clock_offset` in the profile.

### Step 1 — Inventory, import and reference timeline
1. `python SKILL/scripts/probe_rushes.py <rushes folder> transcripts/rushes.json` reads every video file of the
   folder and its sub-folders with ffprobe, recognises each camera (profile `cameras`, else its metadata), gives
   short names, sorts by recording time and proposes the reference format. Show the user its table (local
   recording time, camera, short name, format, length) and its warnings, and get the order validated. Watch for:
   rushes of two cameras that overlap in time (simultaneous filming: multicam is not handled yet, ask which to
   keep), a camera whose times look shifted (wrong clock: `clock_offset`), files without a recording time, variable
   frame rate (phones), vertical rushes, unknown cameras (offer to add them to the profile's `cameras`).
2. **Reference format** = the lowest common one, as proposed by the inventory: the smallest rate that divides all
   the others (25p for 25p + 50p) and the smallest frame size (the reference only serves the transcript and the
   scene index). If the rates have no common divisor (24/25/30), ask. **The rate chosen here stays the rate of
   every timeline of the video** (plans count reference frames); the size can change for the montage (Step 7).
3. `resolve/import_reference.py` with `rushes_json = transcripts/rushes.json`, `exclude` (short names),
   `clips_out = transcripts/clips.json` (and `fps`/`width`/`height` if the user changed the proposal).
   Check: no gaps, no `rush_length_mismatch`, timeline format == the validated one, start TC 00:00:00:00. Never
   touch color nor audio processing (done by the user unless the profile says otherwise). Each rush keeps its own
   rate: Resolve plays a 50p rush at real speed in a 25p timeline, nothing is re-encoded.

### Step 2 — Audio export
`resolve/render_audio.py` (`target_dir = audio`, FLAC 16-bit). A full 35 min export takes ~40 s. If still
rendering, call again with `{"job": <id>}`. If stuck at 0%: Resolve's audio output device is probably missing or
frozen (`references/resolve.md`); give the user the fix from the profile's workstation traps if it names the device,
else the generic one. Do not ask about sound beforehand. Verify duration == reference.

### Step 3 — Transcription (costs ~0.008 $/min — tell the user the estimate before starting)
```
python SKILL/scripts/prepare_audio.py audio/00_REFERENCE_audio.flac transcripts/clips.json audio/parts
python SKILL/scripts/transcribe_fal.py audio/parts/manifest.json transcripts/transcript.json
python SKILL/scripts/readable_transcript.py transcripts/transcript.json transcripts/clips.json transcripts/transcript_lisible.txt
python SKILL/scripts/flag_passages.py transcripts/transcript.json transcripts/clips.json > transcripts/flags.txt
```
Language and keyterms come from the profile (`--language`, `--keyterm` override). Parts are split at rush
boundaries under 20 min (fal limit). Details: `references/transcription.md`.

**Then, with Resolve Studio 21.1.2 or later (free, no external service): put the transcript in Resolve**, one
transcription per rush, so the user can search, read and edit by text in Resolve without transcribing again:
```
python SKILL/scripts/split_transcript.py transcripts/transcript.json transcripts/clips.json transcripts/resolve_transcription.json
```
then `resolve/set_transcription.py` with `transcription = <video folder>\transcripts\resolve_transcription.json`.
It reads every rush back and lists any difference (`readback_mismatch` must be empty). A rush that already has a
transcription is kept unless `overwrite: True` (ask the user). With the free Resolve, skip this step. When
reporting it, say plainly that **Resolve transcribed nothing**: the Scribe transcript was copied into Resolve, cut
by rush (no second transcription, no cost), and the readback matches. Tell the user how to see it: Media Pool,
right-click a rush > AI Tools > Audio Transcription > Transcribe (on a transcribed clip it only opens the
Transcription window).

### Step 4 — Dérushage report (read `transcript_lisible.txt` + `flags.txt`)
Present, with reference timecodes: failed takes and retakes, off-topic passages (passers-by, cameraman),
false starts, topics explained twice, passages the profile's editorial policy asks to flag, repeated
interjections, and the list of sequences (one per object/topic). Then ask the user, ONE question at a time, what
to remove. Silent visual moments (arrivals, demonstrations) are invisible in the transcript: when in doubt,
look at a small contact sheet of the reference at those timecodes (`resolve/export_frames.py`, below), or ask.
**Bloopers are not a default** (few channels make them): if the rushes hold genuinely funny moments (an incident,
a slip of the tongue, a fit of laughter) and the profile does not rule them out, ask ONCE, at the end of the
report, whether the user wants a bloopers section, and list the candidates only if they say yes. Otherwise do not
mention bloopers, unless the user asks for them.
Before the first question, save the report: `history.py save derushage_proposal` with the .md as shown and the
.json of the proposed removals (`{"linear": {"remove": [{"label", "start", "end", "reason"}]}}`).
Record validated removals in `decisions.json` → `linear.remove`.

### Step 5 — Linear cut
`python SKILL/scripts/build_linear_edl.py decisions.json transcripts/transcript.json transcripts/clips.json edl/linear_v1.json`
then `resolve/build_timeline.py` with `plan = edl/linear_v1.json`, `name = "01 - LINEAIRE v1"`, and
`history.py save decisions_linear decisions.json` (each version). Then check the cuts by eye: `resolve/export_frames.py` with `timeline = "01 - LINEAIRE v1"`, `mode = "cuts"`,
`out_dir = <video folder>\edl\cuts_linear_v1`, `clips_json = <video folder>\transcripts\clips.json` → sheets of the
last frame before / first frame after every cut, labelled with the rush short names. Look at them and REPORT what
looks wrong (black or blurred frame, badly framed presenter at a rush head, camera still moving): never remove
anything because of an image, and never because a passage has no speech.
Report pieces, duration, what was removed, what the cut sheets show, and the markers legend. The user
spot-checks via markers (Shift+Up/Down). Corrections → update `decisions.json` → new version (never edit a built timeline).
Rules and thresholds: `references/editing-method.md` + the profile's style and `settings.json` → `linear`.

### Step 6 — Montage proposal (propose BEFORE building; the user will watch it entirely)
From the sequences, propose an order following `references/editing-method.md` and the profile's style (hook
early, alternate topics, reconnect material shot at different times, the presenter's own structural phrases at
the right place, crescendo to the best pieces, outro last; bloopers after a title card only if the user asked for
them at Step 4). Watch for sentences
that continue across rushes (keep those rushes adjacent). Respect the video type (some keep the shooting order).
Present it as a table with approximate durations and save it (`history.py save montage_proposal`, the .md table
and a .json `{"montage": {"sequences": [...], "bloopers": [...]}}`) before the user answers; validate; write
`decisions.json` → `montage.sequences` / `bloopers`.

### Step 7 — Build the montage
Before building, propose the montage timeline format: same rate as the reference (always); size by default the
largest size of the rushes used (e.g. UHD), or what the user prefers. Pass `width`/`height` to
`build_timeline.py` when it differs from the reference.
`build_montage.py` → `resolve/build_timeline.py` (`name = "02 - MONTAGE v1"`), then
`history.py save decisions_montage decisions.json`. It adds the title card,
bloopers, audio cross fades (4 frames), YouTube loudness normalization (relative) and markers, and verifies
everything. Check its cuts the same way (`mode = "cuts"`, `out_dir = <video folder>\edl\cuts_montage_v1`, same
`clips_json`). Then offer to duplicate it as `"03 - FINAL"` (`timeline.DuplicateTimeline`) for the user's manual
pass, and remind them of their audio finishing chain if the profile documents one.

### Step 8 — Publication package
After the user's manual pass: `resolve/dump_timeline.py` on "03 - FINAL" → `chapters.py` (works on all tracks,
ignores bloopers) → write `publication/youtube.md` per `references/publication.md` and the profile's publication
rules: title proposals, thumbnail text + image candidates (`thumbnail_candidates.py` then
`resolve/export_frames.py` on "03 - FINAL": one contact sheet the USER looks at and picks from — don't view it
yourself), full description with rewritten chapter titles and the
profile's fixed footer, tags. Save the package as first proposed: `history.py save publication_proposal
publication/youtube.md`.

### Step 9 — Lessons learned and video note (end of every video)
- What changed by hand, from facts: `python SKILL/scripts/final_changes.py edl/montage_v1.json edl/final_dump.json
  history/09_final_changes --clips transcripts/clips.json` (the montage plan actually built vs the FINAL dumped at
  Step 8: passages removed or added, sequences moved, shots on V2, other items). Show it and ask the user only WHY.
- Ask what was really published (title, thumbnail text, link) and save it: `history.py save published <file>`.
  Then `python SKILL/scripts/history.py compare` → `history/comparison.md` (your proposals vs the validated
  decisions); mention what the user changed most, it feeds the lessons.
- **Channel lessons** (style, editorial line, video type, publication) → update the profile's files.
- **Generic lessons** (Resolve API, scripts, method): **only if `profile.md` says the user develops this skill**
  (a "skill development" section naming its source repo) → that repo, as `profile.md` says. Otherwise never
  propose improvements to the skill itself: the user edits videos, not the skill.
- If `profile.md` names a notes folder, write the video note there (format in `references/profile.md`): what
  was published, what was changed by hand and why, lessons, and the small files worth archiving (`decisions.json`,
  `history/`, `publication/`) — the work drive is often wiped once a video is out.

## References
- `references/profile.md` — channel profile format, settings keys, per-video note, how to create a profile
- `references/editing-method.md` — when to cut, linear cut mechanics, montage principles, markers, audio finishing
- `references/transcription.md` — fal.ai / Scribe v2 facts and pitfalls
- `references/resolve.md` — Resolve API facts, traps, verified recipes
- `references/publication.md` — YouTube package structure and thumbnail search
