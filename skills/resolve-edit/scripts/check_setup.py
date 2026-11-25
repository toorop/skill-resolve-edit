"""Step 0: check that this computer has what the skill needs, and say how to install what is missing.

Checks Python, ffmpeg / ffprobe (with the soxr resampler used to prepare the audio), the fal.ai key (only its
presence and length, never its value), HTTPS access to fal.ai, the channel profile and its settings (cameras).
DaVinci Resolve itself is checked by Claude through the MCP (get_resolve_status), not here. Images (contact sheets,
thumbnails) are rendered by Resolve, not by ffmpeg.

Usage: python check_setup.py [--profile DIR] [--offline]
Exit code 0 when nothing is missing (warnings allowed), 1 otherwise.
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from common import camera_rules, find_profile, load_settings

SYSTEM = platform.system()  # "Windows", "Darwin" (macOS), "Linux"
INSTALL = {
    "python": {"Windows": "winget install Python.Python.3.13   (or https://www.python.org/downloads/)",
               "Darwin": "brew install python   (or https://www.python.org/downloads/)",
               "Linux": "sudo apt install python3   (Debian/Ubuntu; other distributions: their package manager)"},
    "ffmpeg": {"Windows": "winget install Gyan.FFmpeg   (full build; then open a NEW terminal so the PATH is updated)",
               "Darwin": "brew install ffmpeg",
               "Linux": "sudo apt install ffmpeg   (Debian/Ubuntu)"},
}
problems, warnings = [], []


def line(status, what, detail=""):
    print(f"[{status:4}] {what}" + (f": {detail}" if detail else ""))


def ok(what, detail=""):
    line("OK", what, detail)


def warn(what, detail):
    warnings.append(what)
    line("WARN", what, detail)


def fail(what, detail, install=None):
    problems.append(what)
    line("FAIL", what, detail)
    if install:
        print(f"       install: {INSTALL[install].get(SYSTEM, INSTALL[install]['Linux'])}")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def check_python():
    v = sys.version_info
    if v < (3, 8):
        fail("Python", f"{platform.python_version()} is too old (3.8 or later)", "python")
    else:
        ok("Python", f"{platform.python_version()} ({sys.executable})")


def check_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        if not path:
            fail(tool, "not found in the PATH", "ffmpeg")
            return
        first = (run([tool, "-version"]).stdout.splitlines() or ["?"])[0].split(" Copyright")[0]
        ok(tool, f"{first} ({path})")
    soxr = run(["ffmpeg", "-hide_banner", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000", "-t", "0.1",
                "-af", "aresample=16000:resampler=soxr", "-f", "null", "-"])
    if soxr.returncode:
        fail("ffmpeg soxr resampler", "not available (needed to prepare the audio): install a full build", "ffmpeg")
    else:
        ok("ffmpeg soxr resampler")


def check_key():
    try:
        from fal_key import get_key
        key = get_key()
    except Exception as e:  # noqa: BLE001 - report any storage problem
        key = None
        warn("fal.ai key", f"could not read the key store ({e.__class__.__name__})")
    if key:
        ok("fal.ai key", f"found ({len(key)} characters)")
    else:
        fail("fal.ai key", "missing: the USER runs `python <skill>/scripts/fal_key.py set` in a terminal "
             "(Windows), or sets the FAL_KEY environment variable (other systems). Never paste it in the chat.")


def check_network():
    for url in ("https://rest.alpha.fal.ai/", "https://v3.fal.media/"):
        try:
            urllib.request.urlopen(url, timeout=15)
            ok("HTTPS", url)
        except urllib.error.HTTPError:  # any HTTP answer means TLS and network are fine
            ok("HTTPS", url)
        except urllib.error.URLError as e:
            reason = str(e.reason)
            if "CERTIFICATE_VERIFY_FAILED" in reason:
                warn("HTTPS " + url, "certificate not trusted yet by Python; transcribe_fal.py works around it on "
                     "Windows (curl.exe); elsewhere update the system's CA certificates")
            else:
                fail("HTTPS " + url, f"unreachable ({reason[:80]})")


def check_profile(profile):
    folder = profile or find_profile()
    if not folder or not os.path.isdir(folder):
        fail("channel profile", "not found (no resolve-edit.json in this folder or above, no --profile): create one "
             "at Step 0 (templates/profile/)")
        return
    ok("channel profile", folder)
    if not os.path.isfile(os.path.join(folder, "profile.md")):
        warn("profile.md", "missing in the profile folder")
    try:
        settings = load_settings(folder)
    except ValueError as e:
        fail("settings.json", f"not valid JSON: {e}")
        return
    if not settings:
        warn("settings.json", "missing or empty: generic defaults only")
        return
    cams = camera_rules(settings)
    ok("cameras", ", ".join(c["name"] for c in cams) if cams else "none described (rushes still work: names from "
       "their metadata, file-name short names)")
    for k in ("flags", "thumbnail"):
        if not settings.get(k):
            warn(f"settings.json {k}", "empty: the matching step will stop and say so")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", help="channel profile folder (default: found via resolve-edit.json)")
    ap.add_argument("--offline", action="store_true", help="skip the HTTPS check")
    args = ap.parse_args()
    print(f"System: {SYSTEM} {platform.release()}" + ("" if SYSTEM == "Windows" else
                                                      "  (the skill is tested on Windows only)"))
    check_python()
    check_ffmpeg()
    check_key()
    if not args.offline:
        check_network()
    check_profile(args.profile)
    print(f"\n{len(problems)} missing, {len(warnings)} warning(s)."
          + ("" if not problems else " Fix the missing items before Step 1."))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
