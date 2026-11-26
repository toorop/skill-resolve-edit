# Channel profile — <channel name>

Read by the resolve-edit skill at Step 0. Write it in YOUR language: it is your document.
Replace every <...>; delete what does not apply. Format: `references/profile.md` of the skill.

## The channel
- Name and URL: <...>
- Presenter(s): <...>
- Language: <e.g. English> (Claude speaks it with you; transcription language goes in settings.json)
- Audience: <age, country, viewing device — TV, desktop or phone changes the pace a lot>
- Goals: <views, clients for a business, ...>

## Shooting
- Camera(s), resolution, fps, log profile: <...> (does the user grade the footage themselves?) — each camera also
  gets an entry in `settings.json` → `cameras` (how to recognise it, short names, clock offset)
- Several cameras in one video: <one after the other / never> (filming at the same time is not handled yet)
- Which sound to use: <the sound inside the video files; which microphone it comes from; files to ignore, e.g. a
  camera's backup .WAV>
- Microphone(s): <...>
- Typical takes: <one continuous shot per topic, walk-and-talk, ...>

## Workstation (known traps)
- <audio interface that freezes, full drives, ...>
- One Resolve project per video, named like its folder: <yes/no>

## Skill development (ONLY if you develop the skill yourself; otherwise delete this section)
- Repo: <path or URL of your copy of skill-resolve-edit>, reinstall with `install.ps1`. With this section, Step 9
  also proposes improvements to the skill (Resolve API, scripts, method); without it, it never does.

## Per-video notes (Step 9, optional)
- Folder: <path of your notes folder, one sub-folder per video>, or "none".

## Profile files
| File | When to read it |
|---|---|
| `settings.json` | read by the scripts (thresholds, keyword lists) |
| `editing-style.md` | Steps 4 to 7 |
| `editorial-policy.md` | Step 4 (dérushage report) and Step 8 |
| `video-types.md` | Step 0 (ask the type) and Step 6 |
| `publication.md` + `footer.md` | Step 8 |
