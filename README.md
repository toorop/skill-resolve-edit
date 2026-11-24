# skill-resolve-edit

> **Work in progress.** Used for real on one YouTube channel, on Windows, with DaVinci Resolve Studio 21.2. Expect
> changes between versions, rough edges on other setups (macOS and Linux have never been tried), and French names
> inside Resolve. Feedback and issues are welcome.

A Claude skill (`resolve-edit`) that edits YouTube videos in **DaVinci Resolve Studio** through the Resolve MCP, from
the raw camera files to the YouTube publication package, following a **channel profile** (your style, your
editorial line, your video types, your cameras).

You film and you do the final pass. Claude does the tedious part in between, one step at a time, and waits for
your go-ahead after each step:

| Step | What happens | What you get |
|---|---|---|
| 0 | Setup check, channel profile loaded, a few questions (video type, rushes to leave out) | |
| 1 | Inventory of the rushes (any cameras, any folder layout), import, **reference timeline** | `00 - REFERENCE (ne pas modifier)` in Resolve |
| 2 | Audio export of the reference | `audio/00_REFERENCE_audio.flac` |
| 3 | **Word-level transcript** (ElevenLabs Scribe v2 through fal.ai, ~$0.008 per minute) | `transcripts/transcript_lisible.txt` |
| 4 | **Dérushage report**: failed takes, false starts, off-topic passages, what your editorial policy flags | your decisions, asked one at a time |
| 5 | **Linear cut**: removals applied, long silences shortened, breaths and air kept | `01 - LINEAIRE v1` + review markers |
| 6 | **Montage proposal**: the sequences re-ordered for retention, as a table | your validation |
| 7 | **Montage** built: title card and bloopers, audio cross fades, YouTube loudness, markers | `02 - MONTAGE v1`, copy `03 - FINAL` for your pass |
| 8 | **Publication package** from your FINAL: titles, thumbnail texts, a contact sheet of thumbnail candidates, description with chapters, tags | `publication/youtube.md` |
| 9 | **Lessons learned**: what you changed by hand becomes a rule (in your profile or in the skill) | updated profile |

Nothing is ever re-encoded and your rushes are never modified: Resolve reads them as they are. Every edit is a
new timeline built from the rushes; the reference timeline and your FINAL are never touched.

