"""Updates from GitHub Releases.

A release carries KiCadBOM-windows.zip (the program folder: KiCadBOM.exe + _internal) and its
.sha256. The folder build is used instead of a single .exe because antivirus programs and Chrome
flag single-file PyInstaller programs, which unpack themselves to a temp folder at every start.

The running program can't overwrite its own files, so the verified zip is unpacked next to the
user data and a small script copies it over the program folder once this process has exited,
then starts the new version.

Older single-file versions (KiCadBOM.exe) are still updated by swapping the .exe.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

from .net import urlopen
from . import __version__
from .config import app_dir

REPO = "Kaelor9/kicad-bomtool"
ASSET = "KiCadBOM.exe"            # single-file build (up to v1.5.0)
ZIP_ASSET = "KiCadBOM-windows.zip"  # folder build
CHECK_EVERY = 6 * 3600
_cache = {"time": 0, "info": None}


def _ver(tag):
    return tuple(int(x) for x in re.findall(r"\d+", tag or "")[:3]) or (0,)


def frozen():
    return bool(getattr(sys, "frozen", False))


def folder_build():
    """Running as KiCadBOM.exe next to its _internal folder (not the single-file build)?"""
    return frozen() and os.path.isdir(os.path.join(os.path.dirname(sys.executable), "_internal"))


def _get(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": f"kicad-bomtool/{__version__}"})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def check(force=False):
    """Latest release info: {current, latest, newer, notes, page, exe_url, sha_url, can_install, error}."""
    if not force and _cache["info"] and time.time() - _cache["time"] < CHECK_EVERY:
        return _cache["info"]
    info = {"current": __version__, "latest": None, "newer": False, "notes": "", "page": "",
            "can_install": frozen(), "error": ""}
    try:
        rel = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
        info["latest"] = rel.get("tag_name", "").lstrip("v")
        info["notes"] = (rel.get("body") or "")[:4000]
        info["page"] = rel.get("html_url", "")
        assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets") or []}
        name = ZIP_ASSET if folder_build() or ZIP_ASSET in assets else ASSET
        if not folder_build() and name == ZIP_ASSET:
            info["can_install"] = False     # a single .exe can't become a folder by itself
        info["exe_url"], info["sha_url"] = assets.get(name), assets.get(name + ".sha256")
        info["newer"] = _ver(info["latest"]) > _ver(__version__)
        if not (info["exe_url"] and info["sha_url"]):
            info["can_install"] = False
    except urllib.error.HTTPError as e:
        info["error"] = "Ingen udgivelser fundet endnu." if e.code == 404 else f"GitHub svarede {e.code}."
    except (urllib.error.URLError, OSError, ValueError) as e:
        info["error"] = f"Kunne ikke tjekke for opdateringer ({getattr(e, 'reason', e)})."
    _cache.update(time=time.time(), info=info)
    return info


def install():
    """Download, verify and swap in the new .exe, then start it. Returns a message; the caller exits."""
    info = check(force=True)
    if not info["newer"]:
        raise ValueError("Du har allerede den nyeste version.")
    if not frozen():
        raise ValueError("Programmet kører fra kildekoden – opdatér med 'git pull'.")
    if not info["can_install"]:
        raise ValueError("Udgivelsen mangler programfilen – hent den manuelt fra GitHub.")
    data = _get(info["exe_url"], "application/octet-stream")
    want = _get(info["sha_url"], "application/octet-stream").decode("ascii", "replace").split()[0].lower()
    got = hashlib.sha256(data).hexdigest()
    if got != want:
        raise ValueError("Den hentede fil er beskadiget (checksum passer ikke) – intet er ændret.")
    if folder_build():
        return _install_folder(data, info["latest"])
    exe = sys.executable
    new, old = exe + ".new", os.path.splitext(exe)[0] + ".old"
    with open(new, "wb") as fh:
        fh.write(data)
    if os.path.exists(old):
        os.remove(old)
    os.replace(exe, old)          # allowed while running
    try:
        os.replace(new, exe)
    except OSError:
        os.replace(old, exe)      # put the old one back
        raise
    # Without this the new .exe inherits PyInstaller's variables and tries to run
    # from the old version's (soon deleted) unpack folder instead of starting fresh.
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen([exe] + sys.argv[1:], close_fds=True, env=env,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return f"Opdateret til {info['latest']} – starter igen."


def _install_folder(data, version):
    """Unpack the new program folder and let a script copy it over this one after we exit."""
    import io  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    work = os.path.join(app_dir(), "update")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():   # nothing may land outside the update folder
            if n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/"):
                raise ValueError("Opdateringen indeholder ugyldige stier – intet er ændret.")
        z.extractall(work)
    src = next((r for r, _, fs in os.walk(work) if "KiCadBOM.exe" in fs), None)
    if not src or not os.path.isdir(os.path.join(src, "_internal")):
        raise ValueError("Opdateringen mangler programmet – intet er ændret.")
    dst = os.path.dirname(sys.executable)
    script = os.path.join(work, "install.cmd")
    # Wait for this process to end, copy the new files over (never deletes anything in the
    # program folder), start the new version.
    with open(script, "w", encoding="mbcs" if os.name == "nt" else "utf-8") as fh:
        fh.write(f"""@echo off
:wait
tasklist /FI "PID eq {os.getpid()}" 2>nul | find "{os.getpid()}" >nul && (ping -n 2 127.0.0.1 >nul & goto wait)
robocopy "{src}" "{dst}" /E /R:10 /W:1 /NFL /NDL /NJH /NJS /NP >nul
start "" "{os.path.join(dst, "KiCadBOM.exe")}"
""")
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen(["cmd", "/c", script], close_fds=True, env=env, cwd=work, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return f"Opdateret til {version} – starter igen."


def cleanup():
    """Remove the previous version left behind by an update."""
    if folder_build():
        import shutil  # noqa: PLC0415
        shutil.rmtree(os.path.join(app_dir(), "update"), ignore_errors=True)
        return
    if frozen():
        old = os.path.splitext(sys.executable)[0] + ".old"
        for _ in range(10):
            try:
                if os.path.exists(old):
                    os.remove(old)
                break
            except OSError:
                time.sleep(0.5)   # the old process may still be closing


__all__ = ["check", "install", "cleanup", "folder_build", "app_dir", "REPO"]
