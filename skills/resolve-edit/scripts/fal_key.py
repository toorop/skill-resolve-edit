"""fal.ai API key storage in the Windows Credential Manager (per-user, DPAPI-encrypted), stdlib only.

Why not an environment variable: a global env var is inherited by every program the user runs and shows up in
process dumps / crash reports. The Credential Manager keeps it encrypted at rest and only returns it on request.
(Any program running under the same Windows account could still ask for it: this protects against casual
exposure, not against malware running as the user.)

Store the key (the user runs this THEMSELVES in a terminal; never shown to Claude):
    python fal_key.py set               (masked prompt: one '*' per character, Ctrl+V pastes)
    python fal_key.py set --clipboard   (reads the clipboard directly)
The clipboard is cleared after a paste.
Check / remove:
    python fal_key.py check
    python fal_key.py delete
Scripts call get_key(): Credential Manager first, then the FAL_KEY environment variable as a fallback.
It appears in the Windows Credential Manager (Windows credentials) as resolve-edit/fal.
"""
import ctypes
import ctypes.wintypes as wt
import getpass
import os
import subprocess
import sys

TARGET = "resolve-edit/fal"
LEGACY_TARGETS = []  # former entry names, read only, so an existing key keeps working
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR), ("Comment", wt.LPWSTR),
                ("LastWritten", wt.FILETIME), ("CredentialBlobSize", wt.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_char)), ("Persist", wt.DWORD),
                ("AttributeCount", wt.DWORD), ("Attributes", ctypes.c_void_p), ("TargetAlias", wt.LPWSTR),
                ("UserName", wt.LPWSTR)]


def _advapi():
    if os.name != "nt":
        return None
    return ctypes.WinDLL("advapi32", use_last_error=True)


def get_key():
    adv = _advapi()
    if adv:
        for target in [TARGET] + LEGACY_TARGETS:
            pcred = ctypes.POINTER(CREDENTIAL)()
            if adv.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
                try:
                    c = pcred.contents
                    return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-8")
                finally:
                    adv.CredFree(pcred)
    return os.environ.get("FAL_KEY")


def set_key(key):
    adv = _advapi()
    blob = key.encode("utf-8")
    buf = ctypes.create_string_buffer(blob, len(blob))
    c = CREDENTIAL()
    c.Type = CRED_TYPE_GENERIC
    c.TargetName = TARGET
    c.UserName = "fal"
    c.CredentialBlobSize = len(blob)
    c.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))
    c.Persist = CRED_PERSIST_LOCAL_MACHINE
    if not adv.CredWriteW(ctypes.byref(c), 0):
        raise OSError(ctypes.get_last_error(), "CredWriteW failed")


def _clipboard():
    return subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                          capture_output=True, text=True).stdout.strip()


def masked_input(prompt):
    """Hidden input that echoes '*' per character (Windows console). Ctrl+V pastes even in consoles that don't
    handle it themselves; Backspace works; Enter validates; Esc/Ctrl+C aborts."""
    import msvcrt
    sys.stdout.write(prompt)
    sys.stdout.flush()
    chars, pasted = [], False
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            break
        if ch in ("\x03", "\x1b"):
            sys.stdout.write("\n")
            raise SystemExit("annule")
        if ch in ("\x00", "\xe0"):  # special key prefix (arrows...): skip its second code
            msvcrt.getwch()
            continue
        if ch == "\x08":
            if chars:
                chars.pop()
                sys.stdout.write("\b \b")
        elif ch == "\x16":  # Ctrl+V not handled by the console: paste the clipboard ourselves
            clip = _clipboard()
            chars.extend(clip)
            sys.stdout.write("*" * len(clip))
            pasted = True
        elif ord(ch) >= 32:
            chars.append(ch)
            sys.stdout.write("*")
        sys.stdout.flush()
    sys.stdout.write(f"\n{len(chars)} caracteres saisis\n")
    return "".join(chars).strip(), pasted


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "set":
        pasted = False
        if "--clipboard" in sys.argv:  # read the clipboard directly
            key, pasted = _clipboard(), True
        elif os.name == "nt":
            key, pasted = masked_input("Cle fal.ai (collez avec Ctrl+V, une etoile par caractere) : ")
        else:
            key = getpass.getpass("Cle fal.ai : ").strip()
        if pasted:  # don't leave the key lying in the clipboard
            subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ' '"], capture_output=True)
        if len(key) < 20 or any(ord(ch) < 32 for ch in key):
            raise SystemExit(f"Cle invalide ({len(key)} caracteres) : rien n'a ete enregistre. "
                             "Copiez la cle puis lancez: python fal_key.py set --clipboard")
        set_key(key)
        print(f"Cle enregistree ({len(key)} caracteres) dans le Gestionnaire d'identification Windows ({TARGET}).")
    elif cmd == "delete":
        ok = _advapi().CredDeleteW(TARGET, CRED_TYPE_GENERIC, 0)
        print("supprimee" if ok else "aucune cle enregistree")
    else:
        k = get_key()
        print(f"cle trouvee ({len(k)} caracteres)" if k else "aucune cle trouvee")  # never print any part of it


if __name__ == "__main__":
    main()