## Contents
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installing the tools](#installing-the-tools)
- [Installation (Windows)](#installation-windows)
- [macOS and Linux](#macos-and-linux)
- [First use: set up your channel profile](#first-use-set-up-your-channel-profile)
- [Starting a new video](#starting-a-new-video)
- [The workflow in detail](#the-workflow-in-detail)
- [Several cameras, any camera](#several-cameras-any-camera)
- [What the video folder contains](#what-the-video-folder-contains)
- [In Resolve: timelines, bins, markers](#in-resolve-timelines-bins-markers)
- [Scripts](#scripts)
- [Troubleshooting](#troubleshooting)
- [Current limits](#current-limits)
- [Repository layout](#repository-layout)
- [License](#license)

## How it works

```
 you ──talk──▶ Claude Code ──reads──▶ the skill (SKILL.md + references)   = the method, the same for everyone
                    │       ──reads──▶ your channel profile               = your taste, your rules, your cameras
                    │
                    ├── runs local Python scripts (stdlib + ffmpeg): inventory, transcript, cut plans, chapters, thumbnails
                    └── drives DaVinci Resolve Studio through its MCP server: import, timelines, audio export, markers
```

- **The skill** (this repository) holds the generic method: how to cut, how to build a montage, the Resolve API
  facts, the scripts.
- **The channel profile** (a folder of yours, outside this repository) holds everything that differs from one
  channel to another: audience, editing style, editorial policy, video types, publication format, thresholds,
  keyword lists in your language, your cameras.
- **Cut plans are files** (`decisions.json`, `edl/*.json`): every timeline can be rebuilt, compared, corrected by
  a new version. Claude never edits a built timeline by hand.

## Requirements

- **DaVinci Resolve Studio 21.1 or later** (the paid version: the MCP server and external scripting are Studio
  only), with its MCP server connected to Claude. Tested on 21.2.
- **Claude Code** (desktop app or CLI).
- **Python 3.8 or later** (standard library only: nothing to `pip install`).
- **ffmpeg and ffprobe** in the PATH, a full build (the scripts use the soxr resampler and the lut3d, drawtext and
  tile filters).
- A **fal.ai** account and API key (pay per use, about $0.008 per audio minute for the transcript).
- **Windows 10 or 11**: the only system the skill has been tested on so far (see [macOS and Linux](#macos-and-linux)).
- **Camera clocks set right** when you film with several cameras: the reference timeline is sorted by recording
  time (a wrong clock can be compensated in the profile, see [Several cameras](#several-cameras-any-camera)).

## Installing the tools

On Windows, in a terminal (PowerShell or Command Prompt), with `winget` (built into Windows 10 and 11):
```bat
winget install Python.Python.3.13
winget install Gyan.FFmpeg
winget install Git.Git
```
`Gyan.FFmpeg` is the full build (soxr, lut3d, drawtext included). **Close and reopen the terminal and Claude Code
afterwards**: programs already running don't see the new PATH. Check with `python --version` and `ffmpeg -version`.

| | Windows | macOS ([Homebrew](https://brew.sh)) | Linux (Debian / Ubuntu) |
|---|---|---|---|
| Python 3 | `winget install Python.Python.3.13` | `brew install python` | `sudo apt install python3` |
| ffmpeg + ffprobe | `winget install Gyan.FFmpeg` | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| git | `winget install Git.Git` | `brew install git` | `sudo apt install git` |

Then check the whole setup, from a video folder (or anywhere, with `--profile`):
```bat
python skills\resolve-edit\scripts\check_setup.py
```
It checks Python, ffmpeg and ffprobe and their needed features, the fal.ai key (only whether it is there and its
length), HTTPS access to fal.ai, the channel profile and its LUT files, and prints the install command of anything
missing for your system. Claude runs it at Step 0 of every video. DaVinci Resolve is checked by Claude through
the MCP.

## Installation (Windows)

```bat
git clone https://github.com/toorop/skill-resolve-edit.git
cd skill-resolve-edit
powershell -ExecutionPolicy Bypass -File install.ps1
```
`install.ps1` mirrors `skills/resolve-edit` into `%USERPROFILE%\.claude\skills\resolve-edit` (a copy rather than a
link, so it also works when that folder lives in WSL). **Run it again after every change or `git pull`.** The
repository also has a plugin manifest (`.claude-plugin/plugin.json`).

### fal.ai key
Never in this repository, in a file or in a global environment variable. Store it yourself, in a terminal:
```bat
python skills\resolve-edit\scripts\fal_key.py set
```
Masked input (one `*` per character, Ctrl+V pastes) or `set --clipboard`; the clipboard is cleared afterwards.
The key goes to the Windows Credential Manager (entry `resolve-edit/fal`). `fal_key.py check` shows only its
length, `fal_key.py delete` removes it. The `FAL_KEY` environment variable is accepted as a fallback (e.g. on
another OS). Claude never sees, asks for or prints the key.

## macOS and Linux

**Only tested on Windows so far.** Most of the skill is portable (Python standard library, ffmpeg, the Resolve
MCP, which DaVinci Resolve Studio has on all three systems), but expect rough edges:
- **Installing**: there is no installer script. Copy or link the skill folder:
  `ln -s "$PWD/skills/resolve-edit" ~/.claude/skills/resolve-edit` (a link: no need to reinstall after `git pull`).
- **fal.ai key**: the Windows Credential Manager does not exist there. Set `FAL_KEY` in the environment of the
  terminal that starts Claude Code (`fal_key.py check` then finds it). Keep it out of shared shell files if you
  can, e.g. load it from your system keychain in that terminal only.
- **Contact sheet font**: Arial (macOS) or DejaVu Sans / Liberation Sans (Linux) are found automatically; else set
  `thumbnail.font` in the profile.
- **Paths in the profile** (viewing LUTs) are per computer: point them to your Resolve LUT folder (macOS:
  `/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT/`; Linux: `/opt/resolve/LUT/`).
- Please report what breaks (issues welcome).

## First use: set up your channel profile

Everything that is yours lives in a profile folder, found through a small pointer file `resolve-edit.json` placed
in the channel folder that holds all your video folders:

```
<channel folder>/                e.g. D:\MyChannel\
  resolve-edit.json              {"profile": "profile"}   (path relative to this file; absolute paths work too)
  profile/
    profile.md                   entry point: channel, audience, presenter, language, shooting setup, workstation
                                 traps, where to write per-video notes, and the list of the other files
    settings.json                numbers, keyword lists and cameras read by the scripts (JSON with // comments)
    editing-style.md             ...and your other documents (free names, listed in profile.md):
    editorial-policy.md          editorial line, video types, publication rules, description footer...
    video-types.md
    publication.md
    footer.md
  12 - some video/               one folder per video
    rushes/
  13 - another video/
    rushes/
```

You never tell the skill where the profile is: Claude and the scripts look for `resolve-edit.json` in the video
folder, then in each parent folder. For a video folder stored elsewhere, give the profile path in your first
message (scripts: `--profile DIR` or the `RESOLVE_EDIT_PROFILE` environment variable). Without a profile, the skill
stops at Step 0 and offers to create one with you: it never edits without your rules.

Create the profile either way:
- **with Claude** (recommended): open Claude Code in the channel folder and type
  `/resolve-edit Create a channel profile for my channel.` Claude asks its questions one at a time (channel and
  audience, what makes the channel work, editorial line, video types, shooting setup and cameras, publication) and
  writes the files in your language;
- **by hand**: copy [`skills/resolve-edit/templates/profile/`](skills/resolve-edit/templates/profile/) into the
  channel folder as `profile\`, move its `resolve-edit.json` up into the channel folder, and fill in the `<...>`
  placeholders. Write the keyword lists of `settings.json` in your channel's language and describe your cameras.

Write the profile in your own language: it is your document, you will reread and correct it. The keys of
`settings.json` stay in English (the scripts read them). All keys:
[`skills/resolve-edit/references/profile.md`](skills/resolve-edit/references/profile.md). The profile gets better
after each video (Step 9).

## Starting a new video

1. Create the video folder inside the channel folder and copy the camera files into a sub-folder named `rushes`
   (any case). Inside it, organise as you like: everything together, one folder per camera, one per day...
   Sidecar files (`.XML`, `.LRF` proxies, backup `.WAV`, thumbnails) can stay: only video files are read.
2. Open Resolve Studio and create or open the video's project. Check that timeline playback has sound (a frozen
   audio device makes every render hang at 0%).
3. Open Claude Code **in the video folder** (the one that contains `rushes`) and type, for example:
   ```
   /resolve-edit New video: the rushes are in rushes/, the Resolve project is open.
   ```
4. Answer the questions (one at a time) and give your go-ahead at each step. You can stop at any step and resume
   later: everything is in the video folder.

## The workflow in detail

**Step 0 — Setup.** Claude reads your profile, checks Resolve, ffmpeg and the fal.ai key, and asks the video type,
the rushes to leave out, and, if several cameras were used, whether their clocks were right.

**Step 1 — Inventory and reference timeline.** `probe_rushes.py` reads every video file of the rushes folder and
its sub-folders, recognises the camera of each one, gives it a short name and sorts everything by recording time.
Claude shows you the table and its warnings and proposes the reference format: the **lowest common** one (25p for
25p + 50p rushes, the smallest frame size), because the reference only serves the transcript and the scene index.
The rate you validate here stays the rate of every timeline of the video. Then the rushes are imported into
Resolve and laid end to end in `00 - REFERENCE (ne pas modifier)`, timecode starting at 00:00:00:00.

**Step 2 — Audio export** of the whole reference (FLAC, about 40 s for 35 min).

**Step 3 — Transcript.** The audio is converted to 16 kHz mono, split at rush boundaries if longer than 19 min,
sent to Scribe v2 (language and names to spell from your profile), and merged into one word-level transcript
aligned on the reference. Claude reads only the condensed `transcript_lisible.txt` (one sentence per line, with
reference timecodes, grouped by rush), plus `flags.txt` (keyword pre-scan from your profile: divisive topics,
swearing, repeated interjections, retakes).

**Step 4 — Dérushage report.** Failed takes and retakes, off-topic passages, false starts, topics explained twice,
passages your editorial policy flags, and the list of sequences (one per object or topic). Claude asks you, one
question at a time, what to remove, and records your decisions in `decisions.json`.

**Step 5 — Linear cut** (`01 - LINEAIRE v1`), shooting order kept: validated removals, silences longer than 2 s
shortened to about 1 s (unless the words before announce a silent demonstration), rush heads and tails trimmed
around the speech, isolated slivers dropped. Thresholds in your profile. You spot-check with the markers
(Shift+Up/Down in Resolve). Corrections go into `decisions.json` and give `v2`, never a hand-edited timeline.

**Step 6 — Montage proposal.** The sequences re-ordered for retention (stake stated early, alternate topics,
reconnect material shot at different times, best pieces towards the end, outro last), following your profile's
style and video type, as a table with durations. Nothing is built before you validate it.

**Step 7 — Montage** (`02 - MONTAGE v1`). Claude proposes its format first (same rate as the reference; the size
can be larger, e.g. UHD). Built from the clean linear material: title card and bloopers at the end if you want
them, 4-frame audio cross fades at every cut, YouTube loudness normalisation (one relative gain), review markers,
then a full verification (every piece: right rush, right source frame, video and audio aligned, no gap). Claude
then offers to duplicate it as `03 - FINAL` for your manual pass.

**Step 8 — Publication package**, from the real state of your FINAL (your manual changes included): title
proposals, thumbnail texts, a contact sheet of ~20 thumbnail candidates for you to pick from (frames where the
presenter shows something, through each camera's viewing LUT), full-size exports of your picks, description with
YouTube chapters (first at 00:00, at least 3, at least 10 s each) and your fixed footer, tags. All in
`publication/youtube.md`, ready to copy and paste.

**Step 9 — Lessons learned.** Claude asks what you changed by hand in FINAL and why: channel lessons go into your
profile, generic lessons into the skill. If your profile names a notes folder, Claude writes a note for the video
there (the work drive is often wiped once a video is out).

## Several cameras, any camera

The skill works with any camera and any number of cameras **filming one after the other** (A-cam then B-cam, a
camera for the walk-through and another for the presentation...). Nothing about a particular camera is in the
code: what depends on a camera is in your profile.

- **Folder layout**: free. All sub-folders of `rushes` are searched; sidecars and proxies are skipped
  (`settings.json` → `rushes.ignore` for more, e.g. proxies copied with a whole memory card).
- **Order**: by recording time (the files' `creation_time`). The order of the reference matters little (it serves
  the transcript; the montage chooses its own order), but a wrong clock would scatter the scenes: Step 0 asks,
  Step 1 shows the table with local times, and `clock_offset` corrects a camera whose clock is wrong (e.g. a camera
  that ignores daylight saving time).
- **Mixed frame rates**: each rush keeps its own rate. Resolve plays a 50p rush at real speed in a 25p timeline;
  the scripts convert their frame numbers with each rush's rate. Nothing is re-encoded (verified to the frame
  with 25p + 50p). Fractional rates (23.976, 29.97 non-drop) are counted on their nominal rate like Resolve's
  timecode, but have not been tested in Resolve yet.
- **Mixed sizes, codecs, file names**: the reference uses the smallest size; the montage can be larger. File names
  only need to be unique.
- **Short names** (used in reports and in `decisions.json`): from a pattern per camera in your profile (e.g.
  `C0522` for a Sony, `DJI0030` for a DJI), else the file name without extension.
- **Viewing LUT per camera** for the thumbnail contact sheet (e.g. S-Log3 → Rec.709, HLG → Rec.709). Grading
  remains yours: the skill never touches color in Resolve.
- **Sound**: always the sound inside the video files. Separate audio files are never imported (e.g. the backup
  `.WAV` an action camera writes next to each clip).
- **Unknown camera**: it still works (named after its metadata, file-name short names, no LUT); Claude offers to
  add it to your profile.

Describe each camera in `settings.json`:
```jsonc
"cameras": [
  {
    "name": "Sony A6700",
    "match": "XAVC",                         // regex searched in the file path and metadata (encoder, make, model...)
    "short_name": "C\\d{4}",                 // groups joined, else the whole match -> C0522
    "lut": "C:\\ProgramData\\Blackmagic Design\\DaVinci Resolve\\Support\\LUT\\Sony\\SLog3SGamut3.CineToLC-709.cube",
    "clock_offset": 0                         // seconds added to its recording times
  },
  {
    "name": "DJI Osmo Action 5 Pro",
    "match": "DJI ?Osmo ?Action ?5",
    "short_name": "(DJI)_\\d{14}_(\\d{4})",  // DJI_20261109153839_0030_D.MP4 -> DJI0030
    "lut": "C:\\ProgramData\\Blackmagic Design\\DaVinci Resolve\\Support\\LUT\\DJI\\DLOG_LUTs\\HLG_to_REC709.cube",
    "clock_offset": 0
  }
]
```
The `signature` field of `transcripts/rushes.json` shows the metadata each file was recognised by.

**Not yet**: cameras filming **at the same time** (multicam, synchronised by sound or timecode). The inventory
detects overlapping recordings and warns; you then keep one camera for that passage. The design leaves room for it
(Resolve 21.2 has `AutoSyncAudio` and `CreateMulticamClip`).

## What the video folder contains

```
<video folder>/
  rushes/                      your camera files (never modified)
  audio/                       00_REFERENCE_audio.flac + parts/ (16 kHz WAV sent for transcription, manifest.json)
  transcripts/
    rushes.json                inventory: every rush, its camera, format, recording time; the proposed format
    clips.json                 map of the reference: where each rush starts and ends, its rate, camera, file
    transcript.json            word-level transcript on the reference timeline (large: Claude never reads it)
    transcript_lisible.txt     readable transcript (one sentence per line, reference timecodes)
    flags.txt                  keyword pre-scan for the dérushage report
  decisions.json               YOUR decisions: removals, exceptions, montage sequences, bloopers (source of truth)
  edl/                         plans: linear_vN.json, montage_vN.json; final_dump.json (state of your FINAL)
  publication/
    youtube.md                 the copy-paste package
    vignettes/                 contact sheet, candidates.json, full-size exports
```
Example of `decisions.json`: [`templates/decisions.example.json`](skills/resolve-edit/templates/decisions.example.json).
Times are reference-timeline seconds or `HH:MM:SS:FF` timecodes.

## In Resolve: timelines, bins, markers

- Bins: `Rushes` (all cameras together), `Rushes/Non retenus` (rushes left out), `Timelines`.
- Timelines: `00 - REFERENCE (ne pas modifier)` (never modified), `01 - LINEAIRE vN`, `02 - MONTAGE vN`,
  `03 - FINAL` (your manual pass: never rebuilt, only read).
- Markers: **Purple** = sequence start (= YouTube chapters) · **Red** = passage removed · **Blue** = long silence
  shortened · **Green** = long silence kept (demonstration?) · **Cyan** = material shot elsewhere joined here ·
  **Pink** = title card and bloopers. Plain rush junctions are not marked.
- Names in Resolve are ASCII only (the scripting bridge garbles accents); accented on-screen text such as the
  bloopers title is handled.

## Scripts

Local scripts (`skills/resolve-edit/scripts/`, Python stdlib + ffmpeg; they find the profile themselves,
`--profile DIR` overrides):

| Script | Does |
|---|---|
| `check_setup.py` | Step 0: tools, ffmpeg features, fal.ai key, network, profile; install commands for what is missing |
| `probe_rushes.py RUSHES OUT.json` | inventory of all rushes (sub-folders included), cameras, order, proposed format, warnings |
| `prepare_audio.py AUDIO CLIPS OUT_DIR` | 16 kHz mono WAV, split at rush boundaries under the fal.ai limit |
| `transcribe_fal.py MANIFEST OUT.json` | Scribe v2 on fal.ai, parts merged on the reference timeline |
| `readable_transcript.py TRANSCRIPT CLIPS OUT.txt` | condensed transcript to read |
| `flag_passages.py TRANSCRIPT CLIPS` | keyword pre-scan (profile `flags`) |
| `build_linear_edl.py DECISIONS TRANSCRIPT CLIPS OUT.json` | linear cut plan |
| `build_montage.py DECISIONS TRANSCRIPT CLIPS OUT.json` | montage plan (sequences, title, bloopers, markers) |
| `chapters.py MONTAGE_PLAN FINAL_DUMP` | YouTube chapters from your FINAL |
| `thumbnail_candidates.py TRANSCRIPT CLIPS FINAL_DUMP RUSHES OUT_DIR` | contact sheet of thumbnail candidates; `--export 1,7` full size |
| `fal_key.py set / check / delete` | the fal.ai key in the Windows Credential Manager |

Resolve-side scripts (`scripts/resolve/`), run by Claude through the MCP tool `run_script_unsafe`
(`ARGS = {...}; exec(open(...).read())`, 60 s per call): `import_reference.py`, `render_audio.py`,
`build_timeline.py` (also `width`/`height` for a montage in another size), `dump_timeline.py`.

## Troubleshooting

- **`ffmpeg` or `python` not found although installed**: the terminal or Claude Code was open during the
  install. Close and reopen them. `check_setup.py` tells what is missing and how to install it.
- **Render stuck at 0 %, silent playback**: Resolve's audio output device is missing or frozen (e.g. a USB audio
  interface after a Linux dual boot). Unplug and replug it, restart Resolve. Not the disk, not the GPU.
- **`CERTIFICATE_VERIFY_FAILED` during the transcript**: Windows installs some root certificates only when a
  Windows program first needs them, and Python cannot trigger that. `transcribe_fal.py` now does it by itself
  (one request through `curl.exe`) and retries; if it still fails, open `https://v3.fal.media` once in a browser.
- **"N files are named X"**: two rushes with the same file name in different sub-folders. Rename one: Resolve
  identifies clips by name in timelines.
- **Rushes of two cameras overlap**: they filmed at the same time (not handled yet) or a clock is wrong. Check the
  table; fix a wrong clock with `clock_offset`.
- **A camera is not recognised**: look at the `signature` of one of its files in `transcripts/rushes.json` and add
  a `match` for it in the profile's `cameras`.
- **After a Resolve update**: the MCP changelog may lag; Claude reads the installed API stubs.

## Current limits

- **Cameras filming at the same time** (multicam) are not handled yet: one camera at a time.
- **Tested on Windows only**: macOS and Linux should mostly work but have never been tried (see
  [macOS and Linux](#macos-and-linux)).
- **Resolve names and review markers are in French**: timelines `00 - REFERENCE (ne pas modifier)`,
  `01 - LINEAIRE vN`, `02 - MONTAGE vN`, `03 - FINAL`, bin `Rushes/Non retenus`, markers "Passage retire",
  "Blanc raccourci", "Raccord deplace"... They work in any language but read oddly elsewhere.
- **Drop-frame timecode** (29.97 DF) is not handled; non-drop fractional rates (23.976, 29.97) are written for but
  untested in Resolve.
- **J-cuts** (voice under the previous shot) are proposed but not built: you do them in your manual pass.
- **Separate audio** (a recorder's WAV) is never imported: the sound inside the video files is used.
- Tested on one channel (French, Sony + DJI cameras); the profile creation flow has not yet been run with a new
  user.

## Repository layout

```
skills/resolve-edit/
  SKILL.md            the step-by-step workflow Claude follows
  references/         profile format and keys, editing method, transcription, Resolve API facts, publication
  scripts/            local Python scripts (stdlib + ffmpeg)
  scripts/resolve/    scripts run inside Resolve through the MCP
  templates/          decisions.example.json, profile/ (empty channel profile to copy)
install.ps1           installs the skill into %USERPROFILE%\.claude\skills
LICENSE               MIT
```

## License

[MIT](LICENSE) © 2026 Stéphane Depierrepont. The channel profiles you write are yours and stay outside this
repository.
