"""Split the reference transcript into one transcription per rush, for Resolve's MediaPoolItem.SetTranscription
(applied by resolve/set_transcription.py). Pure computation: no Resolve needed.

The transcript is timed on the REFERENCE timeline (seconds). Each word goes to the rush where it starts; its times
become frames of THAT RUSH (its own rate, frame 0 = first frame of the rush). resolve/set_transcription.py adds the
clip's Start TC. Words are grouped in segments (new segment at a speaker change, after . ? ! or after a silence of
--gap seconds). Spacing tokens and audio events ([rire]) are dropped; a punctuation-only token sticks to the word
before it. Word text gets a leading space, as in Resolve's own transcriptions.

Frames: start and end = nearest frame (halves up), at least one frame long. Words may share a boundary
frame (Resolve's own transcriptions do), never overlap: a word that would start inside the previous one starts at
its end (counted in "shifted").

Usage: python split_transcript.py TRANSCRIPT.json CLIPS.json OUT.json [--gap 1.5] [--no-speakers] [--fps N]
"""
import argparse
import math

from common import Clips, fps_value, load_json, save_json

LANGUAGES = {"fra": "fr", "eng": "en", "deu": "de", "spa": "es", "ita": "it", "por": "pt", "nld": "nl"}
SENTENCE_END = (".", "?", "!", "…")


def language(code):
    """Scribe gives ISO 639-3 ('fra'), Resolve wants 'fr'. None when unknown: Resolve keeps the clip's language."""
    if not code:
        return None
    code = code.lower()
    return code if len(code) == 2 else LANGUAGES.get(code)


def to_frame(seconds, rate):
    """Nearest frame, halves rounded up (Python's round() sends x.5 to the even number, so two words that touch
    could land one frame apart or overlap). Scribe times are multiples of 20 ms: x.5 is frequent at 25p."""
    return int(math.floor(seconds * rate + 0.5 + 1e-6))


def speaker_name(speaker_id):
    """speaker_0 -> 'Speaker 1' (Resolve's own naming)."""
    if not speaker_id:
        return None
    tail = speaker_id.rsplit("_", 1)[-1]
    return f"Speaker {int(tail) + 1}" if tail.isdigit() else speaker_id


def rush_words(words, clips):
    """Spoken words grouped by rush: {clip name: [{text, start, end, speaker}]} with times in reference seconds."""
    out = {}
    last_clip = None
    for w in words:
        if w["type"] != "word":
            continue
        text = w["text"].strip()
        if not text:
            continue
        if not any(ch.isalnum() for ch in text):
            if last_clip and out[last_clip]:
                out[last_clip][-1]["text"] += text
            continue
        clip = clips.at(w["start"])
        if clip is None:
            continue
        last_clip = clip
        out.setdefault(clip, []).append({"text": text, "start": w["start"], "end": w["end"],
                                         "speaker": w.get("speaker_id")})
    return out


def split(transcript, clips, gap=1.5, speakers=True):
    tl_fps = clips.fps
    result = {"version": 1, "source": transcript.get("source"), "language": language(transcript.get("language_code")),
              "gap": gap, "clips": []}
    by_clip = rush_words(transcript["words"], clips)
    for name, start, end in clips.items:
        rate = fps_value(clips.meta.get(name, {}).get("fps") or tl_fps)
        length = int(round((end - start) * rate / tl_fps))  # rush length in its own frames
        offset = start / tl_fps                              # reference seconds of the rush's first frame
        segments, seg, prev_end, prev_word, shifted = [], None, 0, None, 0
        for w in by_clip.get(name, []):
            s = to_frame(w["start"] - offset, rate)
            e = to_frame(w["end"] - offset, rate)
            if s < prev_end:
                s = prev_end
                shifted += 1
            s = min(max(s, 0), length - 1)
            e = min(max(e, s + 1), length)
            spk = speaker_name(w["speaker"]) if speakers else None
            new_seg = (seg is None or (speakers and spk != seg["speaker"])
                       or prev_word["text"].endswith(SENTENCE_END)
                       or w["start"] - prev_word["end"] >= gap)
            if new_seg:
                seg = {"start": s, "end": e, "speaker": spk, "words": []}
                segments.append(seg)
            seg["words"].append({"text": " " + w["text"], "start": s, "end": e})
            seg["end"] = e
            prev_end, prev_word = e, w
        for sg in segments:
            sg["text"] = "".join(x["text"] for x in sg["words"])
            if not speakers:
                del sg["speaker"]
        result["clips"].append({"name": name, "file": clips.file(name), "short": clips.short(name), "fps": rate,
                                "frames": length, "n_words": sum(len(sg["words"]) for sg in segments),
                                "shifted": shifted, "segments": segments})
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("clips")
    ap.add_argument("out")
    ap.add_argument("--gap", type=float, default=1.5, help="silence (s) that starts a new segment")
    ap.add_argument("--no-speakers", action="store_true", help="do not pass speaker names to Resolve")
    ap.add_argument("--fps", type=float, default=None, help="reference timeline rate (default: from clips.json)")
    args = ap.parse_args()

    clips = Clips(args.clips, args.fps, settings={})
    res = split(load_json(args.transcript), clips, args.gap, not args.no_speakers)
    data = load_json(args.clips)
    if isinstance(data, dict):
        res["rushes_dir"] = data.get("rushes_dir")
    save_json(args.out, res)
    n_words = sum(c["n_words"] for c in res["clips"])
    empty = [c["short"] for c in res["clips"] if not c["segments"]]
    print(f"{args.out}: {len(res['clips'])} rushes, {n_words} words, "
          f"{sum(len(c['segments']) for c in res['clips'])} segments, "
          f"{sum(c['shifted'] for c in res['clips'])} words shifted, language {res['language']}")
    if empty:
        print("no speech (left without transcription): " + ", ".join(empty))


if __name__ == "__main__":
    main()
