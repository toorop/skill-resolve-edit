# YouTube publication package → `publication/youtube.md`

Goal: the user copies/pastes into YouTube Studio and only corrects. Written in the channel's language and the
presenter's voice. The channel profile gives the style (title examples, thumbnail rules, links, footer, generic
tags): read its publication file before writing anything.

## 1. Titles (4-5 proposals)
- Follow the style of the channel's best videos (the profile gives references). Concrete subject + story angle.
- Vary: use the strongest object/story of THIS video rather than the series name.
- Catchy but honest: no fake promises, no outrage unless the profile wants it.

## 2. Thumbnail text (2-4 words)
- Propose 3 short texts that speak DIRECTLY to the target audience (what the video is about), no abstract
  wordplay. Respect the profile's series labels and visual rules.
- The user usually finds the final wording while making the thumbnail: propose, don't insist.

## 2b. Thumbnail image search (cheap: 1 contact sheet ≈ 1 image of tokens)
```
python SKILL/scripts/thumbnail_candidates.py transcripts/transcript.json transcripts/clips.json edl/final_dump.json publication/vignettes
```
- The transcript preselects ~20 moments where the presenter shows something (profile `thumbnail.cues`), only if
  still present in FINAL, and writes `candidates.json` + `sheet_frames.json`. Then `resolve/export_frames.py` with
  `timeline = "03 - FINAL"`, `frames_json = publication/vignettes/sheet_frames.json`, `out_dir = publication/vignettes`
  renders `sheet_1.jpg` (number + FINAL timecode on each frame), as the FINAL shows it (grade, sizing, titles).
- DO NOT look at the sheet yourself (token saving; the user chooses): give the user the sheet path and the list
  of candidates (id, FINAL timecode, cue, context) and let THEM pick. Only analyse images if the user asks.
- Selection hints if asked: the presenter surrounded by many objects (curiosity), an object clearly visible and
  held up, facing camera with a natural expression; avoid unflattering poses, blur, an object hiding the face,
  backs.
- Export the user's picks full size: same command + `--export 1,16,19` (writes `export_frames.json`), then
  `resolve/export_frames.py` on "03 - FINAL" with `frames_json = publication/vignettes/export_frames.json`,
  `mode = "single"` → `vignette_<id>_<tc>.png`, full size. The user retouches the chosen frame for the thumbnail
  anyway (more saturation, warmer, stronger lines: thumbnails are seen very small), so an ungraded FINAL is fine.

## 3. Description
```
<greeting in the presenter's style>
<1 paragraph of context, presenter's voice: where, what, why it's special>

<the profile's links — HIGH, right after the first paragraph, so viewers find them with a tiny scroll>

<highlights: 3-5 short lines>

<optional closing line>

00:00 - <chapter>
...   (from chapters.py on "03 - FINAL"; rewrite titles to be descriptive and catchy; ≥3 chapters, ≥10 s each,
       first at 00:00)

---

<the profile's fixed footer, verbatim>
```

## 4. Tags (~15)
The profile's generic tags + specific ones (objects, places, themes of the video). One comma-separated line
ready to paste.
