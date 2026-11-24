"""Shared helpers for the resolve-edit scripts (stdlib only)."""
import json
import os
import re
import unicodedata

FPS_DEFAULT = 25
PROFILE_POINTER = "resolve-edit.json"  # {"profile": "<channel profile folder>"}, in the video folder or above it
PROFILE_ENV = "RESOLVE_EDIT_PROFILE"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data, indent=1):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def load_jsonc(path):
    """JSON with full-line // comments (used for the channel profile's settings.json)."""
    with open(path, encoding="utf-8") as f:
        text = "".join(line for line in f if not line.lstrip().startswith("//"))
    return json.loads(text)


def find_profile(start=None):
    """Channel profile folder: --profile, else $RESOLVE_EDIT_PROFILE, else the first resolve-edit.json found in the
    working directory (= video folder) or one of its parents. Relative paths are relative to the pointer file."""
    if os.environ.get(PROFILE_ENV):
        return os.path.abspath(os.environ[PROFILE_ENV])
    d = os.path.abspath(start or os.getcwd())
    while True:
        pointer = os.path.join(d, PROFILE_POINTER)
        if os.path.isfile(pointer):
            return os.path.normpath(os.path.join(d, load_json(pointer)["profile"]))
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_settings(profile=None):
    """settings.json of the channel profile ({} when there is no profile: generic defaults only)."""
    folder = profile or find_profile()
    path = os.path.join(folder, "settings.json") if folder else None
    if not path or not os.path.isfile(path):
        return {}
    return load_jsonc(path)


def add_profile_arg(parser):
    parser.add_argument("--profile", help="channel profile folder (default: found via resolve-edit.json)")


def tc(seconds_or_frames, fps=FPS_DEFAULT, frames=False):
    """Resolve-style timecode HH:MM:SS:FF from seconds (default) or frames."""
    f = int(seconds_or_frames) if frames else int(round(seconds_or_frames * fps))
    return f"{f // (3600 * fps):02d}:{f // (60 * fps) % 60:02d}:{f // fps % 60:02d}:{f % fps:02d}"


def parse_time(value, fps=FPS_DEFAULT):
    """Seconds (number) or 'HH:MM:SS:FF' timecode -> seconds (float)."""
    if isinstance(value, (int, float)):
        return float(value)
    h, m, s, fr = (int(x) for x in str(value).split(":"))
    return h * 3600 + m * 60 + s + fr / fps


def short_name(clip_name):
    """'20260101_C0012.MP4' -> 'C0012' (Sony numbering), otherwise the file stem."""
    m = re.search(r"C\d{4}", clip_name)
    return m.group(0) if m else os.path.splitext(clip_name)[0]


def ascii_only(text):
    """Resolve's scripting bridge mangles non-ASCII names/notes: strip accents for markers, bins, timelines."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def is_spoken(word):
    return word.get("type") == "word" and any(ch.isalnum() for ch in word.get("text", ""))


def load_words(transcript_path, include_spacing=False):
    words = load_json(transcript_path)["words"]
    return words if include_spacing else [w for w in words if w["type"] != "spacing"]


class Clips:
    """Reference timeline map: [[clip_name, start_frame, end_frame], ...] (frame 0 = start of the reference)."""

    def __init__(self, path_or_list, fps=FPS_DEFAULT):
        self.items = load_json(path_or_list) if isinstance(path_or_list, str) else path_or_list
        self.fps = fps
        self.start = {n: s for n, s, _ in self.items}
        self.end = {n: e for n, _, e in self.items}

    @property
    def total_frames(self):
        return self.items[-1][2]

    def at_frame(self, frame):
        for n, s, e in self.items:
            if s <= frame < e:
                return n
        return None

    def at(self, seconds):
        return self.at_frame(seconds * self.fps)

    def by_short(self, short):
        for n, s, e in self.items:
            if short_name(n) == short:
                return n, s, e
        raise KeyError(short)

    def split(self, a, b):
        """Reference frames [a, b) -> list of [clip, src_in, src_out) split on rush boundaries."""
        out = []
        while a < b:
            n = self.at_frame(a)
            hi = min(b, self.end[n])
            out.append([n, a - self.start[n], hi - self.start[n]])
            a = hi
        return out
