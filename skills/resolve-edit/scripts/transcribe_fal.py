"""Transcribe the prepared audio parts with ElevenLabs Scribe v2 on fal.ai (pay per use, no subscription).

Reads the API key from the Windows Credential Manager (fal_key.py), FAL_KEY env var as fallback.
NEVER store it in files or the repo. Verified 2026-09-24: 2 min part -> ~10 s, same words and timings (median 0 ms,
max 40 ms) as the fal.ai web form.
For each part of the manifest: upload to fal storage, submit to the queue, poll, save <part>.json,
then merge everything into one transcript aligned on the reference timeline.

Usage:
  python transcribe_fal.py MANIFEST.json OUT_TRANSCRIPT.json [--language fr] [--keyterm "Name" ...] [--no-diarize]
                           [--profile DIR]
Language and keyterms default to the channel profile settings.json ("language", "transcription": {"keyterms"});
without a language, Scribe detects it.
Cost: about $0.008 per audio minute (+30% if keyterms are used).
"""
import argparse
import json
import mimetypes
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from common import add_profile_arg, load_json, load_settings, save_json
from fal_key import get_key
from merge_transcripts import merge

MODEL = "fal-ai/elevenlabs/speech-to-text/scribe-v2"
REST = "https://rest.alpha.fal.ai"
QUEUE = "https://queue.fal.run"


def warm_windows_roots(url):
    """Windows installs most root certificates only when a Windows program first meets them; Python's ssl reads the
    store but cannot trigger that download, so a host signed by a root this PC has never seen fails with
    CERTIFICATE_VERIFY_FAILED (seen 2026-11-24 with fal's storage host v3.fal.media, SSL.com root). One request with
    curl.exe (built into Windows 10+, uses the Windows TLS stack) makes Windows fetch the root; then Python works."""
    if os.name != "nt":
        return False
    host = urllib.parse.urlsplit(url)
    try:
        subprocess.run(["curl.exe", "-s", "-o", os.devnull, f"{host.scheme}://{host.netloc}/"], timeout=30, check=False)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def http(method, url, key=None, body=None, content_type="application/json", timeout=600, _retry=True):
    try:
        return _http(method, url, key, body, content_type, timeout)
    except urllib.error.URLError as e:
        if _retry and isinstance(e.reason, ssl.SSLCertVerificationError) and warm_windows_roots(url):
            return http(method, url, key, body, content_type, timeout, _retry=False)
        raise


def _http(method, url, key=None, body=None, content_type="application/json", timeout=600):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if key:
        req.add_header("Authorization", f"Key {key}")
    if data is not None:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw and r.headers.get_content_type() == "application/json" else raw
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {url} -> HTTP {e.code}: {e.read()[:500]!r}")


def upload(path, key):
    ctype = mimetypes.guess_type(path)[0] or "audio/wav"
    init = http("POST", f"{REST}/storage/upload/initiate?storage_type=fal-cdn-v3", key,
                {"file_name": os.path.basename(path), "content_type": ctype})
    with open(path, "rb") as f:
        http("PUT", init["upload_url"], body=f.read(), content_type=ctype)
    return init["file_url"]


def transcribe(audio_url, key, language, keyterms, diarize):
    payload = {"audio_url": audio_url, "tag_audio_events": True, "diarize": diarize}
    if language:
        payload["language_code"] = language
    if keyterms:
        payload["keyterms"] = keyterms
    sub = http("POST", f"{QUEUE}/{MODEL}", key, payload)
    status_url = sub.get("status_url") or f"{QUEUE}/{MODEL}/requests/{sub['request_id']}/status"
    result_url = sub.get("response_url") or f"{QUEUE}/{MODEL}/requests/{sub['request_id']}"
    while True:
        st = http("GET", status_url, key)
        if st.get("status") == "COMPLETED":
            break
        if st.get("error"):
            raise SystemExit(f"fal error: {st.get('error')}")
        time.sleep(3)
    return http("GET", result_url, key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("out")
    ap.add_argument("--language")
    ap.add_argument("--keyterm", action="append", default=[])
    ap.add_argument("--no-diarize", action="store_true")
    add_profile_arg(ap)
    args = ap.parse_args()
    settings = load_settings(args.profile)
    args.language = args.language or settings.get("language")
    args.keyterm = args.keyterm or settings.get("transcription", {}).get("keyterms", [])

    key = get_key()
    if not key:
        raise SystemExit("No fal.ai key: the user must run `python fal_key.py set` in a terminal (Windows Credential "
                         "Manager), or define FAL_KEY.")
    parts = []
    for m in load_json(args.manifest):
        out_part = os.path.splitext(m["file"])[0] + ".json"
        if os.path.exists(out_part) and os.path.getsize(out_part) > 0:
            print(f"{os.path.basename(out_part)} already exists, skipping")
        else:
            print(f"uploading {os.path.basename(m['file'])} ({m['duration']:.0f}s)...", flush=True)
            url = upload(m["file"], key)
            print("transcribing...", flush=True)
            res = transcribe(url, key, args.language, args.keyterm, not args.no_diarize)
            if not res.get("words"):
                raise SystemExit(f"empty transcription for {m['file']}: {str(res)[:300]}")
            save_json(out_part, res)
            print(f"  {len(res['words'])} tokens, language {res.get('language_code')}")
        parts.append((out_part, m["offset"]))
    merge(parts, args.out)


if __name__ == "__main__":
    sys.exit(main())
