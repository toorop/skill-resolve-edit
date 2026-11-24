"""Prepare the reference audio for transcription.

Converts the reference-timeline audio export (FLAC/WAV, any rate) into 16 kHz mono WAV (what speech models use:
no useful loss, no MP3/AAC priming offset) and, if longer than --max-seconds, splits it at RUSH BOUNDARIES
(never inside a sentence), sample-exact. Writes a manifest with each part's offset in the reference timeline.

Usage:
  python prepare_audio.py REFERENCE_AUDIO CLIPS.json OUT_DIR [--max-seconds 1150] [--fps N]
Output: OUT_DIR/ref16k_partN.wav + OUT_DIR/manifest.json  [{"file": ..., "offset": seconds, "duration": seconds}]
"""
import argparse
import os
import subprocess

from common import Clips, fps_arg, save_json, tc

SR = 16000


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def probe_samples(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                          "stream=duration_ts,sample_rate", "-of", "csv=p=0", path],
                         check=True, capture_output=True, text=True).stdout.strip()
    rate, dts = out.split(",")[:2]
    return int(rate), int(dts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("clips")
    ap.add_argument("out_dir")
    ap.add_argument("--max-seconds", type=float, default=1150.0, help="fal.ai Scribe limit is 1200 s; keep a margin")
    fps_arg(ap)
    args = ap.parse_args()

    clips = Clips(args.clips, args.fps, {})
    fps = clips.fps
    os.makedirs(args.out_dir, exist_ok=True)
    full = os.path.join(args.out_dir, "ref16k_full.wav")
    run(["ffmpeg", "-v", "error", "-y", "-i", args.audio, "-ac", "1", "-af", f"aresample={SR}:resampler=soxr",
         "-c:a", "pcm_s16le", full])
    rate, total = probe_samples(full)
    expected = round(clips.total_frames / fps * SR)
    if abs(total - expected) > SR / fps:
        raise SystemExit(f"Audio length {total / SR:.3f}s does not match the reference timeline "
                         f"{expected / SR:.3f}s: export the WHOLE reference timeline.")

    # greedy split on rush boundaries
    bounds = [s for _, s, _ in clips.items[1:]]
    cuts, part_start = [], 0
    max_frames = int(args.max_seconds * fps)
    while clips.total_frames - part_start > max_frames:
        candidates = [b for b in bounds if part_start < b <= part_start + max_frames]
        if not candidates:
            raise SystemExit(f"A single rush is longer than {args.max_seconds}s; split manually.")
        cut = max(candidates)
        cuts.append(cut)
        part_start = cut

    edges = [0] + cuts + [clips.total_frames]
    manifest = []
    for k, (a, b) in enumerate(zip(edges, edges[1:]), 1):
        name = os.path.join(args.out_dir, f"ref16k_part{k}.wav") if len(edges) > 2 else full
        if len(edges) > 2:
            run(["ffmpeg", "-v", "error", "-y", "-i", full, "-af",
                 f"atrim=start_sample={round(a * SR / fps)}:end_sample={round(b * SR / fps)},asetpts=PTS-STARTPTS",
                 "-c:a", "pcm_s16le", name])
        manifest.append({"file": os.path.abspath(name), "offset": a / fps, "duration": (b - a) / fps,
                         "starts_at": tc(a, fps, frames=True), "first_rush": clips.at_frame(a)})
    if len(edges) > 2:
        os.remove(full)
    save_json(os.path.join(args.out_dir, "manifest.json"), manifest, indent=2)
    for m in manifest:
        print(f"{os.path.basename(m['file'])}: offset {m['offset']:.2f}s ({m['starts_at']}, {m['first_rush']}), "
              f"{m['duration']:.2f}s")


if __name__ == "__main__":
    main()
