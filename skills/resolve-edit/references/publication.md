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
python SKILL/scripts/thumbnail_candidates.py transcripts/transcript.json transcripts/clips.json edl/final_dump.json rushes publication/vignettes
```
- The transcript preselects ~20 moments where the presenter shows something (profile `thumbnail.cues`), only if
  still present in FINAL; ffmpeg extracts one frame each (through the viewing LUT of the rush's camera, profile `cameras`,
  preview only) and tiles them in `sheet_1.png` with number + FINAL timecode.
- DO NOT look at the sheet yourself (token saving; the user chooses): give the user the sheet path and the list
  of candidates (id, FINAL timecode, cue, context) and let THEM pick. Only analyse images if the user asks.
- Selection hints if asked: the presenter surrounded by many objects (curiosity), an object clearly visible and
  held up, facing camera with a natural expression; avoid unflattering poses, blur, an object hiding the face,
  backs.
- Export the user's picks full size: same command + `--export 1,16,19` → `vignette_<id>_<tc>.png`. The user makes
  the real thumbnail from the graded image in Resolve at the given FINAL timecode.

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
