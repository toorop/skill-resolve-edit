"""Condensed transcript for reading (by Claude or the user): one sentence per line, Resolve timecode of the
REFERENCE timeline, grouped by rush, speaker changes and silences >= 1.5 s shown. Never read the raw JSON.

Usage: python readable_transcript.py TRANSCRIPT.json CLIPS.json OUT.txt [--fps 25]
"""
import argparse

from common import Clips, load_words, short_name, tc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("clips")
    ap.add_argument("out")
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--silence", type=float, default=1.5)
    args = ap.parse_args()

    words = load_words(args.transcript, include_spacing=True)
    clips = Clips(args.clips, args.fps)
    lines, cur, cur_clip, prev_end = [], [], None, None

    def flush():
        if cur:
            text = "".join(w["text"] for w in cur).strip()
            spk = cur[0].get("speaker_id") or ""
            spk = "" if spk in ("speaker_0", "") else f"[{spk}] "
            lines.append(f"{tc(cur[0]['start'], args.fps)}  {spk}{text}")
            cur.clear()

    for w in words:
        if w["type"] == "spacing":
            if cur:
                cur.append(w)
            continue
        c = clips.at(w["start"])
        gap = w["start"] - prev_end if prev_end is not None else 0
        if c != cur_clip:
            flush()
            lines.append(f"\n=== {short_name(c) if c else '?'}  ({tc(w['start'], args.fps)})")
            cur_clip = c
        elif gap >= args.silence:
            flush()
            lines.append(f"            ... silence {gap:.1f}s")
        elif cur and cur[0].get("speaker_id") != w.get("speaker_id"):
            flush()
        cur.append(w)
        prev_end = w["end"]
        if w["type"] == "audio_event" or w["text"].rstrip().endswith((".", "?", "!")):
            flush()
    flush()
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).lstrip() + "\n")
    print(f"{args.out}: {len(lines)} lines")


if __name__ == "__main__":
    main()
