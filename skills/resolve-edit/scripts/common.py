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


def fps_value(x):
    """25 / 25.0 / "25" -> 25 (int when integral, so plans keep writing "fps": 25); 29.97 stays a float."""
    x = float(x)
    return int(x) if x == int(x) else x


def tc(seconds_or_frames, fps=FPS_DEFAULT, frames=False):
    """Resolve-style timecode HH:MM:SS:FF from seconds (default) or frames. Fractional rates (23.976, 29.97) count
    frames on the nominal rate (24, 30) like Resolve's non-drop-frame timecode."""
    f = int(seconds_or_frames) if frames else int(round(seconds_or_frames * fps))
    n = int(round(fps))
    return f"{f // (3600 * n):02d}:{f // (60 * n) % 60:02d}:{f // n % 60:02d}:{f % n:02d}"


def parse_time(value, fps=FPS_DEFAULT):
    """Seconds (number) or 'HH:MM:SS:FF' timecode -> seconds (float)."""
    if isinstance(value, (int, float)):
        return float(value)
    h, m, s, fr = (int(x) for x in str(value).split(":"))
    if fps == int(fps):
        return h * 3600 + m * 60 + s + fr / fps
    return (((h * 60 + m) * 60 + s) * int(round(fps)) + fr) / fps


def camera_rules(settings):
    """Profile cameras ("cameras" of settings.json) with their compiled patterns."""
    out = []
    for cam in (settings or {}).get("cameras") or []:
        out.append(dict(cam, _match=re.compile(cam["match"], re.I) if cam.get("match") else None,
                        _short=re.compile(cam["short_name"]) if cam.get("short_name") else None))
    return out


def short_from_pattern(name, pattern):
    """Short name from a camera pattern: the captured groups joined, else the whole match; None if no match."""
    m = pattern.search(name) if pattern else None
    if not m:
        return None
    return "".join(g for g in m.groups() if g) if m.groups() else m.group(0)


def short_name(clip_name, settings=None):
    r"""Short name of a rush for reports and decisions.json. Rules come from the profile's cameras ("short_name"
    pattern, e.g. "C\d{4}" or "(DJI)_\d{14}_(\d{4})"); without a matching rule, the file stem."""
    for cam in camera_rules(settings if settings is not None else load_settings()):
        sh = short_from_pattern(clip_name, cam["_short"])
        if sh:
            return sh
    return os.path.splitext(clip_name)[0]


def ascii_only(text):
    """Resolve's scripting bridge mangles non-ASCII names/notes: strip accents for markers, bins, timelines."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def is_spoken(word):
    return word.get("type") == "word" and any(ch.isalnum() for ch in word.get("text", ""))


def load_words(transcript_path, include_spacing=False):
    words = load_json(transcript_path)["words"]
    return words if include_spacing else [w for w in words if w["type"] != "spacing"]


class Clips:
    """Reference timeline map (frame 0 = start of the reference). ALL frames are reference-timeline frames, at the
    timeline rate, whatever each rush's own rate: a 50p rush in a 25p timeline spans 25 frames per second here.

    clips.json, written by resolve/import_reference.py:
      {"version": 2, "fps": 25, "width": 3840, "height": 2160,
       "clips": [{"name", "start", "end", "short", "camera", "fps", "file"}, ...]}
    The first format, a bare list [[clip_name, start_frame, end_frame], ...], is still read (fps from --fps or 25,
    short names from the profile's camera patterns).
    """

    def __init__(self, path_or_list, fps=None, settings=None):
        data = load_json(path_or_list) if isinstance(path_or_list, str) else path_or_list
        if isinstance(data, dict):
            self.fps = fps_value(fps or data.get("fps") or FPS_DEFAULT)
            self.meta = {c["name"]: c for c in data["clips"]}
            self.items = [[c["name"], c["start"], c["end"]] for c in data["clips"]]
        else:
            self.fps = fps_value(fps or FPS_DEFAULT)
            self.items = data
            self.meta = {}
        self.settings = settings
        self.start = {n: s for n, s, _ in self.items}
        self.end = {n: e for n, _, e in self.items}
        self._short = {}

    @property
    def total_frames(self):
        return self.items[-1][2]

    def short(self, name):
        if name not in self._short:
            m = self.meta.get(name, {})
            self._short[name] = m.get("short") or short_name(name, self.settings)
        return self._short[name]

    def file(self, name):
        """Path of the rush relative to the rushes folder (sub-folders kept); the name itself for old clips.json."""
        return self.meta.get(name, {}).get("file") or name

    def camera(self, name):
        return self.meta.get(name, {}).get("camera")

    def at_frame(self, frame):
        for n, s, e in self.items:
            if s <= frame < e:
                return n
        return None

    def at(self, seconds):
        return self.at_frame(seconds * self.fps)

    def by_short(self, short):
        for n, s, e in self.items:
            if self.short(n) == short:
                return n, s, e
        raise KeyError(short)

    def split(self, a, b):
        """Reference frames [a, b) -> list of [clip, in, out) split on rush boundaries. in/out are offsets from the
        start of the rush IN TIMELINE FRAMES (resolve/build_timeline.py converts them to the rush's own frames)."""
        out = []
        while a < b:
            n = self.at_frame(a)
            hi = min(b, self.end[n])
            out.append([n, a - self.start[n], hi - self.start[n]])
            a = hi
        return out


def fps_arg(parser):
    parser.add_argument("--fps", type=float, default=None,
                        help="reference timeline rate (default: from clips.json, else 25)")
