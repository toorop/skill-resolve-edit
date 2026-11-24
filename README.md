# skill-resolve-edit

A Claude skill (`resolve-edit`) that edits YouTube videos in **DaVinci Resolve Studio** through the Resolve MCP,
from raw rushes to the YouTube publication package, following a **channel profile**.

1. Import the rushes and build a **reference timeline** (never modified)
2. Export the audio → **word-level transcript** (ElevenLabs Scribe v2 via fal.ai)
3. **Dérushage report**: failed takes, off-topic, passages the channel's editorial policy flags
4. **Linear cut** (breaths and air kept)
5. **Re-ordered montage** for retention
6. Finishing: title card, bloopers, audio cross fades, **YouTube loudness normalization**, review markers
7. A "FINAL" copy for the user's manual pass
8. **Publication package**: titles, thumbnail text, a contact sheet of thumbnail candidates, description with
   chapters, tags
9. **Lessons learned**: what the user changed by hand becomes a rule (in the profile or in the skill)

Every step waits for the user's go-ahead.

## Channel profile

Everything that differs from one channel to another (audience, style, editorial line, video types, publication
format, thresholds, keyword lists, hardware traps) lives in a profile folder outside this repo, found through a
`resolve-edit.json` pointer placed in the channel folder above the video folders:

```
<channel folder>/
  resolve-edit.json        {"profile": "profile"}
  profile/
    profile.md             entry point (read by Claude at Step 0)
    settings.json          numbers and keyword lists read by the scripts
    ...                    style, editorial policy, video types, publication, footer...
  12 - some video/         one folder per video = Claude's working directory
    rushes/
```

Format and settings keys: [`skills/resolve-edit/references/profile.md`](skills/resolve-edit/references/profile.md).

**You never tell the skill where the profile is**: Claude and the scripts look for `resolve-edit.json` in the
video folder, then in each parent folder, so any video folder placed inside the channel folder finds it. For a
video folder stored elsewhere, give the profile path in your first message (scripts: `--profile DIR` or the
`RESOLVE_EDIT_PROFILE` environment variable). Without a profile, the skill stops at Step 0 and offers to create
one with you: it never edits without the channel's rules.

## First use: set up your channel (once)

1. [Install](#installation-windows) the skill and [store your fal.ai key](#falai-key).
2. Create a channel folder that will hold all your video folders, e.g. `D:\MyChannel\`.
3. Create the profile, either way:
   - **with Claude** (recommended): open Claude Code in the channel folder and type
     `/resolve-edit Create a channel profile for my channel.` It asks its questions one at a time (channel,
     audience, style, editorial line, video types, shooting setup, publication) and writes the files;
   - **by hand**: copy [`skills/resolve-edit/templates/profile/`](skills/resolve-edit/templates/profile/) into the
     channel folder as `profile\`, move `resolve-edit.json` from it up into the channel folder, and fill in the
     `<...>` placeholders. Write the keyword lists of `settings.json` in your channel's language.
4. Your channel folder now looks like the tree above. The profile gets better after each video (Step 9: what you
   changed by hand becomes a rule).

## Starting a new video

1. Create the video folder inside the channel folder and put the camera files in `rushes/`.
2. Open Resolve and create or open the video's project. Check that timeline playback has sound (a frozen audio
   device makes every render hang at 0%).
3. Open Claude Code **in the video folder** and type, for example:
   ```
   /resolve-edit New video: the rushes are in rushes/, the Resolve project is open.
   ```

## Requirements

- DaVinci Resolve Studio 21.x with its MCP server enabled
- Claude Code (desktop app or CLI)
- Python 3 (standard library only) and ffmpeg / ffprobe in the PATH
- A fal.ai API key (pay per use, ~$0.008 per audio minute)
- Windows for now (the key is stored in the Windows Credential Manager; paths in the scripts)

## Current limits

The workflow and the profile mechanism are generic, but some things still reflect where the skill was born
(a French channel, filmed with one Sony camera):
- **Windows only**: the fal.ai key uses the Windows Credential Manager (`FAL_KEY` works elsewhere, untested), the
  default label font is `C:\Windows\Fonts\arial.ttf` (override: `thumbnail.font`).
- **Resolve names and review markers are in French**: timelines `00 - REFERENCE (ne pas modifier)`,
  `01 - LINEAIRE vN`, `02 - MONTAGE vN`, `03 - FINAL`, bin `Rushes/Non retenus`, markers "Passage retire",
  "Blanc raccourci", "Raccord deplace"... They work in any language but read oddly outside France.
- **Rush short names** follow Sony numbering (`C0123`); other cameras fall back to the file name.
- Tested on one channel only; the profile creation flow has not yet been run with a new user.

## Installation (Windows)

```bat
powershell -ExecutionPolicy Bypass -File install.ps1
```
Mirror copy of `skills/resolve-edit` into `%USERPROFILE%\.claude\skills` (works even when that folder is a WSL
link). Run it again after every change or `git pull`. The repo also has a plugin manifest
(`.claude-plugin/plugin.json`).

## fal.ai key

Never in this repo nor in a global environment variable. Store it yourself, in a terminal:
```bat
python skills\resolve-edit\scripts\fal_key.py set
```
Masked input (one `*` per character, Ctrl+V pastes) or `set --clipboard`; the clipboard is cleared afterwards.
It goes to the Windows Credential Manager (entry `resolve-edit/fal`). `fal_key.py check` shows only its length,
`fal_key.py delete` removes it. `FAL_KEY` is accepted as a fallback.

## Layout

```
skills/resolve-edit/
  SKILL.md            the step-by-step workflow
  references/         profile format, editing method, transcription, Resolve API facts, publication
  scripts/            Python scripts (stdlib + ffmpeg)
  scripts/resolve/    scripts run inside Resolve through the MCP (run_script_unsafe)
  templates/          decisions.example.json, profile/ (empty channel profile to copy)
```
