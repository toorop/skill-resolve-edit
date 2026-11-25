"""Shared helpers for the tests: invented data only (no real channel, no real footage).

Run all tests from the repository root:  python -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "resolve-edit", "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = unittest.skipUnless(HAS_FFMPEG, "ffmpeg / ffprobe not in the PATH")

# An invented English channel profile (settings.json content).
SETTINGS = {
    "language": "en",
    "cameras": [
        {"name": "Cam A", "match": "CAMA", "short_name": r"A\d{4}", "clock_offset": 0},
        {"name": "Cam B", "match": "CAMB", "short_name": r"(B)_\d{8}_(\d{3})", "clock_offset": 0},
    ],
    "linear": {"demo_cues": ["look", "watch this"]},
    "flags": {"swearing": r"damn\b", "retake": r"cut\b|let me start again"},
    "thumbnail": {"cues": [["treasure|gorgeous", 3], ["look at", 1]], "show_delay": 1.5},
    "montage": {"blooper_title": "Bloopers"},
}


def write_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return path


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clips_data(rushes, fps=25):
    """rushes = [(name, length_in_timeline_frames, rush_fps or None, short or None), ...] laid end to end."""
    out, pos = [], 0
    for r in rushes:
        name, length = r[0], r[1]
        rate = r[2] if len(r) > 2 and r[2] else fps
        short = r[3] if len(r) > 3 and r[3] else os.path.splitext(name)[0]
        out.append({"name": name, "start": pos, "end": pos + length, "short": short, "camera": None, "fps": rate,
                    "file": name})
        pos += length
    return {"version": 2, "fps": fps, "width": 1920, "height": 1080, "rushes_dir": "/rushes", "clips": out}


def transcript(words, language="eng"):
    """words = [(text, start, end) or (text, start, end, speaker_id) or (text, start, end, speaker, type)].
    Spacing tokens are added between words, like Scribe."""
    toks = []
    for k, w in enumerate(words):
        text, start, end = w[0], w[1], w[2]
        spk = w[3] if len(w) > 3 else "speaker_0"
        typ = w[4] if len(w) > 4 else "word"
        if toks:
            prev = toks[-1]
            toks.append({"text": " ", "start": prev["end"], "end": start, "type": "spacing", "speaker_id": spk})
        toks.append({"text": text, "start": start, "end": end, "type": typ, "speaker_id": spk})
    return {"source": "test", "language_code": language, "words": toks, "text": "".join(t["text"] for t in toks)}


def sentence(text, start, step=0.4, speaker="speaker_0"):
    """'Hello there.' starting at `start`: one word every `step` s, each lasting step - 0.1 s."""
    return [(w, round(start + k * step, 3), round(start + k * step + step - 0.1, 3), speaker)
            for k, w in enumerate(text.split())]


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="resolve-edit-test-")
        self.profile = os.path.join(self.tmp, "profile")
        write_json(os.path.join(self.profile, "settings.json"), SETTINGS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)

    def run_script(self, script, *args, check=True):
        """Runs a skill script like Claude does (python <script> args), from the temp folder."""
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        env.pop("RESOLVE_EDIT_PROFILE", None)
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + [str(a) for a in args],
                           cwd=self.tmp, capture_output=True, text=True, encoding="utf-8", env=env)
        if check and p.returncode:
            self.fail(f"{script} failed ({p.returncode}):\n{p.stdout}\n{p.stderr}")
        return p
