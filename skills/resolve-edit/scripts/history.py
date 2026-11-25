"""Keeps what Claude proposed and what the user validated, video by video, in the video folder's history/ (small,
private, archived with the video note). The future data set to compare models; nothing here changes the edit.

  python history.py save KIND FILE [--model ID]   copy FILE into history/ under the name of KIND
  python history.py compare [--fps N]              proposals vs what was validated -> history/comparison.md/.json

KIND (file names in history/; a second proposal of the same kind gets _2, _3...):
  derushage_proposal     04_derushage_proposal.md / .json    Step 4 report as shown, BEFORE the user's answers;
                                                             the .json in the decisions.json format
                                                             {"linear": {"remove": [{label, start, end, reason}]}}
  decisions_linear       decisions_linear_vN.json            decisions.json when a linear version is built
  montage_proposal       06_montage_proposal.md / .json      Step 6 order as proposed ({"montage": {"sequences"...}})
  decisions_montage      decisions_montage_vN.json           decisions.json when a montage version is built
  publication_proposal   08_publication_proposal.md          titles, thumbnail texts, description proposed
  published              09_published.md                     what the user really published (Step 9)
Every save is listed in history/meta.json with its time, the model (--model) and a hash of the skill's scripts.
Run from the video folder.
"""
import argparse
import hashlib
import os
import shutil
import sys
from datetime import datetime, timezone

from common import find_profile, load_json, parse_time, save_json, tc

HERE = os.path.dirname(os.path.abspath(__file__))
KINDS = {"derushage_proposal": "04_derushage_proposal", "montage_proposal": "06_montage_proposal",
         "publication_proposal": "08_publication_proposal", "published": "09_published",
         "decisions_linear": "decisions_linear_v", "decisions_montage": "decisions_montage_v"}


def skill_hash():
    """Short hash of the skill's scripts: which exact code produced the material."""
    h = hashlib.sha256()
    for d, dirs, files in sorted(os.walk(HERE)):
        dirs[:] = sorted(x for x in dirs if x != "__pycache__")
        for f in sorted(files):
            if f.endswith(".py"):
                with open(os.path.join(d, f), "rb") as fh:
                    h.update(f.encode() + fh.read())
    return h.hexdigest()[:12]


def target(folder, kind, ext):
    base = KINDS[kind]
    if base.endswith("_v"):  # versions: next free number
        n = 1
        while os.path.exists(os.path.join(folder, f"{base}{n}{ext}")):
            n += 1
        return os.path.join(folder, f"{base}{n}{ext}")
    path, n = os.path.join(folder, base + ext), 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base}_{n}{ext}")
        n += 1
    return path


def save(kind, src, model=None, folder="history"):
    if kind not in KINDS:
        raise SystemExit(f"unknown kind {kind}: one of {', '.join(KINDS)}")
    ext = os.path.splitext(src)[1].lower() or ".md"
    if ext == ".json":
        load_json(src)  # refuse a broken JSON now rather than at comparison time
    os.makedirs(folder, exist_ok=True)
    dst = target(folder, kind, ext)
    shutil.copyfile(src, dst)
    meta_path = os.path.join(folder, "meta.json")
    meta = load_json(meta_path) if os.path.exists(meta_path) else {
        "video": os.path.basename(os.path.abspath(".")), "profile": os.path.basename(find_profile() or "") or None,
        "saves": []}
    meta["saves"].append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                          "kind": kind, "file": os.path.basename(dst), "model": model, "skill": skill_hash()})
    save_json(meta_path, meta)
    return dst


def _latest(folder, prefix):
    if not os.path.isdir(folder):
        return None
    files = sorted((f for f in os.listdir(folder) if f.startswith(prefix) and f.endswith(".json")),
                   key=lambda f: (len(f), f))
    return os.path.join(folder, files[-1]) if files else None


def compare_removals(proposed, validated, fps):
    """Proposed vs validated removals (seconds). Same passage = overlap of at least half the shorter one."""
    def rng(r):
        return parse_time(r["start"], fps), parse_time(r["end"], fps)
    P = [(r, *rng(r)) for r in proposed]
    V = [(r, *rng(r)) for r in validated]
    used, out = set(), {"accepted": [], "adjusted": [], "refused": [], "added_by_user": []}
    for r, a, b in P:
        best, score = None, 0.0
        for k, (v, c, d) in enumerate(V):
            inter = min(b, d) - max(a, c)
            if inter > 0 and k not in used:
                s = inter / max(1e-9, min(b - a, d - c))
                if s > score:
                    best, score = k, s
        if best is None or score < 0.5:
            out["refused"].append({"label": r.get("label"), "start": tc(a, fps), "end": tc(b, fps),
                                   "reason": r.get("reason")})
            continue
        used.add(best)
        v, c, d = V[best]
        item = {"label": r.get("label"), "proposed": [tc(a, fps), tc(b, fps)], "validated": [tc(c, fps), tc(d, fps)],
                "shift_start": round(c - a, 2), "shift_end": round(d - b, 2)}
        (out["accepted"] if abs(c - a) < 0.5 and abs(d - b) < 0.5 else out["adjusted"]).append(item)
    for k, (v, c, d) in enumerate(V):
        if k not in used:
            out["added_by_user"].append({"label": v.get("label"), "start": tc(c, fps), "end": tc(d, fps)})
    return out


