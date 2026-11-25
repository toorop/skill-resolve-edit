# Editing method (generic — the channel profile's style refines or overrides it)

## Priorities when they conflict
1. **Don't break what is said**: speech is the content, not the packaging.
2. **Show the object / the subject**: words alone rarely make people understand or want it.
3. **Make the whole hold together** without turning it into a catalogue.

## When to cut — three reasons, no more
1. **Remove dead time**: hesitation, false start, repetition, gap that is too long.
2. **Move from one idea to another**: new object, topic, conclusion.
3. **Show**: cut to the object or a detail when speech is not enough.
- Never cut inside a sentence that carries information or emotion: cut in silences.
- A cut that serves none of the three reasons is one cut too many. No target cutting rate.
- When hesitating between cutting and leaving: leave (unless the profile says the audience wants a fast pace).

## Linear cut mechanics (`edl_lib.py`, thresholds in the profile's `settings.json` → `linear`)
| Rule | Default | Why |
|---|---|---|
| Never touch gaps shorter than | `gap_min` 2.0 s | breaths, air |
| Longer gaps → keep on each side | `keep_air` 0.5 s (gap becomes ~1 s) | |
| ...unless the words before suggest a demonstration | `demo_cues` (profile, language-specific) | silent showing/opening |
| Each raw rush starts before the first word | `head_pad` 0.3 s | camera start, framing |
| ...and ends after the last word | `tail_pad` 0.5 s | |
| Isolated piece shorter than, cut on both sides (a rush change counts as a cut) | `min_isolated` 1.5 s → dropped, plus the orphan end of its sentence in the next rush | parasite flash ("Right.", "So, let's do / ...") |
| `keep_head` / `keep_tail` exceptions | per video (`decisions.json`) | silent visual intro (arrival), sentence continuing across rushes |
- The transcript cannot see images. Rush heads can hold real content (an arrival by car): ask when a rush
  head/tail is long and silent.
- Sentences can continue across rushes: keep both rushes adjacent in the montage. But if the part before the rush
  change is a short isolated sliver, drop it AND the orphan continuation up to the first punctuation.

## Image: flattering framing and J-cuts
At rush heads (getting out of a car, bending over, sitting down) the presenter can be badly framed. Check with
the cut sheets (`resolve/export_frames.py`, `mode = "cuts"`) and PROPOSE a J-cut (voice of the talking shot laid under the previous shot,
video on V2) rather than cutting words. `build_timeline.py` doesn't build J-cuts yet: describe it and let the
user do it.

## Turning an inventory into a story (re-ordered montage)
1. **State the stake at the start** (10-30 s): where, what we will see, why it is worth the time. The only place
   where a faster pace is acceptable: that is where viewers leave.
2. **Keep the presenter's structural phrases and place them where they become true** ("before we start",
   "we're halfway", "I kept the best for the end"). Never cut a mid-video promise; avoid stacking "we're nearly
   done" phrases.
3. **Order, don't stack**: don't keep the shooting order by default (unless the video type needs the geography,
   e.g. a house visit). Strong or emotional topics early; best pieces at the end or just before; a weak piece
   after a strong one must be announced.
4. **Alternate** (technical object → personal or funny moment); never three similar topics in a row; group what
   belongs together; reconnect material shot at different times (an add-on shot later goes right after its topic).
5. Business announcements not at the very start: after the first strong topic.
6. End on the outro; if the best piece and the outro are in the same rush, end on it (no join).
7. Bloopers (optional): after a title card; cut real swear words before them.

## Using the channel's retention data (when the user has it)
- Treat the first 30 seconds as a block to review on its own.
- A retention peak after the middle should move into the first third.
- A dip matches a sequence: shorten or move it. Never compensate a dip by adding elsewhere.

## Audio finishing (built by `build_timeline.py`)
- Audio **cross fade** at every cut: "Cross Fade +3 dB", 4 frames, centered (left-aligned when no handles).
  Not fade-out/fade-in dips (the level audibly dips).
- **Normalize** with the YouTube preset, RELATIVE mode (one gain for all clips).
- No video transitions, no other audio processing, no color unless the profile says so.

## Review markers (so the user doesn't rewatch everything)
Purple = sequence start (= chapters) · Blue = gap shortened · Green = gap kept (demo?) · Red = passage removed ·
Cyan = moved material joined · Pink = title / bloopers. Plain rush junctions are not marked.

## What not to believe
Cutting every 2-3 seconds, a spectacular 3-second hook and high cadence as a retention lever come from short
formats and cinema; an experimental study on jump cuts found high cadence reduces sustained engagement. The
"8-second attention span" is a myth. YouTube's own retention documentation (intro as a unit, top moments,
dips) is the reliable source.
