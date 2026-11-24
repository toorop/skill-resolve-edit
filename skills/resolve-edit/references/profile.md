# Channel profile — format and creation

Everything that differs from one channel to another lives in the channel profile, not in the skill. The skill
gives the method and generic defaults; the profile gives the taste. Write the profile in the user's language:
it is the user's document, they reread and correct it.

## Where it is found
1. `--profile DIR` on a script;
2. else the `RESOLVE_EDIT_PROFILE` environment variable;
3. else the first `resolve-edit.json` found in the working directory (the video folder) or one of its parents:
   ```json
   {"profile": "profil"}
   ```
   The path is relative to the pointer file (absolute paths and `\\server\share` paths work too). Put the pointer
   in the channel folder that holds all the video folders: moving the profile then means changing one line.

## Required files
| File | Read by | Content |
|---|---|---|
| `profile.md` | Claude, Step 0 | channel, URL, audience, presenter, language; shooting setup (camera, fps, log profile, microphone); workstation traps (audio device, drives); where the skill's source repo is and how to reinstall it; where to write the per-video notes; **list of the other files and when to read them** |
| `settings.json` | scripts | numbers and keyword lists (below). JSON; lines starting with `//` are comments |

Typical other files (free names, listed in `profile.md`): editing style, editorial policy, video types,
publication rules, description footer, audio finishing chain, a `decisions.json` example from a real video.

## `settings.json` keys
Layering for the linear cut: skill defaults < profile `linear` < the video's `decisions.json` `linear`.
```
language                 transcription language code ("fr"); omitted = Scribe detects it
transcription.keyterms   names Scribe should spell right (+30% cost)
linear.gap_min           gaps shorter than this are never touched (s, default 2.0)
linear.keep_air          air kept on each side of a shortened gap (s, default 0.5)
linear.head_pad          kept before the first word of a rush (s, default 0.3)
linear.tail_pad          kept after the last word of a rush (s, default 0.5)
linear.min_isolated      isolated pieces shorter than this are dropped (s, default 1.5)
linear.demo_cues         word fragments before a long gap that mean "silent demonstration": keep the gap
flags.<category>         regex alternatives for flag_passages.py (e.g. divisive, youtube, interjection, retake)
thumbnail.cues           [[regex, weight], ...] moments where the presenter shows something
thumbnail.show_delay     seconds after the cue (default 1.5)
thumbnail.lut            viewing LUT (.cube) for log footage, or null
thumbnail.font           font for the contact sheet labels (default Arial)
montage.blooper_title    title card text before the bloopers (default "Bloopers")
```
Without `flags` or `thumbnail.cues`, those scripts stop and say so: the lists are language- and channel-specific.

## Per-video note (Step 9), if `profile.md` names a notes folder
One folder per video (e.g. `<date of shooting> <title>`), holding the pre-shoot documents if any and a
"montage and publication" note: published title, description and tags (or a link to the archived
`youtube.md`), YouTube link, timelines of the Resolve project, what the user changed by hand in FINAL and why,
lessons and where they were written (profile or skill), and the path of the working folder. Archive next to it
the small files worth keeping once the work drive is wiped: `decisions.json`, `transcript_lisible.txt`,
`publication/youtube.md`, the montage plan and `final_dump.json` (tens of KB, never media or raw transcripts).

## Creating a profile with the user
Ask one question at a time, with a recommendation each time. In this order:
1. Channel, URL, presenter(s), language, audience (age, viewing device: TV vs. phone changes everything).
2. What makes the channel work and what must never be done (rhythm, cuts, transitions, music, humor).
3. Editorial line: business goals, what to flag (divisive, YouTube-sensitive), what is fine.
4. Video types and how each is edited (free re-ordering vs. shooting order).
5. Shooting setup and workstation traps.
6. Publication: title style, thumbnail style, links and footer, tags.
Then copy `templates/profile/` to `<channel folder>/profile/`, move its `resolve-edit.json` up into the channel
folder, and fill in the files with the answers, in the user's language (rename the documents if the user prefers,
and update the table of `profile.md`). Translate the keyword lists of `settings.json` into the channel's language:
the template's lists are English examples. Run Step 0 again. The first video's Step 9 will refine the profile.