def compare_sequences(proposed, validated):
    titles_v = [s["title"] for s in validated]
    titles_p = [s["title"] for s in proposed]
    out = {"kept_same_place": [], "moved": [], "dropped": [], "added_by_user": [], "ranges_changed": []}
    for i, s in enumerate(proposed):
        if s["title"] not in titles_v:
            out["dropped"].append(s["title"])
            continue
        j = titles_v.index(s["title"])
        (out["kept_same_place"] if i == j else out["moved"]).append(
            s["title"] if i == j else {"title": s["title"], "proposed_rank": i + 1, "validated_rank": j + 1})
        if s.get("ranges") != validated[j].get("ranges"):
            out["ranges_changed"].append(s["title"])
    out["added_by_user"] = [t for t in titles_v if t not in titles_p]
    return out


def compare(folder="history", fps=None):
    res, lines = {}, []
    decisions = load_json("decisions.json") if os.path.exists("decisions.json") else {}
    fps = fps or decisions.get("fps") or 25
    prop = _latest(folder, "04_derushage_proposal")
    val = _latest(folder, "decisions_linear_v") or ("decisions.json" if decisions else None)
    if prop and val:
        r = compare_removals(load_json(prop).get("linear", {}).get("remove", []),
                             load_json(val).get("linear", {}).get("remove", []), fps)
        res["derushage"] = dict(r, proposal=os.path.basename(prop), validated=os.path.basename(val))
        lines.append(f"## Derushage ({os.path.basename(prop)} -> {os.path.basename(val)})")
        lines.append(f"accepted {len(r['accepted'])}, adjusted {len(r['adjusted'])}, refused {len(r['refused'])}, "
                     f"added by the user {len(r['added_by_user'])}")
        lines += [f"- adjusted: {x['label']} {x['proposed']} -> {x['validated']}" for x in r["adjusted"]]
        lines += [f"- refused: {x['label']} {x['start']}-{x['end']}" for x in r["refused"]]
        lines += [f"- added by the user: {x['label']} {x['start']}-{x['end']}" for x in r["added_by_user"]]
    prop = _latest(folder, "06_montage_proposal")
    val = _latest(folder, "decisions_montage_v") or ("decisions.json" if decisions.get("montage") else None)
    if prop and val:
        r = compare_sequences(load_json(prop).get("montage", {}).get("sequences", []),
                              load_json(val).get("montage", {}).get("sequences", []))
        res["montage"] = dict(r, proposal=os.path.basename(prop), validated=os.path.basename(val))
        lines.append(f"## Montage order ({os.path.basename(prop)} -> {os.path.basename(val)})")
        lines.append(f"same place {len(r['kept_same_place'])}, moved {len(r['moved'])}, dropped {len(r['dropped'])}, "
                     f"added by the user {len(r['added_by_user'])}, ranges changed {len(r['ranges_changed'])}")
        lines += [f"- moved: {m['title']} {m['proposed_rank']} -> {m['validated_rank']}" for m in r["moved"]]
        lines += [f"- dropped: {t}" for t in r["dropped"]] + [f"- added by the user: {t}" for t in r["added_by_user"]]
    if not res:
        raise SystemExit(f"nothing to compare in {folder}/ (no saved proposal with its validated decisions)")
    save_json(os.path.join(folder, "comparison.json"), res)
    text = "\n".join(lines) + "\n"
    with open(os.path.join(folder, "comparison.md"), "w", encoding="utf-8") as f:
        f.write(text)
    return text


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save")
    s.add_argument("kind", choices=sorted(KINDS))
    s.add_argument("file")
    s.add_argument("--model", help="model that wrote the proposal (e.g. claude-opus-5-5)")
    c = sub.add_parser("compare")
    c.add_argument("--fps", type=float)
    args = ap.parse_args()
    if args.cmd == "save":
        print(save(args.kind, args.file, args.model))
    else:
        sys.stdout.write(compare(fps=args.fps))


if __name__ == "__main__":
    main()
