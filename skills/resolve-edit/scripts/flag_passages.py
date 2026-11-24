"""Keyword pre-scan of the transcript to help the editorial review (Claude still reads the readable transcript and
decides; this only makes sure nothing obvious is missed).

The categories and their regular expressions come from the channel profile (settings.json "flags": {category:
regex}), since they depend on the language and on the channel's editorial policy. Usual categories: divisive
(politics, religion...), youtube (swearing, drugs, sex, violence), interjection (repeated expressions: report the
COUNT), retake (signs of failed takes / off-topic).
Each alternative is matched from the START of a word (the scan adds a leading word boundary).

Usage: python flag_passages.py TRANSCRIPT.json CLIPS.json [--fps 25] [--profile DIR] > flags.txt
"""
import argparse
import re
from collections import defaultdict

from common import Clips, add_profile_arg, load_settings, load_words, short_name, tc

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("clips")
    ap.add_argument("--fps", type=int, default=25)
    add_profile_arg(ap)
    args = ap.parse_args()
    patterns = load_settings(args.profile).get("flags") or {}
    if not patterns:
        raise SystemExit('No "flags" patterns in the channel profile settings.json: nothing to scan.')

    words = load_words(args.transcript)
    clips = Clips(args.clips, args.fps)
    text, index = "", []  # char offset -> word index
    for w in words:
        index.append(len(text))
        text += w["text"].lower() + " "
    hits = defaultdict(list)
    for cat, pat in patterns.items():
        for m in re.finditer(r"\b(?:" + pat + ")", text):
            wi = max(i for i, off in enumerate(index) if off <= m.start())
            ctx = " ".join(w["text"] for w in words[max(0, wi - 8):wi + 8])
            hits[cat].append((words[wi]["start"], m.group(0), ctx))
    for cat in patterns:
        print(f"\n## {cat} ({len(hits[cat])})")
        for t, kw, ctx in hits[cat]:
            print(f"  {tc(t, args.fps)} {short_name(clips.at(t) or '?'):6} [{kw}]  ...{ctx}...")


if __name__ == "__main__":
    main()
